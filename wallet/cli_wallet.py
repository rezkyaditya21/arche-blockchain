from __future__ import annotations

"""
Production wallet CLI.

Fixes vs. educational version:
- --password flag for encrypted wallet files (AES-256-GCM + scrypt).
- --fee argument for explicit fee control.
- Base58 recipient address correctly decoded before sending.
- Address validation before constructing transaction.
- Confirmation polling after send (GET /tx/<txid> until found or timeout).
- load_wallet / save_wallet pass password through properly.
- Full BIP39 mnemonic generation and validation.
"""

import argparse
import json
import os
import sys
import time

import requests

from wallet.wallet import (
    KeyPair,
    default_wallet_path,
    save_wallet,
    load_wallet,
    address_hex_to_base58,
    address_base58_to_hex,
    generate_mnemonic,
    validate_mnemonic,
)
from node.tx import create_signed_tx, pubkey_to_address


# ---------------------------------------------------------------------------
# Address validation
# ---------------------------------------------------------------------------

def _validate_address_hex(addr: str) -> bool:
    """Check that addr is a 40-char hex string (20-byte P2PKH hash)."""
    if len(addr) != 40:
        return False
    try:
        bytes.fromhex(addr)
        return True
    except ValueError:
        return False


def _resolve_address(addr: str, is_base58: bool) -> str:
    """Convert address to hex form; raise if invalid."""
    if is_base58:
        try:
            addr = address_base58_to_hex(addr)
        except Exception as e:
            print(f"Invalid Base58Check address: {e}", file=sys.stderr)
            sys.exit(2)
    if not _validate_address_hex(addr):
        print(f"Invalid address (expected 40-char hex / 20 bytes): {addr!r}", file=sys.stderr)
        sys.exit(2)
    return addr


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_create(args: argparse.Namespace) -> None:
    if args.seed:
        if not validate_mnemonic(args.seed):
            print("Warning: provided seed phrase fails BIP39 checksum validation.", file=sys.stderr)
        keypair = KeyPair.from_mnemonic(args.seed, index=args.index)
        mnemonic = args.seed
    else:
        mnemonic = generate_mnemonic(128)
        keypair = KeyPair.from_mnemonic(mnemonic, index=args.index)

    path = args.out or default_wallet_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    save_wallet(path, keypair, mnemonic=mnemonic, password=args.password or None)

    out: dict = {
        "wallet_file": path,
        "address_hex": keypair.address,
        "mnemonic": mnemonic,
        "encrypted": bool(args.password),
    }
    if args.base58:
        out["address_base58"] = address_hex_to_base58(keypair.address)
    print(json.dumps(out, indent=2))


def cmd_recover(args: argparse.Namespace) -> None:
    if not args.seed:
        print("--seed is required for recovery", file=sys.stderr)
        sys.exit(2)
    if not validate_mnemonic(args.seed):
        print("Warning: seed phrase fails BIP39 checksum validation.", file=sys.stderr)

    keypair = KeyPair.from_mnemonic(args.seed, index=args.index)
    path = args.out or default_wallet_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    save_wallet(path, keypair, mnemonic=args.seed, password=args.password or None)

    out: dict = {
        "wallet_file": path,
        "address_hex": keypair.address,
        "encrypted": bool(args.password),
    }
    if args.base58:
        out["address_base58"] = address_hex_to_base58(keypair.address)
    print(json.dumps(out, indent=2))


def cmd_balance(args: argparse.Namespace) -> None:
    addr = _resolve_address(args.address, args.base58)
    r = requests.get(f"{args.rpc}/balance/{addr}", timeout=10)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))


