from __future__ import annotations

import argparse
import json
import logging
import queue
import threading
import time
from typing import Dict, List, Optional

from node.block import Block
from node.chain import Blockchain
from node.pow import mine_block
from node.p2p import PeerClient, PeerServer
from node.tx import TxInput, TxOutput, validate_transaction
from node.network import get_network, set_network, NETWORKS
from coin_params import (
    COIN_NAME, COIN_TICKER, INITIAL_SUBSIDY, block_subsidy,
    DEFAULT_P2P_PORT, DEFAULT_HTTP_PORT, MAX_MEMPOOL_SIZE,
)

log = logging.getLogger(__name__)

MAX_BLOCKS_PER_RESP = 500
MAX_ORPHANS = 200


class Node:
    def __init__(
        self,
        data_dir: str,
        host: str,
        port: int,
        difficulty: int,
        miner_address: Optional[str] = None,
        subsidy: Optional[int] = None,
        fee_floor: int = 0,
        no_retarget: bool = False,
        network: str = "mainnet",
    ) -> None:
        self.network_params = NETWORKS.get(network, NETWORKS["mainnet"])
        self.chain = Blockchain(data_dir, no_retarget=no_retarget, network=network)
        self.host = host
        self.port = port
        self.difficulty = difficulty
        self.miner_address = miner_address
        self.subsidy = subsidy
        self.fee_floor = fee_floor

        self._inbox: "queue.Queue[Dict]" = queue.Queue()
        self._mine_interrupt = threading.Event()
        self._mempool: List[Dict] = []
        self._mempool_lock = threading.Lock()
        self._orphans: Dict[str, Block] = {}

        magic = self.network_params.magic
        self.server = PeerServer(
            host, port, self._enqueue,
            on_new_peer=self._on_new_inbound_peer,
            network_magic=magic,
        )
        self.client = PeerClient(
            on_message=self._enqueue,
            my_listen_port=port,
            network_magic=magic,
        )

        self._http_app: Optional[object] = None
        self._http_host = host
        self._http_port = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self.server.start()
        threading.Thread(target=self._inbox_loop, daemon=True, name="node-inbox").start()
        if self._http_app is not None:
            threading.Thread(target=self._run_http, daemon=True, name="node-http").start()
        log.info("[%s] Node started  height=%d  tip=%s", COIN_NAME, self.chain.height, self.chain.tip or "(none)")

    def connect_peer(self, host: str, port: int) -> None:
        self.client.add_peer(host, port)
        # Ask the peer for any blocks we're missing
        threading.Timer(1.5, self._request_blocks, args=(host, port)).start()

    def _on_new_inbound_peer(self, host: str, port: int) -> None:
        """Called when an inbound peer announces its listen port in HELLO.
        We add it as an outbound peer so both sides can broadcast to each other."""
        key = f"{host}:{port}"
        log.info("Bidirectional peer discovered: %s", key)
        self.connect_peer(host, port)

    # ------------------------------------------------------------------
    # IBD — initial block download
    # ------------------------------------------------------------------

    def _request_blocks(self, host: str, port: int) -> None:
        self.client.send_to(host, port, {
            "type": "GET_BLOCKS",
            "from_height": max(0, self.chain.height + 1),
            "max": MAX_BLOCKS_PER_RESP,
        })

    def _serve_blocks(self, from_height: int, max_n: int) -> List[dict]:
        result = []
        for h in range(from_height, from_height + min(max_n, MAX_BLOCKS_PER_RESP)):
            b = self.chain.get_block(h)
            if not b:
                break
            result.append(b.to_dict())
        return result

    # ------------------------------------------------------------------
    # Inbox loop
    # ------------------------------------------------------------------

    def _enqueue(self, msg: Dict) -> None:
        self._inbox.put(msg)

    def _inbox_loop(self) -> None:
        while True:
            msg = self._inbox.get()
            try:
                self._dispatch(msg)
            except Exception as e:
                log.warning("Error handling %s: %s", msg.get("type"), e)

    def _dispatch(self, msg: Dict) -> None:
        t = msg.get("type")
        if t == "NEW_TX":
            self._handle_tx(msg["tx"])
        elif t == "NEW_BLOCK":
            self._handle_block(Block.from_dict(msg["block"]), rebroadcast=True)
        elif t == "GET_BLOCKS":
            blocks = self._serve_blocks(
                int(msg.get("from_height", 0)),
                int(msg.get("max", MAX_BLOCKS_PER_RESP)),
            )
            if blocks:
                self.client.broadcast({"type": "BLOCKS", "blocks": blocks})
        elif t == "BLOCKS":
            for bd in msg.get("blocks", []):
                self._handle_block(Block.from_dict(bd), rebroadcast=False)
        elif t in ("HELLO", "PING", "PONG"):
            pass
        else:
            log.debug("Unknown message type: %s", t)

    # ------------------------------------------------------------------
    # Block handling
    # ------------------------------------------------------------------

    def _handle_block(self, block: Block, *, rebroadcast: bool) -> None:
        if self.chain.add_block(block, self.difficulty):
            log.info("Accepted block h=%d  %s", block.index, block.compute_hash()[:16])
            included = {t["txid"] for t in block.transactions}
            with self._mempool_lock:
                self._mempool = [t for t in self._mempool if t["txid"] not in included]
            self._mine_interrupt.set()
            if rebroadcast:
                self.client.broadcast({"type": "NEW_BLOCK", "block": block.to_dict()})
            self._process_orphans(block.compute_hash())
        elif block.index > self.chain.height + 1:
            # Store as orphan (parent not yet known)
            if len(self._orphans) < MAX_ORPHANS:
                self._orphans[block.prev_hash] = block

    def _process_orphans(self, new_tip: str) -> None:
        block = self._orphans.pop(new_tip, None)
        if block and self.chain.add_block(block, self.difficulty):
            log.info("Attached orphan h=%d", block.index)
            self.client.broadcast({"type": "NEW_BLOCK", "block": block.to_dict()})
            self._process_orphans(block.compute_hash())

    # ------------------------------------------------------------------
    # Transaction handling
    # ------------------------------------------------------------------

    def _handle_tx(self, tx: Dict) -> None:
        txid = tx.get("txid")
        if not txid:
            return
        with self._mempool_lock:
            if any(m.get("txid") == txid for m in self._mempool):
                return
            # Mempool size limit — evict lowest-fee tx if full (Phase 5)
            if len(self._mempool) >= MAX_MEMPOOL_SIZE:
                # Compute fees and evict lowest
                def _fee(t: Dict) -> int:
                    return t.get("_fee_cache", 0)
                self._mempool.sort(key=_fee)
                self._mempool.pop(0)

        if not validate_transaction(
            tx, self.chain.utxo,
            min_fee=self.fee_floor,
            chain_id=self.chain.chain_id,
            current_height=self.chain.height,
            coinbase_maturity=100,
        ):
            return

        # Cache fee estimate on tx dict for eviction sorting
        in_sum = sum(
            self.chain.utxo.get(i["txid"], i["index"]).value
            for i in tx.get("inputs", [])
            if self.chain.utxo.has(i["txid"], i["index"])
        )
        out_sum = sum(o["value"] for o in tx.get("outputs", []))
        tx["_fee_cache"] = max(0, in_sum - out_sum)

        with self._mempool_lock:
            if all(m.get("txid") != txid for m in self._mempool):
                self._mempool.append(tx)
        self.client.broadcast({"type": "NEW_TX", "tx": tx})

    # ------------------------------------------------------------------
    # Mining
    # ------------------------------------------------------------------

    def _coinbase_txid(self, outputs: list) -> str:
        from node.tx import sha256d_hex
        body = json.dumps(
            {"inputs": [], "outputs": outputs},
            sort_keys=True, separators=(",", ":"),
        ).encode()
        return sha256d_hex(body)

    def mine(self) -> None:
        if not self.miner_address:
            return
        self._mine_interrupt.clear()

        # Snapshot mempool
        with self._mempool_lock:
            candidates = list(self._mempool)

        snap = self.chain.utxo.snapshot()
        valid_txs: List[Dict] = []
        total_fees = 0

        for txd in candidates:
            if not validate_transaction(txd, snap, min_fee=self.fee_floor):
                continue
            in_sum = sum(
                snap.get(i["txid"], i["index"]).value
                for i in txd.get("inputs", [])
                if snap.has(i["txid"], i["index"])
            )
            out_sum = sum(o["value"] for o in txd.get("outputs", []))
            fee = in_sum - out_sum
            for inp in txd.get("inputs", []):
                snap.spend(TxInput(**inp))
            for idx, out in enumerate(txd.get("outputs", [])):
                snap.utxos[(txd["txid"], idx)] = TxOutput(**out)
            valid_txs.append(txd)
            total_fees += fee

        new_height = self.chain.height + 1 if self.chain.height >= 0 else 0
        reward = (self.subsidy if self.subsidy is not None else block_subsidy(new_height)) + total_fees
        cb_outputs = [{"value": reward, "address": self.miner_address}]
        coinbase: Dict = {
            "inputs": [],
            "outputs": cb_outputs,
            "coinbase": True,
            "txid": self._coinbase_txid(cb_outputs),
        }

        prev_hash = self.chain.tip if self.chain.height >= 0 else "0" * 64
        candidate = Block.create(
            index=new_height,
            prev_hash=prev_hash,
            transactions=[coinbase] + valid_txs,
            difficulty=self.difficulty,
        )

        try:
            mined, _ = mine_block(candidate, self.difficulty, interrupt=self._mine_interrupt)
        except RuntimeError:
            log.debug("Mining interrupted at height %d", new_height)
            return

        if self.chain.add_block(mined, self.difficulty):
            log.info("[%s] Mined block h=%d  %s", COIN_TICKER, mined.index, mined.compute_hash()[:16])
            self.client.broadcast({"type": "NEW_BLOCK", "block": mined.to_dict()})
            included = {t["txid"] for t in mined.transactions}
            with self._mempool_lock:
                self._mempool = [t for t in self._mempool if t["txid"] not in included]

    # ------------------------------------------------------------------
    # HTTP API
    # ------------------------------------------------------------------

    def enable_http(self, host: str, port: int) -> None:
        from flask import Flask, jsonify, request as req

        app = Flask("coin-node")
        app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB max POST (Phase 16)
        self._http_app = app
        self._http_host = host
        self._http_port = port

        from coin_params import to_arc, COIN_NAME, COIN_TICKER
        import time as _time
        from collections import defaultdict

        # CORS — allow browser requests from explorer
        @app.after_request
        def add_cors(response):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return response

        # Simple in-memory rate limiter for HTTP API (Phase 16)
        _http_rate: Dict[str, list] = defaultdict(list)
        _http_rate_lock = threading.Lock()

        def _check_rate(ip: str, limit: int = 60) -> bool:
            now = _time.monotonic()
            with _http_rate_lock:
                times = [t for t in _http_rate[ip] if now - t < 60]
                _http_rate[ip] = times
                if len(times) >= limit:
                    return False
                _http_rate[ip].append(now)
                return True

        @app.get("/health")
        def health():
            return jsonify({"coin": COIN_NAME, "ticker": COIN_TICKER,
                            "height": self.chain.height, "tip": self.chain.tip,
                            "peers": self.client.all_peers(self.server)})

        @app.get("/balance/<address>")
        def balance(address: str):
            bal = self.chain.get_balance(address)
            return jsonify({"address": address, "balance": bal, "balance_arc": to_arc(bal)})

        @app.get("/utxos/<address>")
        def utxos(address: str):
            result = self.chain.get_utxos_for_address(address)
            for u in result:
                u["value_arc"] = to_arc(u["value"])
            return jsonify({"address": address, "utxos": result})

        @app.get("/mempool")
        def mempool():
            with self._mempool_lock:
                return jsonify({"mempool": list(self._mempool)})

        @app.post("/tx")
        def post_tx():
            if not _check_rate(req.remote_addr or "unknown", limit=30):
                return jsonify({"error": "rate limit exceeded"}), 429
            tx = req.get_json(force=True, silent=True)
            if not tx:
                return jsonify({"error": "invalid JSON"}), 400
            txid = tx.get("txid")
            if not txid:
                return jsonify({"error": "missing txid"}), 400
            if not validate_transaction(
                tx, self.chain.utxo,
                min_fee=self.fee_floor,
                chain_id=self.chain.chain_id,
                current_height=self.chain.height,
                coinbase_maturity=100,
            ):
                return jsonify({"error": "invalid transaction"}), 422
            with self._mempool_lock:
                if all(m.get("txid") != txid for m in self._mempool):
                    self._mempool.append(tx)
            self.client.broadcast({"type": "NEW_TX", "tx": tx})
            return jsonify({"status": "accepted", "txid": txid})

        @app.get("/block/<int:height>")
        def block(height: int):
            b = self.chain.get_block(height)
            return jsonify(b.to_dict()) if b else (jsonify({"error": "not found"}), 404)

        @app.get("/tx/<txid>")
        def tx(txid: str):
            t = self.chain.get_tx(txid)
            return jsonify(t) if t else (jsonify({"error": "not found"}), 404)

    def _run_http(self) -> None:
        assert self._http_app is not None
        try:
            from waitress import serve  # type: ignore
            log.info("HTTP API on http://%s:%d (waitress)", self._http_host, self._http_port)
            serve(self._http_app, host=self._http_host, port=self._http_port, threads=4)
        except ImportError:
            log.warning("waitress not installed — using Flask dev server (not for production)")
            self._http_app.run(host=self._http_host, port=self._http_port)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser(description=f"Run a {COIN_NAME} ({COIN_TICKER}) node")
    p.add_argument("--data", default=f"./{COIN_TICKER.lower()}-data")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_P2P_PORT)
    p.add_argument("--peer", action="append", help="Seed peer host:port")
    p.add_argument("--difficulty", type=int, default=2)
    p.add_argument("--http-port", type=int, default=0)
    p.add_argument("--miner", dest="miner_address", default=None)
    p.add_argument("--subsidy", type=int, default=None,
                   help=f"Override block subsidy in base units (default: {COIN_TICKER} halving schedule)")
    p.add_argument("--fee-floor", type=int, default=0)
    p.add_argument("--mine", action="store_true")
    p.add_argument("--no-retarget", action="store_true",
                   help="Testnet mode: disable difficulty retargeting")
    p.add_argument("--network", default="mainnet",
                   choices=["mainnet", "testnet", "regtest"],
                   help="Network to connect to (default: mainnet)")
    args = p.parse_args()

    node = Node(
        args.data, args.host, args.port, args.difficulty,
        miner_address=args.miner_address,
        subsidy=args.subsidy,
        fee_floor=args.fee_floor,
        no_retarget=args.no_retarget,
        network=args.network,
    )
    if args.http_port:
        node.enable_http(args.host, args.http_port)
    node.start()

    if args.peer:
        for peer_str in args.peer:
            h, ps = peer_str.rsplit(":", 1)
            node.connect_peer(h, int(ps))

    if args.mine:
        while True:
            node.mine()
            time.sleep(0.05)
    else:
        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()
