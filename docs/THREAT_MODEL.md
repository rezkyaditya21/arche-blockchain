# ARCHE Threat Model v1.0

---

## 1. Malicious Miner

**Attack:** A miner with >50% hashrate attempts to double-spend, rewrite history,
or selectively censor transactions.

**Impact:** Double-spend confirmed transactions; exclude specific addresses.

**Current mitigation:**
- Cumulative chain-work selection makes rewriting history expensive.
- Any block must satisfy PoW — no shortcuts.

**Remaining risk:**
- No 51%-attack prevention beyond PoW cost.
- At low network hashrate, 51% is feasible with consumer hardware.

**Recommendation:** Increase minimum difficulty; encourage multiple independent miners.

---

## 2. Malicious Peer (P2P)

**Attack:** Peer sends invalid blocks/transactions at high rate to exhaust CPU.

**Impact:** CPU exhaustion; node falls behind; consensus disrupted.

**Current mitigation:**
- Rate limiter: 100 messages/second per peer.
- Ban after 5 consecutive connection failures.
- Message size cap: 4 MB.
- Network magic validation disconnects wrong-network peers immediately.

**Remaining risk:**
- Rate limiter resets in-memory after restart.
- Multiple IPs from same attacker not correlated.

**Recommendation:** Add subnet-level rate limiting; persist ban scores across restarts.

---

## 3. Transaction Spammer

**Attack:** Flood mempool with valid zero-fee transactions to exhaust RAM.

**Impact:** Legitimate transactions evicted; node RAM exhausted.

**Current mitigation:**
- Mempool size limit: `MAX_MEMPOOL_SIZE = 5000` transactions.
- Eviction by fee: lowest-fee transactions evicted first.

**Remaining risk:**
- Attacker with funds can spam with non-zero fees.
- No per-address mempool limit.

**Recommendation:** Add per-address mempool limit; implement replace-by-fee (RBF).

---

## 4. Double-Spender

**Attack:** Submit a transaction, wait for confirmation, then submit a conflicting
transaction spending the same UTXO.

**Impact:** Recipient loses funds.

**Current mitigation:**
- UTXO is removed from set immediately upon confirmation.
- Mempool rejects transactions spending already-spent UTXOs.
- Intra-block double-spend rejected during block validation.

**Remaining risk:**
- With <6 confirmations, a well-resourced attacker could reorg the chain.

**Recommendation:** Require sufficient confirmations for high-value transactions.

---

## 5. State Corruption Attacker

**Attack:** Corrupt the on-disk store to inject fraudulent balance.

**Impact:** False balances; chain divergence.

**Current mitigation:**
- Atomic writes (temp file → rename) prevent partial writes.
- Startup integrity check: if tip hash doesn't match stored block, UTXO is rebuilt.
- UTXO rebuilt from chain replay as fallback.

**Remaining risk:**
- No per-record checksum (only tip-level integrity check).
- JSON store has no cryptographic authentication.

**Recommendation:** Add SHA256 checksum to each stored block; use LevelDB in production.

---

## 6. Network Partition (Eclipse Attack)

**Attack:** Attacker controls all of a node's peers, feeding it a fake chain.

**Impact:** Node accepts a fork; double-spends appear confirmed.

**Current mitigation:**
- Network magic prevents testnet/mainnet mixing.
- Multiple peer connections (up to 125 inbound).

**Remaining risk:**
- No hardcoded peer seeds (DNS seeds).
- Small network → easier to eclipse.

**Recommendation:** Add hardcoded seed nodes; implement peer diversity requirements.

---

## 7. Fork Attacker

**Attack:** Mine a secret chain longer than the public chain, then broadcast it to
cause a deep reorg.

**Impact:** Transactions confirmed on public chain become unconfirmed.

**Current mitigation:**
- Chain selection by cumulative work (not height).
- `_block_work()` correctly weights higher-difficulty blocks.

**Remaining risk:**
- Requires >50% hashrate to sustain; same as 51% attack.

---

## 8. Replay Attacker

**Attack:** Copy a transaction from testnet and broadcast it on mainnet (or vice versa).

**Impact:** Funds moved without owner's mainnet consent.

**Current mitigation:**
- `chain_id` included in signing domain.
- `chain_id=1` (mainnet) signature is invalid on `chain_id=2` (testnet).
- Verified by test: `TestReplayProtection::test_mainnet_sig_invalid_on_testnet`.

**Remaining risk:** None for cross-network replay. Intra-network replay prevented by UTXO model.

---

## 9. Resource Exhaustion (DoS)

**Attack:** Send extremely large blocks/transactions to exhaust disk, RAM, or CPU.

**Impact:** Node crash; denial of service.

**Current mitigation:**
- `MAX_BLOCK_SIZE = 1_000_000` bytes enforced in `validate_block`.
- `MAX_TX_INPUTS = 1000`, `MAX_TX_OUTPUTS = 1000` enforced in `validate_transaction`.
- P2P message cap: 4 MB.
- HTTP `MAX_CONTENT_LENGTH = 1 MB`.
- HTTP rate limit: 30 POST/minute per IP.

**Remaining risk:**
- `MAX_BLOCK_SIZE` checked by JSON serialization size — slightly imprecise.
- No per-connection disk write rate limit.

**Recommendation:** Switch to binary block serialization for precise size measurement.

---

## 10. Wallet Key Theft

**Attack:** Attacker reads wallet file to extract private key.

**Impact:** Complete loss of funds.

**Current mitigation:**
- Encrypted wallets: AES-256-GCM + scrypt KDF.
- Private key never logged or printed.
- Mnemonic never logged.
- Unique nonce per encryption operation.

**Remaining risk:**
- Unencrypted wallet mode still available (no forced encryption).
- Scrypt parameters (N=16384) are on the lower end; increase for mainnet.

**Recommendation:** Warn prominently when creating unencrypted wallet; increase scrypt N to 2^18 for mainnet.
