from __future__ import annotations

"""
Production HTTP explorer.

Fixes vs. educational version:
- Uses chain's persisted UTXO set — no O(height × tx) chain replay.
- /tx/<txid> uses the O(1) tx index in chain.get_tx().
- /chain supports ?page=N&per_page=M pagination (default 50 blocks/page).
- POST /tx validates and forwards to the node's mempool via the node ref or
  falls back to direct chain validation.
- /mempool returns the real in-memory mempool when node ref is provided.
- Served via Waitress (production WSGI) when available.
"""

import argparse
import json
import logging
import os
from typing import Any, Optional

from flask import Flask, jsonify, request

from node.chain import Blockchain
from node.tx import validate_transaction
from coin_params import COIN_NAME, COIN_TICKER, COIN, MAX_SUPPLY, INITIAL_SUBSIDY, block_subsidy, to_arc

log = logging.getLogger(__name__)


def create_app(data_dir: str, node: Optional[Any] = None) -> Flask:
    """
    Create the explorer Flask app.

    Parameters
    ----------
    data_dir : path to the chain data directory (read-only view of the chain).
    node     : optional running Node instance for mempool access and tx forwarding.
               If None, mempool endpoints return empty and POST /tx validates
               against the local chain view only (no gossip forwarding).
    """
    app = Flask(f"{COIN_NAME}-explorer",
                static_folder=os.path.join(os.path.dirname(__file__), "..", "explorer"),
                static_url_path="/ui")
    # Enable CORS so browser can call API from file:// or different port
    @app.after_request
    def add_cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    @app.get("/")
    def serve_ui():
        return app.send_static_file("index.html")
    def get_chain() -> Blockchain:
        return Blockchain(data_dir, readonly=True)

    # ------------------------------------------------------------------
    # Coin info
    # ------------------------------------------------------------------

    @app.get("/info")
    def coin_info():
        chain = get_chain()
        current_subsidy = block_subsidy(chain.height + 1) if chain.height >= 0 else INITIAL_SUBSIDY
        return jsonify({
            "coin": COIN_NAME,
            "ticker": COIN_TICKER,
            "height": chain.height,
            "tip": chain.tip,
            "block_reward_arc": to_arc(current_subsidy),
            "max_supply_arc": to_arc(MAX_SUPPLY),
            "base_unit": f"1 {COIN_TICKER} = {COIN} base units",
        })

    # ------------------------------------------------------------------
    # Chain endpoints
    # ------------------------------------------------------------------

    @app.get("/chain")
    def get_chain_route():
        chain = get_chain()
        per_page = min(int(request.args.get("per_page", 50)), 500)
        page = max(int(request.args.get("page", 0)), 0)
        start = page * per_page
        end = start + per_page
        blocks = []
        for h in range(start, min(end, chain.height + 1)):
            b = chain.get_block(h)
            if b:
                d = b.to_dict()
                d.pop("transactions", None)
                d["hash"] = b.compute_hash()
                d["tx_count"] = len(b.transactions)
                blocks.append(d)
        return jsonify({
            "height": chain.height,
            "tip": chain.tip,
            "page": page,
            "per_page": per_page,
            "blocks": blocks,
        })

    @app.get("/block/<int:height>")
    def get_block(height: int):
        chain = get_chain()
        b = chain.get_block(height)
        if not b:
            return jsonify({"error": "not found"}), 404
        d = b.to_dict()
        d["hash"] = b.compute_hash()
        return jsonify(d)

    @app.get("/block/hash/<block_hash>")
    def get_block_by_hash(block_hash: str):
        chain = get_chain()
        b = chain.get_block_by_hash(block_hash)
        if not b:
            return jsonify({"error": "not found"}), 404
        d = b.to_dict()
        d["hash"] = b.compute_hash()
        return jsonify(d)

    @app.get("/tx/<txid>")
    def get_tx(txid: str):
        chain = get_chain()
        tx = chain.get_tx(txid)
        if tx is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(tx)

    @app.post("/tx")
    def post_tx():
        chain = get_chain()
        tx = request.get_json(force=True)
        if not tx or not tx.get("txid"):
            return jsonify({"error": "missing txid"}), 400
        if not validate_transaction(tx, chain.utxo):
            return jsonify({"error": "invalid transaction"}), 422
        if node is not None:
            txid = tx.get("txid")
            with node._mempool_lock:
                if all(m.get("txid") != txid for m in node._mempool):
                    node._mempool.append(tx)
            node.client.broadcast({"type": "NEW_TX", "tx": tx})
            return jsonify({"status": "accepted", "txid": txid})
        else:
            return jsonify({"status": "validated", "txid": tx.get("txid"),
                            "note": "no live node; tx not broadcast"})

    @app.get("/balance/<address>")
    def get_balance(address: str):
        chain = get_chain()
        bal = chain.get_balance(address)
        return jsonify({"address": address, "balance": bal, "balance_arc": to_arc(bal)})

    @app.get("/utxos/<address>")
    def get_utxos(address: str):
        chain = get_chain()
        utxos = chain.get_utxos_for_address(address)
        for u in utxos:
            u["value_arc"] = to_arc(u["value"])
        return jsonify({"address": address, "utxos": utxos})

    @app.get("/mempool")
    def get_mempool():
        if node is not None:
            with node._mempool_lock:
                mempool = list(node._mempool)
        else:
            mempool = []
        return jsonify({"mempool": mempool, "count": len(mempool)})

    @app.get("/health")
    def health():
        chain = get_chain()
        return jsonify({
            "coin": COIN_NAME,
            "ticker": COIN_TICKER,
            "height": chain.height,
            "tip": chain.tip,
        })

    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description=f"{COIN_NAME} ({COIN_TICKER}) explorer HTTP server")
    parser.add_argument("--data", default=f"./{COIN_TICKER.lower()}-data", help="Chain data directory")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    app = create_app(args.data)

    try:
        from waitress import serve  # type: ignore
        log.info("ARCHE Explorer on http://%s:%d (waitress)", args.host, args.port)
        serve(app, host=args.host, port=args.port, threads=4)
    except ImportError:
        log.warning("waitress not installed — using Flask dev server")
        app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
