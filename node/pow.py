from __future__ import annotations

import hashlib
import struct
import threading
from typing import Optional, Tuple

from coin_params import (
    TARGET_BLOCK_TIME, RETARGET_INTERVAL,
    MIN_RETARGET_TIMESPAN as MIN_TIMESPAN,
    MAX_RETARGET_TIMESPAN as MAX_TIMESPAN,
    MAX_TARGET,
)
from node.block import Block, bits_to_target, difficulty_to_bits, sha256d


def _target_to_bits(target: int) -> int:
    if target == 0:
        return 0
    tb = target.to_bytes(32, "big")
    for i, b in enumerate(tb):
        if b:
            exp = 32 - i
            coef = int.from_bytes(tb[i:i + 3], "big")
            if coef & 0x800000:
                coef >>= 8
                exp += 1
            return (exp << 24) | (coef & 0x007FFFFF)
    return 0


def calculate_next_bits(
    current_bits: int,
    first_timestamp: int,
    last_timestamp: int,
) -> int:
    actual = last_timestamp - first_timestamp
    actual = max(actual, MIN_TIMESPAN)
    actual = min(actual, MAX_TIMESPAN)
    current_target = bits_to_target(current_bits)
    new_target = current_target * actual // (TARGET_BLOCK_TIME * RETARGET_INTERVAL)
    new_target = min(new_target, MAX_TARGET)
    return _target_to_bits(new_target)


# ---------------------------------------------------------------------------
# Mining loop
# ---------------------------------------------------------------------------

def mine_block(
    block: Block,
    difficulty: int,
    *,
    interrupt: Optional[threading.Event] = None,
    start_nonce: int = 0,
) -> Tuple[Block, int]:
    """
    Mine a block using correct 256-bit integer target comparison.

    Performance notes:
    - The 80-byte header is kept in a bytearray; only the 4-byte nonce
      field is patched on each iteration (no JSON re-serialisation).
    - When the 32-bit nonce space is exhausted, timestamp is incremented
      (acting as extraNonce) and the header is rebuilt.
    - An interrupt threading.Event lets the caller (node) stop mining
      immediately when a new block arrives on the network.

    Raises RuntimeError if interrupted before finding a valid nonce.
    """
    bits = difficulty_to_bits(difficulty)
    target = bits_to_target(bits)
    block.bits = bits

    header_ba = bytearray(block.header_bytes())
    NONCE_OFFSET = 76   # byte offset of nonce in the 80-byte header

    nonce = start_nonce & 0xFFFFFFFF

    while True:
        if interrupt is not None and interrupt.is_set():
            raise RuntimeError("Mining interrupted — new block received")

        struct.pack_into("<I", header_ba, NONCE_OFFSET, nonce)
        hash_int = int.from_bytes(
            hashlib.sha256(hashlib.sha256(header_ba).digest()).digest(),
            "big",
        )

        if hash_int <= target:
            block.nonce = nonce
            return block, nonce

        nonce = (nonce + 1) & 0xFFFFFFFF
        if nonce == 0:
            # Nonce wrapped — increment timestamp as extraNonce
            block.timestamp += 1
            header_ba = bytearray(block.header_bytes())


def meets_target(block: Block) -> bool:
    return block.meets_target()
