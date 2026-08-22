from __future__ import annotations

"""
Genesis block generator.

Production improvements:
- Genesis block is mined with real PoW (configurable difficulty).
- After creation, the genesis hash is printed and can be hardcoded as
  EXPECTED_GENESIS_HASH in chain.py for tamper detection.
- On subsequent runs, the stored genesis hash is verified against the
  on-disk block — a mismatch aborts startup rather than silently accepting
  a tampered chain.
- Coinbase txid computed via the same double-SHA256 / unsigned-body path
  as Transaction.txid in tx.py (no ad-hoc inline code).
"""

import argparse
import json
import sys

from coin_params import COIN_NAME, COIN_TICKER, INITIAL_SUBSIDY
from node.block import Block
from node.chain import Blockchain
from node.pow import mine_block
from node.tx import sha256d_hex


# ---------------------------------------------------------------------------
# Hardcoded genesis hash — set this after first run for tamper detection.
# Leave as None during initial setup; the script will print the value to set.
# ---------------------------------------------------------------------------
EXPECTED_GENESIS_HASH: str | None = "0ddfa0b4573e8765d6b6b71b1a6b9a6cc6a2349b2b2b27356405d8c001a48694"


def make_coinbase_txid(outputs: list) -> str:
    """Stable txid = double-SHA256 of unsigned body (matches Transaction.txid)."""
    import json as _json
    body = _json.dumps(
        {"inputs": [], "outputs": outputs},
        sort_keys=True, separators=(",", ":"),
    ).encode()
    return sha256d_hex(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Create or verify the {COIN_NAME} genesis block")
    parser.add_argument("--data", default=f"./{COIN_TICKER.lower()}-data", help="Chain data directory")
    parser.add_argument("--address", required=True, help="Address to receive genesis reward")
    parser.add_argument("--amount", type=int, default=INITIAL_SUBSIDY,
                        help=f"Genesis coinbase reward in base units (default: {INITIAL_SUBSIDY} = 50 {COIN_TICKER})")
    parser.add_argument("--difficulty", type=int, default=2,
                        help="PoW difficulty for genesis block (default: 2)")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only verify existing genesis, do not create")
    args = parser.parse_args()

    chain = Blockchain(args.data)

    # ------------------------------------------------------------------
    # Verify existing genesis if chain already exists
    # ------------------------------------------------------------------
    if chain.height >= 0:
        genesis = chain.get_block(0)
        if genesis is None:
            print(json.dumps({"error": "chain exists but genesis block missing"}))
            sys.exit(1)
        actual_hash = genesis.compute_hash()
        if EXPECTED_GENESIS_HASH and actual_hash != EXPECTED_GENESIS_HASH:
            print(json.dumps({
                "error": "GENESIS HASH MISMATCH — possible chain tampering",
                "expected": EXPECTED_GENESIS_HASH,
                "actual": actual_hash,
            }))
            sys.exit(1)
        print(json.dumps({
            "status": "exists",
            "height": chain.height,
            "genesis_hash": actual_hash,
        }, indent=2))
        return

    if args.verify_only:
        print(json.dumps({"status": "no_chain", "message": "chain does not exist yet"}))
        return

    # ------------------------------------------------------------------
    # Create genesis block
    # ------------------------------------------------------------------
    cb_outputs = [{"value": args.amount, "address": args.address}]
    coinbase = {
        "inputs": [],
        "outputs": cb_outputs,
        "coinbase": True,
        "txid": make_coinbase_txid(cb_outputs),
    }

    # Mine the genesis block with real PoW
    print(f"Mining genesis block at difficulty={args.difficulty} …", flush=True)
    genesis = Block.create(
        index=0,
        prev_hash="0" * 64,
        transactions=[coinbase],
        difficulty=args.difficulty,
    )
    genesis, nonce = mine_block(genesis, args.difficulty)
    genesis_hash = genesis.compute_hash()

    # Commit directly via _commit to bypass validate_block's expected_bits check
    # (genesis is a special case — we accept whatever we mined)
    chain._commit(genesis)

    print(json.dumps({
        "status": "created",
        "genesis_hash": genesis_hash,
        "nonce": nonce,
        "height": chain.height,
        "note": (
            f"Set EXPECTED_GENESIS_HASH = \"{genesis_hash}\" "
            "in scripts/genesis.py to enable tamper detection."
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
