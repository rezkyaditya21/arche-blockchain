# ARCHE Consensus Specification v1.0

This document defines the ARCHE consensus rules with sufficient detail for an
independent node implementation to be fully compatible.

---

## 1. Block Format

Each block header is serialized as **80 bytes** (identical layout to Bitcoin):

| Field          | Size | Type        | Description                          |
|----------------|------|-------------|--------------------------------------|
| version        | 4    | uint32 LE   | Block version (currently 1)          |
| prev_hash      | 32   | bytes       | Double-SHA256 of previous block header |
| merkle_root    | 32   | bytes       | Merkle root of transaction txids      |
| timestamp      | 4    | uint32 LE   | Unix timestamp (seconds)              |
| bits           | 4    | uint32 LE   | Compact target (nBits)                |
| nonce          | 4    | uint32 LE   | Mining nonce                          |

Block hash = `double_SHA256(header_bytes)`.

---

## 2. Transaction Format

Transactions are JSON-serialized with these fields:

```json
{
  "txid": "<64-char hex>",
  "inputs":  [ { "txid": "...", "index": N, "signature": "...", "pubkey": "..." } ],
  "outputs": [ { "value": N, "address": "<40-char hex>" } ]
}
```

**txid** = `double_SHA256(unsigned_body)` where `unsigned_body` is:

```json
{ "chain_id": 1, "inputs": [{ "txid": "...", "index": N, "pubkey": "..." }], "outputs": [...] }
```

Signatures cover the same `unsigned_body`. Signatures are NOT included in txid
computation — this prevents transaction malleability.

---

## 3. Hashing

All hashing uses **double-SHA256**: `SHA256(SHA256(data))`.

Merkle tree:
- Each leaf = raw bytes of txid (32 bytes).
- Each internal node = `double_SHA256(left_child || right_child)`.
- Odd number of leaves: duplicate the last leaf.

---

## 4. Proof of Work

The **compact target** (nBits) encoding:
- Top byte = exponent `e`
- Lower 3 bytes = coefficient `c`
- `target = c * 2^(8*(e-3))`

A block is valid if: `int.from_bytes(block_hash, "big") <= target`

---

## 5. Difficulty Retarget

Retarget occurs every **2016 blocks**.

```
actual_timespan = last_block.timestamp - first_block.timestamp
actual_timespan = clamp(actual_timespan, 120*2016/4, 120*2016*4)
new_target = current_target * actual_timespan / (120 * 2016)
new_target = min(new_target, MAX_TARGET)
```

`MAX_TARGET = 2^256 - 1` (absolute easiest).

In **testnet** mode (`--no-retarget`): difficulty never changes, always inherits parent bits.

---

## 6. Timestamp Rules

- Block timestamp must be **>= Median Time Past** (median of last 11 blocks).
- Block timestamp must be **<= wall_clock + 7200 seconds** (2 hours).
- Genesis block skips MTP check.

---

## 7. Block Subsidy & Halving

```
INITIAL_SUBSIDY = 50 ARC = 5_000_000_000 base units
HALVING_INTERVAL = 500_000 blocks
subsidy(height) = INITIAL_SUBSIDY >> (height // HALVING_INTERVAL)
```

After 64 halvings: subsidy = 0. Total supply converges to ~50,000,000 ARC.

---

## 8. Fees

```
fee = sum(input_values) - sum(output_values)
fee >= 0  (required)
```

Coinbase constraint:
```
coinbase_output_total <= subsidy(height) + sum(fees_in_block)
```

---

## 9. Coinbase Maturity

Coinbase outputs **cannot be spent** until:
```
current_height - coinbase_block_height >= COINBASE_MATURITY (100)
```

---

## 10. UTXO Rules

- Each output is identified by `(txid, output_index)`.
- An output can only be spent once.
- Spending a non-existent output is invalid.
- Outputs must have `value >= 0`.

---

## 11. Transaction Validity

A non-coinbase transaction is valid iff:
1. At least 1 input, at least 1 output.
2. All inputs ≤ `MAX_TX_INPUTS = 1000`.
3. All outputs ≤ `MAX_TX_OUTPUTS = 1000`.
4. All input UTXOs exist.
5. No intra-tx double-spend.
6. All coinbase inputs satisfy maturity.
7. Each input signature verifies (secp256k1/ECDSA, RFC-6979 deterministic).
8. Each input pubkey hashes to the UTXO's locked address (P2PKH).
9. `output_sum <= input_sum`.
10. All output values `>= 0`.

---

## 12. Block Validity

A block is valid iff:
1. Hash meets compact target (`block_hash_int <= bits_to_target(bits)`).
2. `bits == expected_bits(height)` (retarget enforcement).
3. `prev_hash == hash(block[height-1])`.
4. `tx_merkle_root == merkle_root([tx.txid for tx in transactions])`.
5. Timestamp is valid (MTP + drift rules).
6. `len(serialize(block)) <= MAX_BLOCK_SIZE = 1_000_000`.
7. At least 1 transaction.
8. Exactly 1 coinbase transaction, in position 0.
9. No duplicate txids.
10. Coinbase has no inputs.
11. `coinbase_total <= subsidy + fees`.
12. All non-coinbase txs valid (see §11).

---

## 13. Chain Selection

The canonical chain is the one with the most **cumulative work**:

```
block_work(block) = 2^256 / (target + 1)
chain_work(tip)   = sum(block_work(b) for b in chain from genesis to tip)
```

When two competing chains exist, the chain with higher `chain_work` wins.
Height alone does NOT determine the canonical chain.

---

## 14. Reorg

When a competing block is received with `block.index <= current_height`:
1. Find the common ancestor (fork point).
2. Compare `chain_work(new_tip)` vs `chain_work(current_tip)`.
3. If new chain has more work: roll back UTXO to fork point, apply new chain.
4. Transactions in the reorged-away blocks return to the mempool.

---

## 15. Network Identifiers

| Network  | chain_id | Magic (4 bytes)      | P2P Port | Address prefix |
|----------|----------|----------------------|----------|----------------|
| mainnet  | 1        | `AC AC E1 01`        | 9333     | `0x17` (A)     |
| testnet  | 2        | `AC AC E1 02`        | 19333    | `0x6F`         |
| regtest  | 3        | `AC AC E1 03`        | 29333    | `0x6F`         |

---

## 16. Address Format

Address = `RIPEMD160(SHA256(compressed_pubkey))` as 20-byte hex.

Base58Check encoding:
- Prepend version byte (0x17 for mainnet).
- Append `SHA256(SHA256(version+payload))[:4]` as checksum.
- Encode with Base58 alphabet.

---

## 17. Signing Domain

Transaction signatures use:
```
signing_hash = double_SHA256(unsigned_body)
unsigned_body = JSON({ "chain_id": N, "inputs": [...unsigned...], "outputs": [...] })
```

Including `chain_id` prevents cross-network replay attacks.