def cmd_send(args: argparse.Namespace) -> None:
    if not args.wallet:
        print("--wallet is required", file=sys.stderr)
        sys.exit(2)

    kp = load_wallet(args.wallet, password=args.password or None)

    # Resolve sender address (always hex internally)
    sender_hex = kp.address

    # Resolve recipient address — decode Base58 if needed
    to_hex = _resolve_address(args.to, args.base58)

    fee = int(args.fee)
    amount = int(args.amount)

    if amount <= 0:
        print("Amount must be positive", file=sys.stderr)
        sys.exit(2)

    # Fetch UTXOs
    r = requests.get(f"{args.rpc}/utxos/{sender_hex}", timeout=10)
    r.raise_for_status()
    entries = r.json().get("utxos", [])
    if not entries:
        print("No UTXOs found for address", file=sys.stderr)
        sys.exit(1)

    utxos = [(e["txid"], e["index"], e["value"], e["address"]) for e in entries]

    try:
        tx = create_signed_tx(
            kp.private_key_hex,
            utxos,
            to_hex,
            amount,
            sender_hex,   # change back to sender
            fee=fee,
        )
    except ValueError as e:
        print(f"Error building transaction: {e}", file=sys.stderr)
        sys.exit(1)

    payload = tx.to_dict()

    # Submit via HTTP POST /tx
    try:
        resp = requests.post(f"{args.rpc}/tx", json=payload, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to submit transaction via HTTP: {e}", file=sys.stderr)
        sys.exit(1)

    txid = payload["txid"]
    print(json.dumps({"status": "submitted", "txid": txid}, indent=2))

    # Confirmation polling
    if args.wait:
        print(f"Waiting for confirmation (up to {args.wait}s)…", file=sys.stderr)
        deadline = time.time() + args.wait
        while time.time() < deadline:
            try:
                cr = requests.get(f"{args.rpc}/tx/{txid}", timeout=5)
                if cr.status_code == 200:
                    print(json.dumps({"status": "confirmed", "txid": txid}, indent=2))
                    return
            except Exception:
                pass
            time.sleep(3)
        print(json.dumps({"status": "pending", "txid": txid,
                          "note": "not yet mined within wait window"}, indent=2))


def cmd_info(args: argparse.Namespace) -> None:
    """Show public info for a wallet file (no private key exposed)."""
    if not args.wallet:
        print("--wallet is required", file=sys.stderr)
        sys.exit(2)
    with open(args.wallet, "r") as f:
        data = json.load(f)
    out = {
        "address_hex": data.get("address"),
        "public_key": data.get("public_key"),
        "encrypted": data.get("encrypted", False),
    }
    if args.base58 and data.get("address"):
        out["address_base58"] = address_hex_to_base58(data["address"])
    print(json.dumps(out, indent=2))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wallet", description="Coin wallet CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # create
    pc = sub.add_parser("create", help="Generate new wallet")
    pc.add_argument("--out", help="Output wallet file path")
    pc.add_argument("--base58", action="store_true")
    pc.add_argument("--seed", help="Use existing mnemonic for deterministic generation")
    pc.add_argument("--index", type=int, default=0, help="Derivation index")
    pc.add_argument("--password", help="Encrypt wallet with this passphrase")
    pc.set_defaults(func=cmd_create)

    # recover
    pr = sub.add_parser("recover", help="Recover wallet from mnemonic")
    pr.add_argument("--seed", required=True, help="BIP39 mnemonic phrase")
    pr.add_argument("--out", help="Output wallet file path")
    pr.add_argument("--base58", action="store_true")
    pr.add_argument("--index", type=int, default=0)
    pr.add_argument("--password", help="Encrypt recovered wallet")
    pr.set_defaults(func=cmd_recover)

    # balance
    pb = sub.add_parser("balance", help="Check address balance")
    pb.add_argument("address", help="Address (hex or base58 with --base58)")
    pb.add_argument("--rpc", default="http://127.0.0.1:9081")
    pb.add_argument("--base58", action="store_true")
    pb.set_defaults(func=cmd_balance)

    # send
    ps = sub.add_parser("send", help="Send coins to address")
    ps.add_argument("to", help="Recipient address")
    ps.add_argument("amount", help="Amount in satoshis")
    ps.add_argument("--wallet", required=True, help="Path to wallet file")
    ps.add_argument("--rpc", default="http://127.0.0.1:9081")
    ps.add_argument("--base58", action="store_true", help="Addresses are Base58Check")
    ps.add_argument("--fee", type=int, default=0, help="Transaction fee in satoshis")
    ps.add_argument("--password", help="Wallet decryption passphrase")
    ps.add_argument("--wait", type=int, default=0, metavar="SECONDS",
                    help="Poll for confirmation up to SECONDS (0 = no wait)")
    ps.set_defaults(func=cmd_send)

    # info
    pi = sub.add_parser("info", help="Show wallet public info")
    pi.add_argument("--wallet", required=True)
    pi.add_argument("--base58", action="store_true")
    pi.set_defaults(func=cmd_info)

    return p


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
