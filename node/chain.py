from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional, Tuple

from coin_params import (
    HALVING_INTERVAL, INITIAL_SUBSIDY, RETARGET_INTERVAL,
    GENESIS_PREV_HASH, block_subsidy,
    COINBASE_MATURITY, MAX_BLOCK_SIZE, MAX_TX_INPUTS, MAX_TX_OUTPUTS,
)
from node.block import Block, bits_to_target, merkle_root, difficulty_to_bits
from node.pow import calculate_next_bits
from node.storage import KeyValueStore, WriteBatch, open_kv_store
from node.tx import TxInput, TxOutput, UTXOSet, validate_transaction, sha256d_hex

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage key helpers
# ---------------------------------------------------------------------------

def _block_h_key(height: int) -> bytes:
    return f"block:h:{height}".encode()

def _block_hash_key(h: str) -> bytes:
    return f"block:hash:{h}".encode()

def _utxo_key(txid: str, index: int) -> bytes:
    return f"utxo:{txid}:{index}".encode()

def _txidx_key(txid: str) -> bytes:
    return f"txindex:{txid}".encode()

def _cb_height_key(txid: str) -> bytes:
    """Key for storing the block height at which a coinbase tx was mined."""
    return f"cbheight:{txid}".encode()

def _chain_work_key(height: int) -> bytes:
    return f"chainwork:{height}".encode()

META_KEY = b"meta"


# ---------------------------------------------------------------------------
# Blockchain
# ---------------------------------------------------------------------------

