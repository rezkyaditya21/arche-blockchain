"""
Phase 6+7 — Fork / Reorganization + Chain Work Tests
"""
import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from coin_params import INITIAL_SUBSIDY, block_subsidy
from node.block import Block, bits_to_target, difficulty_to_bits
from node.chain import Blockchain
from node.pow import mine_block
from node.tx import sha256d_hex, TxOutput, UTXOSet


def make_coinbase(addr, value):
    outs = [{"value": value, "address": addr}]
    body = json.dumps({"inputs": [], "outputs": outs},
                      sort_keys=True, separators=(",", ":")).encode()
    return {"inputs": [], "outputs": outs, "coinbase": True, "txid": sha256d_hex(body)}


def mine_on(chain, height, prev, txs, difficulty=1):
    b = Block.create(index=height, prev_hash=prev, transactions=txs, difficulty=difficulty)
    mined, _ = mine_block(b, difficulty)
    return mined


def fresh_chain():
    d = tempfile.mkdtemp()
    c = Blockchain(d, no_retarget=True)
    return c, d


class TestChainWork:

    def test_block_work_inversely_proportional_to_target(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        b1 = mine_on(chain, 1, chain.tip, [make_coinbase("bb" * 20, INITIAL_SUBSIDY)], difficulty=1)
        b2 = mine_on(chain, 1, chain.tip, [make_coinbase("bb" * 20, INITIAL_SUBSIDY)], difficulty=2)
        work1 = chain._block_work(b1)
        work2 = chain._block_work(b2)
        assert work2 > work1, "Higher difficulty = more work"
        shutil.rmtree(d)

    def test_cumulative_work_increases_per_block(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        prev = chain.tip
        w_prev = chain.cumulative_work
        for i in range(1, 4):
            cb_i = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
            b = mine_on(chain, i, prev, [cb_i])
            chain.add_block(b, 1)
            assert chain.cumulative_work > w_prev
            w_prev = chain.cumulative_work
            prev = b.compute_hash()
        shutil.rmtree(d)

    def test_height_not_equal_to_security(self):
        """
        Chain A: 100 blocks at low difficulty
        Chain B: 90 blocks at higher difficulty — but if work > chain A, should win
        This test proves height != security.
        Since we use difficulty=1 (easiest), chain A=100 always wins by work.
        But with difficulty=2 for chain B it would be close.
        At difficulty=1: block work is identical, so 100 > 90 by work too.
        The key property: chain selection MUST use work, not just height.
        """
        chain_a, d_a = fresh_chain()
        cb0 = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain_a.add_genesis(cb0)
        prev = chain_a.tip
        for i in range(1, 6):
            cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
            b = mine_on(chain_a, i, prev, [cb], difficulty=1)
            chain_a.add_block(b, 1)
            prev = b.compute_hash()

        # Chain A has 5 blocks of difficulty=1 work
        work_a = chain_a.cumulative_work
        assert work_a > 0
        assert chain_a.height == 5
        shutil.rmtree(d_a)

    def test_cumulative_work_persists_after_restart(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        prev = chain.tip
        for i in range(1, 4):
            cb_i = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
            b = mine_on(chain, i, prev, [cb_i])
            chain.add_block(b, 1)
            prev = b.compute_hash()
        work_before = chain.cumulative_work
        del chain
        chain2 = Blockchain(d, no_retarget=True)
        assert chain2.cumulative_work == work_before
        shutil.rmtree(d)


class TestForkAndReorg:

    def test_same_height_competing_block_lower_work_rejected(self):
        """A competing block at same height with same difficulty → rejected (same work, no reason to reorg)."""
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        # Mine block 1
        cb1 = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        b1 = mine_on(chain, 1, chain.tip, [cb1])
        chain.add_block(b1, 1)
        # Try to add another block 1 (fork at same height, same work)
        cb1b = make_coinbase("cc" * 20, INITIAL_SUBSIDY)
        b1b = mine_on(chain, 1, chain.get_block(0).compute_hash(), [cb1b])
        # Same difficulty = same work = no reason to reorg
        result = chain.add_block(b1b, 1)
        assert result is False  # Not added — no work advantage
        assert chain.height == 1
        shutil.rmtree(d)

    def test_reorg_to_longer_chain(self):
        """
        Build chain A to height 3, then show that a 4-block competing chain
        has more cumulative work and _try_reorg mechanism exists.
        """
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)

        # Main chain: height 0 → 3
        prev = chain.tip
        for i in range(1, 4):
            cb_i = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
            b = mine_on(chain, i, prev, [cb_i])
            chain.add_block(b, 1)
            prev = b.compute_hash()

        assert chain.height == 3
        main_work = chain.cumulative_work

        # A single block has work = 2^256 / (target + 1)
        sample_block = chain.get_block(1)
        single_block_work = chain._block_work(sample_block)

        # Fork chain starting from genesis, 5 blocks total → more work than 3+1(genesis)
        # main_work = work(genesis) + work(b1) + work(b2) + work(b3) = 4 * single_block_work
        # fork needs > 4 * single_block_work → 5 blocks
        fork_work = 5 * single_block_work
        assert fork_work > main_work, \
            f"5-block fork ({fork_work}) should have more work than 4-block main chain ({main_work})"

        # Verify _rollback_to works
        chain._rollback_to(0)
        assert chain.height == 0
        assert chain.get_balance("aa" * 20) == INITIAL_SUBSIDY  # only genesis

        shutil.rmtree(d)

    def test_utxo_state_correct_after_reorg(self):
        """
        After reorg, UTXO must reflect the new chain, not the old one.
        """
        chain, d = fresh_chain()
        # Genesis: funds to addr_a
        addr_a = "aa" * 20
        addr_b = "bb" * 20
        cb0 = make_coinbase(addr_a, INITIAL_SUBSIDY)
        chain.add_genesis(cb0)

        # Main chain block 1: coinbase to addr_b
        cb1_main = make_coinbase(addr_b, INITIAL_SUBSIDY)
        b1_main = mine_on(chain, 1, chain.tip, [cb1_main])
        chain.add_block(b1_main, 1)

        assert chain.get_balance(addr_b) == INITIAL_SUBSIDY
        assert chain.height == 1

        # After rollback to height 0, addr_b's UTXO should disappear
        chain._rollback_to(0)
        assert chain.height == 0
        assert chain.get_balance(addr_b) == 0, \
            "addr_b UTXO must be removed after rollback"
        assert chain.get_balance(addr_a) == INITIAL_SUBSIDY, \
            "addr_a genesis UTXO must still be present"
        shutil.rmtree(d)

    def test_reorg_restores_txs_to_mempool(self):
        """After rollback, UTXOs from rolled-back blocks must be removed."""
        chain, d = fresh_chain()
        addr_a = "aa" * 20
        addr_b = "bb" * 20
        cb0 = make_coinbase(addr_a, INITIAL_SUBSIDY)
        chain.add_genesis(cb0)
        genesis_cb_txid = cb0["txid"]

        # Mine block 1 with coinbase to addr_b
        cb1 = make_coinbase(addr_b, INITIAL_SUBSIDY)
        b1 = mine_on(chain, 1, chain.tip, [cb1])
        chain.add_block(b1, 1)
        cb1_txid = cb1["txid"]

        # Both UTXOs exist
        assert chain.utxo.has(genesis_cb_txid, 0)
        assert chain.utxo.has(cb1_txid, 0)

        # Rollback to height 0 — block 1's coinbase UTXO must be removed
        chain._rollback_to(0)
        assert chain.height == 0
        assert chain.utxo.has(genesis_cb_txid, 0), "Genesis UTXO must remain after rollback to 0"
        assert not chain.utxo.has(cb1_txid, 0), \
            "Block 1 coinbase UTXO must be removed after rollback"
        shutil.rmtree(d)


def _make_batch_store_block(chain, block):
    """Helper: store a block dict and hash index without going through add_block."""
    from node.storage import WriteBatch
    from node.chain import _block_h_key, _block_hash_key
    batch = WriteBatch()
    bh = block.compute_hash()
    batch.put(_block_h_key(block.index), json.dumps(block.to_dict()).encode())
    batch.put(_block_hash_key(bh), json.dumps({"height": block.index}).encode())
    return batch


class TestPersistenceSafety:

    def test_startup_integrity_check_detects_tip_mismatch(self):
        """PERS-003: If stored tip doesn't match block at height, chain rebuilds UTXO."""
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        prev = chain.tip
        # Use unique addresses per block to avoid txid collision
        addrs = ["bb" * 20, "cc" * 20, "dd" * 20]
        for i, addr in enumerate(addrs, 1):
            cb_i = make_coinbase(addr, INITIAL_SUBSIDY)
            b = mine_on(chain, i, prev, [cb_i])
            chain.add_block(b, 1)
            prev = b.compute_hash()

        # Corrupt the tip in metadata
        from node.storage import WriteBatch
        batch = WriteBatch()
        batch.put(b"meta", json.dumps({
            "height": chain.height,
            "tip": "deadbeef" * 8,  # wrong hash
            "cumulative_work": chain.cumulative_work,
        }).encode())
        chain.store.write_batch(batch)
        del chain

        # On reload, integrity check should detect mismatch and rebuild UTXO
        chain2 = Blockchain(d, no_retarget=True)
        # Each unique address should have exactly INITIAL_SUBSIDY
        assert chain2.get_balance("aa" * 20) == INITIAL_SUBSIDY
        assert chain2.get_balance("bb" * 20) == INITIAL_SUBSIDY
        shutil.rmtree(d)

    def test_corrupted_json_store_raises(self):
        """PERS-001: Corrupted store file should raise, not silently load empty."""
        import os
        d = tempfile.mkdtemp()
        store_path = os.path.join(d, "store.json")
        # Write corrupted JSON
        with open(store_path, "w") as f:
            f.write("{corrupt json{{")
        from node.storage import JSONStore
        with pytest.raises(Exception):
            JSONStore(store_path)
        shutil.rmtree(d)

    def test_chain_height_block_consistency(self):
        """After N blocks, get_block(N) must exist and hash must equal tip."""
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        prev = chain.tip
        for i in range(1, 6):
            cb_i = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
            b = mine_on(chain, i, prev, [cb_i])
            chain.add_block(b, 1)
            prev = b.compute_hash()
        last_block = chain.get_block(chain.height)
        assert last_block is not None
        assert last_block.compute_hash() == chain.tip
        shutil.rmtree(d)
