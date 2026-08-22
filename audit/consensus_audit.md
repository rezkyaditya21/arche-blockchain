# ARCHE Consensus Audit

## Findings

### CONS-001 [CRITICAL] — No Fork / Reorganization
**Status:** NOT IMPLEMENTED  
**File:** node/chain.py  
**Description:** `add_block` only accepts `height == self.height + 1`. Competing chains are silently dropped. A malicious miner can partition the network by broadcasting a longer chain that never gets adopted.  
**Fix Required:** Implement cumulative chain-work based fork selection with UTXO rollback.

### CONS-002 [CRITICAL] — Coinbase Maturity Not Enforced
**Status:** NOT IMPLEMENTED  
**File:** node/chain.py, node/tx.py  
**Description:** `COINBASE_MATURITY = 100` is defined in coin_params but never checked in `validate_transaction`. Coinbase outputs can be spent in the very next block.  
**Fix Required:** Track coinbase output origin height; reject spend if `current_height - coinbase_height < COINBASE_MATURITY`.

### CONS-003 [HIGH] — No Transaction Replay Protection
**Status:** NOT IMPLEMENTED  
**File:** node/tx.py  
**Description:** Signing hash covers only inputs/outputs. A transaction signed on testnet is valid on mainnet. No chain/network identifier in the signing domain.  
**Fix Required:** Include `CHAIN_ID` in `_unsigned_body()` so cross-network replay is impossible.

### CONS-004 [HIGH] — No Block/TX Size Limits Enforced
**Status:** DEFINED BUT NOT ENFORCED  
**File:** coin_params.py, node/chain.py  
**Description:** `MAX_BLOCK_SIZE = 1_000_000` and related constants exist but are never checked during block validation. Attacker can submit a 100MB block.  
**Fix Required:** Enforce size limits in `validate_block`.

### CONS-005 [HIGH] — Cumulative Chain Work Not Used for Chain Selection
**Status:** NOT IMPLEMENTED  
**File:** node/chain.py  
**Description:** `_block_work()` exists but is never used. Chain selection is purely by height.  
**Fix Required:** Use cumulative work for all chain-selection decisions.

### CONS-006 [MEDIUM] — Mempool Has No Size Limit or Eviction
**Status:** NOT IMPLEMENTED  
**File:** node/node.py  
**Description:** `self._mempool` grows unboundedly. An attacker can flood the mempool with valid transactions consuming all RAM.  
**Fix Required:** Enforce `MAX_MEMPOOL_SIZE`, evict lowest-fee transactions.

### CONS-007 [MEDIUM] — Fee Validation Only in Mining, Not in Mempool Accept
**Status:** PARTIAL  
**File:** node/node.py  
**Description:** `fee_floor` is checked in `validate_transaction` when adding to mempool, but the coinbase validation in `validate_block` uses `_total_fees()` which can undercount fees if UTXO state is inconsistent.  
**Fix Required:** Validate fee calculation consistently in both paths.

### CONS-008 [LOW] — Duplicate TX Not Checked in Block
**Status:** PARTIAL  
**File:** node/chain.py  
**Description:** The same txid can appear twice in a block; the second spend would fail UTXO lookup, but the first would be applied, leaving state inconsistent.  
**Fix Required:** Reject blocks with duplicate txids.

### CONS-009 [LOW] — Empty Transaction List Allowed
**Status:** NOT CHECKED  
**File:** node/chain.py  
**Description:** A block with zero transactions (not even coinbase) passes all checks.  
**Fix Required:** Require at least one transaction (the coinbase).

### CONS-010 [LOW] — Negative Value Outputs Not Fully Checked
**Status:** PARTIAL  
**File:** node/tx.py  
**Description:** `validate_transaction` checks `o.value < 0` but coinbase outputs checked in `validate_block` only check `< 0` for a single output. Multiple negative outputs could overflow.  
**Fix Required:** Check all outputs individually.
