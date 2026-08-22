# ARCHE Security Audit

## Findings

### SEC-001 [CRITICAL] — No Network Magic / Chain Separation
**File:** node/p2p.py  
**Description:** HELLO message carries only `version` and `listen_port`. No network magic bytes. A testnet node will happily sync with a mainnet node, and vice-versa.  
**Fix:** Add `NETWORK_MAGIC` to HELLO handshake; reject connections with wrong magic.

### SEC-002 [HIGH] — P2P No Rate Limiting
**File:** node/p2p.py  
**Description:** A single peer can flood the server with messages at full line rate. Each message triggers consensus validation (CPU-intensive). No per-peer rate limiter exists.  
**Fix:** Implement per-peer token-bucket rate limiter; disconnect/ban on exceeded rate.

### SEC-003 [HIGH] — P2P No Connection Limit
**File:** node/p2p.py  
**Description:** `_accept_loop` accepts unlimited connections. Attacker can exhaust file descriptors.  
**Fix:** Cap total inbound connections (e.g., 125 like Bitcoin).

### SEC-004 [HIGH] — P2P Message Size Check Too Late
**File:** node/p2p.py  
**Description:** `_recv_exact(sock, length)` allocates `length` bytes before the message is validated. The 4 MB cap prevents the worst case, but allocation still occurs before content validation.  
**Fix:** Already has 4MB cap — acceptable. Document explicitly.

### SEC-005 [MEDIUM] — No Peer Score / Ban Persistence
**File:** node/p2p.py  
**Description:** `fail_count` resets on reconnect. Banned peers are only tracked in memory; after restart they can reconnect.  
**Fix:** Persist ban list to disk; implement misbehavior scoring.

### SEC-006 [MEDIUM] — No Request Timeout for GET_BLOCKS
**File:** node/node.py  
**Description:** `_request_blocks` sends GET_BLOCKS but never times out waiting for BLOCKS response. A malicious peer can ignore GET_BLOCKS causing the node to stall at genesis.  
**Fix:** Add timeout + retry logic for IBD.

### SEC-007 [MEDIUM] — Wallet Private Key in Unencrypted Mode
**File:** wallet/wallet.py  
**Description:** `save_wallet()` without password stores private key as plaintext hex. No warning is emitted.  
**Fix:** Add explicit warning; recommend encryption in CLI.

### SEC-008 [LOW] — API No Request Size Limit
**File:** node/node.py (Flask routes)  
**Description:** `POST /tx` uses `get_json(force=True)` with no size limit. Attacker can POST 100MB JSON.  
**Fix:** Enforce `MAX_CONTENT_LENGTH` on Flask app.

### SEC-009 [LOW] — API No Rate Limiting
**File:** node/node.py  
**Description:** No per-IP rate limiting on HTTP API. Attacker can spam POST /tx.  
**Fix:** Add simple in-memory rate limiter or use waitress connection limits.

### SEC-010 [INFO] — Logging May Expose Sensitive Data
**File:** node/node.py, wallet/cli_wallet.py  
**Description:** Log lines include full txids, addresses, and hashes. No PII concern but mnemonic phrases should never be logged.  
**Status:** Mnemonics are not currently logged. Monitor going forward.
