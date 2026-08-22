from __future__ import annotations

import hashlib
import json
import struct
import time
from dataclasses import dataclass
from typing import List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BLOCK_VERSION = 1
GENESIS_PREV_HASH = "0" * 64
MAX_FUTURE_SECONDS = 7200   # 2 hours clock drift tolerance


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha256d(data: bytes) -> bytes:
    """Double SHA-256 (used everywhere Bitcoin uses SHA256d)."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def sha256d_hex(data: bytes) -> str:
    return sha256d(data).hex()


# ---------------------------------------------------------------------------
# Compact target (nBits) encoding — identical to Bitcoin
# ---------------------------------------------------------------------------

def difficulty_to_bits(difficulty: int) -> int:
    """
    Convert leading-nibble difficulty (0-63) to compact nBits.
    difficulty=0  → absolute easiest: 0x200FFFFF (max target, any hash passes)
    difficulty=N  → first N hex nibbles must be 0
    """
    if difficulty == 0:
        return 0x200FFFFF   # absolute easiest — any hash passes
    max_target = (1 << 256) - 1
    target = max_target >> (difficulty * 4)
    return _target_to_bits(target)


def _target_to_bits(target: int) -> int:
    if target == 0:
        return 0
    target_bytes = target.to_bytes(32, "big")
    for i, b in enumerate(target_bytes):
        if b != 0:
            exponent = 32 - i
            coeff_bytes = target_bytes[i:i + 3]
            coefficient = int.from_bytes(coeff_bytes, "big")
            if coefficient & 0x800000:
                coefficient >>= 8
                exponent += 1
            return (exponent << 24) | (coefficient & 0x007FFFFF)
    return 0


def bits_to_target(bits: int) -> int:
    """Decode compact nBits to 256-bit integer target."""
    exponent = (bits >> 24) & 0xFF
    coefficient = bits & 0x007FFFFF
    if exponent <= 3:
        return coefficient >> (8 * (3 - exponent))
    return coefficient << (8 * (exponent - 3))


# ---------------------------------------------------------------------------
# Merkle tree
# ---------------------------------------------------------------------------

def merkle_root(txids: List[str]) -> str:
    """Merkle root using double-SHA256 over txid pairs (Bitcoin-compatible)."""
    if not txids:
        return sha256d_hex(b"")
    layer: List[bytes] = [bytes.fromhex(x) for x in txids]
    while len(layer) > 1:
        next_layer: List[bytes] = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else left
            next_layer.append(sha256d(left + right))
        layer = next_layer
    return layer[0].hex()


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------

@dataclass
class Block:
    version: int
    index: int
    prev_hash: str
    timestamp: int
    bits: int           # compact target (nBits)
    nonce: int
    tx_merkle_root: str
    transactions: List[dict]

    # ------------------------------------------------------------------
    # 80-byte canonical binary header (struct layout = Bitcoin's)
    # version(4LE) | prev_hash(32) | merkle(32) | timestamp(4LE) | bits(4LE) | nonce(4LE)
    # ------------------------------------------------------------------

    def header_bytes(self) -> bytes:
        return struct.pack(
            "<I32s32sIII",
            self.version,
            bytes.fromhex(self.prev_hash),
            bytes.fromhex(self.tx_merkle_root),
            self.timestamp,
            self.bits,
            self.nonce,
        )

    def compute_hash(self) -> str:
        return sha256d_hex(self.header_bytes())

    def meets_target(self) -> bool:
        """PoW check: hash as 256-bit int must be <= compact target."""
        target = bits_to_target(self.bits)
        return int.from_bytes(sha256d(self.header_bytes()), "big") <= target

    def validate_timestamp(self, median_time_past: int, now: Optional[int] = None) -> bool:
        if now is None:
            now = int(time.time())
        # MTP=0 means no history — only check future drift
        # Block timestamp must be >= MTP (not strictly greater, to handle same-second mining)
        if median_time_past > 0 and self.timestamp < median_time_past:
            return False
        if self.timestamp > now + MAX_FUTURE_SECONDS:
            return False
        return True

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def create(
        index: int,
        prev_hash: str,
        transactions: List[dict],
        difficulty: int = 1,
        nonce: int = 0,
        version: int = BLOCK_VERSION,
    ) -> "Block":
        ts = int(time.time())
        txids = [t["txid"] for t in transactions]
        root = merkle_root(txids)
        bits = difficulty_to_bits(difficulty)
        return Block(
            version=version,
            index=index,
            prev_hash=prev_hash,
            timestamp=ts,
            bits=bits,
            nonce=nonce,
            tx_merkle_root=root,
            transactions=transactions,
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "index": self.index,
            "prev_hash": self.prev_hash,
            "timestamp": self.timestamp,
            "bits": self.bits,
            "nonce": self.nonce,
            "tx_merkle_root": self.tx_merkle_root,
            "transactions": self.transactions,
        }

    @staticmethod
    def from_dict(d: dict) -> "Block":
        return Block(
            version=d.get("version", BLOCK_VERSION),
            index=d["index"],
            prev_hash=d["prev_hash"],
            timestamp=d["timestamp"],
            bits=d.get("bits", difficulty_to_bits(1)),
            nonce=d["nonce"],
            tx_merkle_root=d["tx_merkle_root"],
            transactions=d["transactions"],
        )