class Blockchain:
    def __init__(
        self,
        data_dir: str,
        no_retarget: bool = False,
        readonly: bool = False,
        network: str = "mainnet",
    ) -> None:
        self.store: KeyValueStore = open_kv_store(data_dir, readonly=readonly)
        self.utxo = UTXOSet()
        self.height: int = -1
        self.tip: str = ""
        self.cumulative_work: int = 0
        self.no_retarget = no_retarget
        self.network = network
        # chain_id for replay protection: 1=mainnet, 2=testnet, 3=regtest
        from node.network import NETWORKS
        net = NETWORKS.get(network)
        self.chain_id: int = net.chain_id if net else 1
        self._load_state()

    # ------------------------------------------------------------------
    # Startup: load metadata + rebuild UTXO
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        raw = self.store.get(META_KEY)
        if raw:
            d = json.loads(raw.decode())
            self.height = d.get("height", -1)
            self.tip = d.get("tip", "")
            self.cumulative_work = d.get("cumulative_work", 0)
        self._rebuild_utxo()
        # Startup integrity check (PERS-003)
        if self.height >= 0 and self.tip:
            b = self.get_block(self.height)
            if b and b.compute_hash() != self.tip:
                log.warning(
                    "STARTUP: tip hash mismatch at height %d — rebuilding UTXO",
                    self.height
                )
                self._rebuild_utxo_from_chain()

    def _rebuild_utxo(self) -> None:
        """Rebuild in-memory UTXO from persisted store."""
        self.utxo = UTXOSet()
        utxo_prefix = b"utxo:"
        for key, val in self.store.iter_prefix(utxo_prefix):
            parts = key.decode().split(":", 2)
            if len(parts) != 3:
                continue
            txid, idx = parts[1], int(parts[2])
            out = TxOutput(**json.loads(val.decode()))
            self.utxo.utxos[(txid, idx)] = out
        # Rebuild coinbase heights
        cb_prefix = b"cbheight:"
        for key, val in self.store.iter_prefix(cb_prefix):
            txid = key.decode()[len("cbheight:"):]
            height = int(val.decode())
            self.utxo.coinbase_heights[txid] = height

    def _rebuild_utxo_from_chain(self) -> None:
        """Full chain replay to rebuild UTXO — used as fallback on corruption."""
        log.info("Rebuilding UTXO from chain replay (height=%d)", self.height)
        self.utxo = UTXOSet()
        for h in range(0, self.height + 1):
            b = self.get_block(h)
            if not b:
                break
            for txd in b.transactions:
                txid = txd["txid"]
                is_cb = bool(txd.get("coinbase"))
                if not is_cb:
                    for tin in txd.get("inputs", []):
                        self.utxo.utxos.pop((tin["txid"], tin["index"]), None)
                for idx, out in enumerate(txd.get("outputs", [])):
                    self.utxo.utxos[(txid, idx)] = TxOutput(**out)
                if is_cb:
                    self.utxo.coinbase_heights[txid] = h

    def _save_meta(self, batch: WriteBatch) -> None:
        batch.put(META_KEY, json.dumps({
            "height": self.height,
            "tip": self.tip,
            "cumulative_work": self.cumulative_work,
        }).encode())

    # ------------------------------------------------------------------
    # Block retrieval
    # ------------------------------------------------------------------

    def get_block(self, height: int) -> Optional[Block]:
        raw = self.store.get(_block_h_key(height))
        if not raw:
            return None
        return Block.from_dict(json.loads(raw.decode()))

    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        raw = self.store.get(_block_hash_key(block_hash))
        if not raw:
            return None
        height = json.loads(raw.decode())["height"]
        return self.get_block(height)

    def get_tx(self, txid: str) -> Optional[dict]:
        raw = self.store.get(_txidx_key(txid))
        if not raw:
            return None
        height = json.loads(raw.decode())["block_height"]
        b = self.get_block(height)
        if not b:
            return None
        for tx in b.transactions:
            if tx.get("txid") == txid:
                return tx
        return None

    # ------------------------------------------------------------------
    # Chain work
    # ------------------------------------------------------------------

    def _block_work(self, block: Block) -> int:
        """Work for a single block = 2^256 / (target + 1)."""
        target = bits_to_target(block.bits)
        if target == 0:
            return 2 ** 256
        return (2 ** 256) // (target + 1)

    def get_cumulative_work(self, height: int) -> int:
        """Get stored cumulative work at a given height."""
        raw = self.store.get(_chain_work_key(height))
        if not raw:
            return 0
        return int(raw.decode())

    # ------------------------------------------------------------------
    # Genesis
    # ------------------------------------------------------------------

    def add_genesis(self, coinbase_tx: dict) -> Block:
        if self.height >= 0:
            return self.get_block(0)  # type: ignore
        genesis = Block.create(
            index=0, prev_hash=GENESIS_PREV_HASH,
            transactions=[coinbase_tx], difficulty=0,
        )
        self._commit(genesis)
        return genesis

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _median_time_past(self, index: int) -> int:
        timestamps = []
        for h in range(max(0, index - 11), index):
            b = self.get_block(h)
            if b:
                timestamps.append(b.timestamp)
        if not timestamps:
            return 0
        timestamps.sort()
        return timestamps[len(timestamps) // 2]

    def _total_fees(self, block: Block, utxo_snapshot: Optional[UTXOSet] = None) -> int:
        snap = utxo_snapshot or self.utxo
        total = 0
        for txd in block.transactions:
            if txd.get("coinbase"):
                continue
            in_sum = sum(
                snap.get(i["txid"], i["index"]).value
                for i in txd.get("inputs", [])
                if snap.has(i["txid"], i["index"])
            )
            out_sum = sum(o["value"] for o in txd.get("outputs", []))
            total += max(0, in_sum - out_sum)
        return total

    def expected_bits(self, height: int) -> int:
        if height == 0:
            return difficulty_to_bits(0)
        if self.no_retarget:
            prev = self.get_block(height - 1)
            return prev.bits if prev else difficulty_to_bits(1)
        if height % RETARGET_INTERVAL != 0:
            prev = self.get_block(height - 1)
            return prev.bits if prev else difficulty_to_bits(1)
        first = self.get_block(height - RETARGET_INTERVAL)
        last = self.get_block(height - 1)
        if not first or not last:
            prev = self.get_block(height - 1)
            return prev.bits if prev else difficulty_to_bits(1)
        return calculate_next_bits(last.bits, first.timestamp, last.timestamp)

    def validate_block(
        self,
        block: Block,
        expected_bits: Optional[int] = None,
        utxo_override: Optional[UTXOSet] = None,
    ) -> bool:
        """
        Full block validation. Returns True iff block is valid.

        Checks (in order):
        1.  PoW — hash meets target
        2.  bits == expected_bits (retarget enforcement)
        3.  prev_hash linkage
        4.  Merkle root
        5.  Timestamp (MTP + drift) — skipped for genesis
        6.  Block size limit (Phase 12)
        7.  At least one transaction required (CONS-009)
        8.  Exactly one coinbase, must be first (CONS-008)
        9.  No duplicate txids (CONS-008)
        10. Coinbase value <= subsidy + fees
        11. All tx outputs non-negative (CONS-010)
        12. Non-coinbase tx count within limits (Phase 12)
        13. Non-coinbase txs validated with coinbase maturity (CONS-002)
        """
        # 1. PoW
        if not block.meets_target():
            return False

        # 2. bits consistency
        if expected_bits is not None and block.bits != expected_bits:
            return False

        # 3. prev_hash linkage
        if block.index == 0:
            if block.prev_hash != GENESIS_PREV_HASH:
                return False
        else:
            prev = self.get_block(block.index - 1)
            if not prev or prev.compute_hash() != block.prev_hash:
                return False

        # 4. Merkle root
        txids = [t["txid"] for t in block.transactions]
        if merkle_root(txids) != block.tx_merkle_root:
            return False

        # 5. Timestamp
        if block.index > 0:
            mtp = self._median_time_past(block.index)
            if not block.validate_timestamp(mtp):
                return False

        # 6. Block size limit
        block_bytes = len(json.dumps(block.to_dict()).encode())
        if block_bytes > MAX_BLOCK_SIZE:
            return False

        # 7. At least one transaction (CONS-009)
        if not block.transactions:
            return False

        # 8. Coinbase position and count
        coinbases = [t for t in block.transactions if t.get("coinbase")]
        if len(coinbases) > 1:
            return False
        if not block.transactions[0].get("coinbase"):
            return False   # must have coinbase as first tx

        # 9. No duplicate txids (CONS-008)
        seen_txids = set()
        for txd in block.transactions:
            txid = txd.get("txid")
            if txid in seen_txids:
                return False
            seen_txids.add(txid)

        # 10. Coinbase value cap
        cb = coinbases[0]
        if cb.get("inputs"):
            return False
        cb_outs = cb.get("outputs", [])
        if not cb_outs:
            return False
        for cb_out in cb_outs:
            if cb_out.get("value", -1) < 0:
                return False
        cb_total = sum(o.get("value", 0) for o in cb_outs)
        snap = (utxo_override or self.utxo).snapshot()
        total_fees = self._total_fees(block, snap)
        if cb_total > block_subsidy(block.index) + total_fees:
            return False

        # 11. All outputs non-negative for non-coinbase txs
        for txd in block.transactions:
            if txd.get("coinbase"):
                continue
            for out in txd.get("outputs", []):
                if out.get("value", 0) < 0:
                    return False

        # 12+13. Validate non-coinbase txs with snapshot (coinbase maturity enforced)
        snap = (utxo_override or self.utxo).snapshot()
        for txd in block.transactions:
            if txd.get("coinbase"):
                continue
            if not validate_transaction(
                txd, snap,
                chain_id=self.chain_id,
                current_height=block.index,
                coinbase_maturity=COINBASE_MATURITY if COINBASE_MATURITY > 0 else -1,
            ):
                return False
            # Apply to snapshot so subsequent txs in same block see the updates
            for tin in txd.get("inputs", []):
                snap.spend(TxInput(**tin))
            for idx, out in enumerate(txd.get("outputs", [])):
                snap.utxos[(txd["txid"], idx)] = TxOutput(**out)

        return True

    # ------------------------------------------------------------------
    # add_block — linear chain + fork/reorg support (Phase 6+7)
    # ------------------------------------------------------------------

    def add_block(self, block: Block, difficulty: int = 1) -> bool:
        """
        Accept a block if it extends the current best chain OR
        represents a competing chain with more cumulative work (reorg).

        Returns True if block was accepted (possibly after reorg).
        """
        exp_bits = self.expected_bits(block.index)

        # Try to add as next sequential block (common case)
        if block.index == self.height + 1 and block.prev_hash == self.tip:
            if not self.validate_block(block, expected_bits=exp_bits):
                return False
            self._commit(block)
            return True

        # Fork detection: block.index <= self.height means competing chain
        if block.index <= self.height:
            return self._try_reorg(block)

        # Future block (gap) — can't add without parent
        return False

    def _try_reorg(self, new_block: Block) -> bool:
        """
        Check if new_block is tip of a chain with more cumulative work.
        If so, reorg to that chain.
        """
        # Find the common ancestor
        fork_block = self.get_block_by_hash(new_block.prev_hash)
        if fork_block is None:
            return False  # We don't have the parent — orphan

        fork_height = fork_block.index
        new_chain_tip = new_block

        # Calculate work of new chain from fork_height+1
        new_chain_work = self.get_cumulative_work(fork_height) + self._block_work(new_block)

        # Compare with current chain work
        if new_chain_work <= self.cumulative_work:
            return False  # Not more work — ignore

        # New chain has more work — validate new block and apply reorg
        exp_bits = self.expected_bits(new_block.index)
        if not self.validate_block(
            new_block,
            expected_bits=exp_bits,
            utxo_override=self._build_utxo_at_height(fork_height),
        ):
            return False

        log.info(
            "REORG: rolling back from h=%d to h=%d, applying new tip h=%d",
            self.height, fork_height, new_block.index
        )

        # Roll back UTXO to fork point
        self._rollback_to(fork_height)

        # Apply new block
        self._commit(new_block)
        return True

    def _build_utxo_at_height(self, target_height: int) -> UTXOSet:
        """Replay chain from 0 to target_height to get UTXO at that point."""
        u = UTXOSet()
        for h in range(0, target_height + 1):
            b = self.get_block(h)
            if not b:
                break
            for txd in b.transactions:
                txid = txd["txid"]
                is_cb = bool(txd.get("coinbase"))
                if not is_cb:
                    for tin in txd.get("inputs", []):
                        u.utxos.pop((tin["txid"], tin["index"]), None)
                for idx, out in enumerate(txd.get("outputs", [])):
                    u.utxos[(txid, idx)] = TxOutput(**out)
                if is_cb:
                    u.coinbase_heights[txid] = h
        return u

    def _rollback_to(self, target_height: int) -> None:
        """
        Roll back the chain and UTXO to target_height.
        Rebuilds in-memory UTXO from chain replay up to target_height.
        """
        # Rebuild UTXO at target_height from scratch
        self.utxo = self._build_utxo_at_height(target_height)
        self.height = target_height
        b = self.get_block(target_height)
        self.tip = b.compute_hash() if b else ""
        self.cumulative_work = self.get_cumulative_work(target_height)

        # Persist the rolled-back state atomically
        with self.store.atomic() as batch:
            self._flush_utxo(batch)
            self._save_meta(batch)

    def _flush_utxo(self, batch: WriteBatch) -> None:
        """Write in-memory UTXO to batch (used after rollback)."""
        # Delete all existing utxo: keys
        existing = list(self.store.iter_prefix(b"utxo:"))
        for k, _ in existing:
            batch.delete(k)
        # Write current UTXO
        for (txid, idx), out in self.utxo.utxos.items():
            batch.put(
                _utxo_key(txid, idx),
                json.dumps({"value": out.value, "address": out.address}).encode()
            )
        # Write coinbase heights
        existing_cb = list(self.store.iter_prefix(b"cbheight:"))
        for k, _ in existing_cb:
            batch.delete(k)
        for txid, height in self.utxo.coinbase_heights.items():
            batch.put(_cb_height_key(txid), str(height).encode())

    # ------------------------------------------------------------------
    # Atomic commit
    # ------------------------------------------------------------------

    def _commit(self, block: Block) -> None:
        block_hash = block.compute_hash()
        new_work = self.cumulative_work + self._block_work(block)

        with self.store.atomic() as batch:
            # Block storage
            batch.put(_block_h_key(block.index), json.dumps(block.to_dict()).encode())
            batch.put(_block_hash_key(block_hash), json.dumps({"height": block.index}).encode())
            # Cumulative work at this height
            batch.put(_chain_work_key(block.index), str(new_work).encode())

            for txd in block.transactions:
                txid = txd["txid"]
                is_cb = bool(txd.get("coinbase"))

                # Spend inputs
                if not is_cb:
                    for tin in txd.get("inputs", []):
                        batch.delete(_utxo_key(tin["txid"], tin["index"]))
                        self.utxo.utxos.pop((tin["txid"], tin["index"]), None)

                # Create outputs
                for idx, out in enumerate(txd.get("outputs", [])):
                    out_obj = TxOutput(**out)
                    batch.put(_utxo_key(txid, idx), json.dumps(out).encode())
                    self.utxo.utxos[(txid, idx)] = out_obj

                # Track coinbase maturity height (CONS-002)
                if is_cb:
                    batch.put(_cb_height_key(txid), str(block.index).encode())
                    self.utxo.coinbase_heights[txid] = block.index

                # Tx index
                batch.put(_txidx_key(txid),
                          json.dumps({"block_height": block.index}).encode())

            self.height = block.index
            self.tip = block_hash
            self.cumulative_work = new_work
            self._save_meta(batch)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_balance(self, address: str) -> int:
        return self.utxo.balance(address)

    def get_utxos_for_address(self, address: str) -> List[dict]:
        return [
            {"txid": txid, "index": idx, "value": out.value, "address": out.address}
            for (txid, idx), out in self.utxo.utxos.items()
            if out.address == address
        ]
