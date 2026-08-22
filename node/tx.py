from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def sha256d_hex(data: bytes) -> str:
    return sha256d(data).hex()


def _ripemd160(data: bytes) -> bytes:
    try:
        h = hashlib.new("ripemd160")
        h.update(data)
        return h.digest()
    except ValueError:
        raise RuntimeError(
            "RIPEMD160 unavailable on this platform. "
            "Install OpenSSL with legacy algorithms or use a compatible Python build."
        )


def pubkey_to_address(pubkey_bytes: bytes) -> str:
    """P2PKH: RIPEMD160(SHA256(pubkey)) as 20-byte hex."""
    return _ripemd160(hashlib.sha256(pubkey_bytes).digest()).hex()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TxInput:
    txid: str
    index: int
    signature: str   # DER hex; empty string when unsigned
    pubkey: str      # 33-byte compressed pubkey hex


@dataclass
class TxOutput:
    value: int       # smallest denomination (base units)
    address: str     # 20-byte P2PKH hash hex


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------

@dataclass
class Transaction:
    inputs: List[TxInput]
    outputs: List[TxOutput]

    def _unsigned_body(self, chain_id: int = 1) -> bytes:
        """
        Canonical serialisation WITHOUT signatures.
        Includes chain_id for replay protection (Phase 11).
        Different chain_id → different signing hash → cross-network replay impossible.
        """
        body = {
            "chain_id": chain_id,
            "inputs": [
                {"txid": i.txid, "index": i.index, "pubkey": i.pubkey}
                for i in self.inputs
            ],
            "outputs": [asdict(o) for o in self.outputs],
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()

    @property
    def txid(self) -> str:
        """double-SHA256 of the unsigned body with chain_id=1 (mainnet).
        txid is stable: does not include signatures."""
        return sha256d_hex(self._unsigned_body(chain_id=1))

    def signing_hash(self, chain_id: int = 1) -> bytes:
        """32-byte hash each input signature covers. Includes chain_id."""
        return sha256d(self._unsigned_body(chain_id=chain_id))

    def to_dict(self) -> dict:
        return {
            "txid": self.txid,
            "inputs": [asdict(i) for i in self.inputs],
            "outputs": [asdict(o) for o in self.outputs],
        }


# ---------------------------------------------------------------------------
# UTXO set
# ---------------------------------------------------------------------------

class UTXOSet:
    def __init__(self) -> None:
        self.utxos: Dict[Tuple[str, int], TxOutput] = {}
        # Track which txids are coinbase outputs and at what height they were mined
        self.coinbase_heights: Dict[str, int] = {}

    def add_tx(self, tx: Transaction) -> None:
        for i, out in enumerate(tx.outputs):
            self.utxos[(tx.txid, i)] = out

    def add_coinbase(self, txid: str, outputs: List[TxOutput], height: int) -> None:
        """Add coinbase outputs, recording their maturity height."""
        for i, out in enumerate(outputs):
            self.utxos[(txid, i)] = out
        self.coinbase_heights[txid] = height

    def spend(self, txin: TxInput) -> None:
        self.utxos.pop((txin.txid, txin.index), None)

    def has(self, txid: str, index: int) -> bool:
        return (txid, index) in self.utxos

    def get(self, txid: str, index: int) -> TxOutput:
        return self.utxos[(txid, index)]

    def is_coinbase(self, txid: str) -> bool:
        return txid in self.coinbase_heights

    def coinbase_height(self, txid: str) -> Optional[int]:
        return self.coinbase_heights.get(txid)

    def balance(self, address: str) -> int:
        return sum(o.value for o in self.utxos.values() if o.address == address)

    def snapshot(self) -> "UTXOSet":
        """Deep copy for block-building without mutating the live set."""
        c = UTXOSet()
        c.utxos = dict(self.utxos)
        c.coinbase_heights = dict(self.coinbase_heights)
        return c


# ---------------------------------------------------------------------------
# Transaction creation (uses coincurve — libsecp256k1)
# ---------------------------------------------------------------------------

def create_signed_tx(
    sender_privkey_hex: str,
    utxos: List[Tuple[str, int, int, str]],  # (txid, index, value, address)
    to_addr: str,
    amount: int,
    change_addr: str,
    fee: int = 0,
    chain_id: int = 1,
) -> Transaction:
    """
    Build and sign a transaction with replay protection via chain_id.

    Parameters
    ----------
    sender_privkey_hex : 32-byte private key as hex
    utxos              : sender's available UTXOs
    to_addr            : recipient address (20-byte hex)
    amount             : value to send (does not include fee)
    change_addr        : address to receive leftover coins
    fee                : explicit fee deducted from change
    chain_id           : network chain identifier (1=mainnet, 2=testnet, 3=regtest)
    """
    import coincurve  # type: ignore

    sk = coincurve.PrivateKey(bytes.fromhex(sender_privkey_hex))
    pubkey_bytes = sk.public_key.format(compressed=True)
    pubkey_hex = pubkey_bytes.hex()

    inputs: List[TxInput] = []
    total = 0
    for (utxo_txid, utxo_index, utxo_value, _) in utxos:
        inputs.append(TxInput(txid=utxo_txid, index=utxo_index, signature="", pubkey=pubkey_hex))
        total += utxo_value
        if total >= amount + fee:
            break

    if total < amount + fee:
        raise ValueError(f"Insufficient funds: have {total}, need {amount + fee}")

    outputs: List[TxOutput] = [TxOutput(value=amount, address=to_addr)]
    change = total - amount - fee
    if change > 0:
        outputs.append(TxOutput(value=change, address=change_addr))

    tx = Transaction(inputs=inputs, outputs=outputs)
    sig_hash = tx.signing_hash(chain_id=chain_id)

    signed_inputs: List[TxInput] = []
    for tin in tx.inputs:
        sig = sk.sign(sig_hash, hasher=None)   # deterministic RFC-6979
        signed_inputs.append(TxInput(txid=tin.txid, index=tin.index,
                                     signature=sig.hex(), pubkey=pubkey_hex))
    tx.inputs = signed_inputs
    return tx


# ---------------------------------------------------------------------------
# Transaction validation
# ---------------------------------------------------------------------------

def validate_transaction(
    tx: "Transaction | dict",
    utxo: UTXOSet,
    *,
    min_fee: int = 0,
    chain_id: int = 1,
    coinbase_heights: Optional[Dict[str, int]] = None,
    current_height: int = 0,
    coinbase_maturity: int = 0,   # 0 = disabled (use coin_params.COINBASE_MATURITY when > 0)
) -> bool:
    """
    Validate a non-coinbase transaction.

    Checks:
    - All UTXOs exist in the set
    - Coinbase maturity respected (if coinbase_maturity > 0)
    - No intra-tx double-spend
    - Signatures valid (coincurve / libsecp256k1)
    - pubkey hashes to UTXO address (P2PKH)
    - Output sum <= input sum (no inflation)
    - Fee >= min_fee
    - All output values >= 0
    - Input/output counts within limits
    - Chain_id included in signing domain
    """
    import coincurve  # type: ignore
    from coin_params import MAX_TX_INPUTS, MAX_TX_OUTPUTS, COINBASE_MATURITY as DEFAULT_MATURITY

    # Normalise to lists of objects
    if isinstance(tx, dict):
        inputs_raw = tx.get("inputs", [])
        outputs_raw = tx.get("outputs", [])
    else:
        inputs_raw = tx.inputs
        outputs_raw = tx.outputs

    inputs: List[TxInput] = [
        i if isinstance(i, TxInput) else TxInput(**i) for i in inputs_raw
    ]
    outputs: List[TxOutput] = [
        o if isinstance(o, TxOutput) else TxOutput(**o) for o in outputs_raw
    ]

    # Basic structural checks
    if not inputs or not outputs:
        return False

    # Resource limits (Phase 12)
    if len(inputs) > MAX_TX_INPUTS:
        return False
    if len(outputs) > MAX_TX_OUTPUTS:
        return False

    # All output values non-negative
    if any(o.value < 0 for o in outputs):
        return False

    # Reconstruct unsigned body for sig verification
    tmp = Transaction(
        inputs=[TxInput(i.txid, i.index, "", i.pubkey) for i in inputs],
        outputs=outputs,
    )
    sig_hash = tmp.signing_hash(chain_id=chain_id)

    input_sum = 0
    seen: Set[Tuple[str, int]] = set()

    # Effective coinbase heights: use parameter or fall back to utxo.coinbase_heights
    effective_cb_heights = coinbase_heights if coinbase_heights is not None else utxo.coinbase_heights
    # coinbase_maturity=-1 means disabled; 0 means use DEFAULT_MATURITY; >0 means use provided value
    if coinbase_maturity < 0:
        effective_maturity = 0   # disabled
    elif coinbase_maturity == 0:
        effective_maturity = DEFAULT_MATURITY
    else:
        effective_maturity = coinbase_maturity

    for tin in inputs:
        key = (tin.txid, tin.index)
        if key in seen:
            return False   # intra-tx double spend
        seen.add(key)

        if not utxo.has(tin.txid, tin.index):
            return False

        out = utxo.get(tin.txid, tin.index)
        input_sum += out.value

        # Coinbase maturity check (Phase 3)
        if tin.txid in effective_cb_heights:
            cb_h = effective_cb_heights[tin.txid]
            if current_height - cb_h < effective_maturity:
                return False

        # Signature verification via libsecp256k1
        try:
            pk = coincurve.PublicKey(bytes.fromhex(tin.pubkey))
            if not pk.verify(bytes.fromhex(tin.signature), sig_hash, hasher=None):
                return False
        except Exception:
            return False

        # P2PKH: pubkey must hash to the locked address
        if pubkey_to_address(bytes.fromhex(tin.pubkey)) != out.address:
            return False

    output_sum = sum(o.value for o in outputs)
    if output_sum > input_sum:
        return False

    if (input_sum - output_sum) < min_fee:
        return False

    return True
