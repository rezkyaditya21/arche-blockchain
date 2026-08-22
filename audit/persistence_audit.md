# ARCHE Persistence Audit

## Findings

### PERS-001 [HIGH] — No Integrity Checksum on Store
**File:** node/storage.py  
**Description:** JSONStore writes raw JSON with no checksum or magic header. A truncated file loads as valid empty dict silently, wiping all chain state.  
**Fix:** Add a checksum field (SHA256 of content) to detect corruption on load.

### PERS-002 [HIGH] — UTXO Set Not Independently Verifiable
**File:** node/chain.py  
**Description:** UTXO set is rebuilt from `utxo:` prefixed keys on startup. If a crash occurs mid-batch after some UTXO keys are written but before metadata is updated, tip and UTXO state diverge.  
**Fix:** WriteBatch already addresses this for JSONStore. Verify tip == compute_hash(last block) on startup.

### PERS-003 [MEDIUM] — No Startup Consistency Check
**File:** node/chain.py  
**Description:** `_load_state()` reads metadata and rebuilds UTXO but never verifies that `self.tip` matches `get_block(self.height).compute_hash()`.  
**Fix:** Add startup integrity check; rebuild UTXO from chain if inconsistency detected.

### PERS-004 [MEDIUM] — Windows Atomic Rename May Fall Back to Non-Atomic
**File:** node/storage.py  
**Description:** On `PermissionError`, `_flush()` falls back to direct `json.dump()` overwrite which is not atomic. A crash during this path corrupts the store.  
**Fix:** On Windows PermissionError, retry with a small delay rather than falling back to non-atomic write.

### PERS-005 [LOW] — JSONStore O(n) Per Operation
**File:** node/storage.py  
**Description:** Every `put`/`delete` flushes the entire JSON file. At 10,000 blocks with 100 UTXOs each, a single write flushes ~1M entries. Performance degrades as chain grows.  
**Status:** Acceptable for development. LevelDB should be used in production (currently fails on Windows due to missing C++ Build Tools).

### PERS-006 [LOW] — No Block Index Verification
**File:** node/chain.py  
**Description:** `get_block(height)` returns whatever is stored without verifying the block's hash matches the expected chain hash.  
**Fix:** Optionally verify block hash on read in production mode.
