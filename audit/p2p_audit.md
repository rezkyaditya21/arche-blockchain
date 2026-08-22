# ARCHE P2P Audit

## Findings

### P2P-001 [CRITICAL] — No Network Magic
**Description:** No way to distinguish mainnet from testnet at the protocol level. Nodes from different networks will sync with each other.

### P2P-002 [HIGH] — No Per-Peer Rate Limiting
**Description:** A single peer can exhaust CPU by sending large blocks/transactions at high frequency.

### P2P-003 [HIGH] — No Inbound Connection Limit
**Description:** Unlimited inbound connections → fd exhaustion.

### P2P-004 [MEDIUM] — No Protocol Version Negotiation
**Description:** HELLO carries `version` field but it is never checked. A node running v1 will accept messages from v99.

### P2P-005 [MEDIUM] — GET_BLOCKS Has No Timeout
**Description:** Node requests blocks from peer but never times out; stall possible.

### P2P-006 [MEDIUM] — Inventory Dedup Only on Server Side
**Description:** `_seen` set deduplicates on inbound server connections, but outbound connections have no dedup. A message broadcast from node A to node B could be echoed back by node B and re-processed.

### P2P-007 [LOW] — Ban List Not Persisted
**Description:** Banned peers reconnect after node restart.

### P2P-008 [LOW] — No IPv6 Support
**Description:** Hardcoded `AF_INET`. Not a security issue but limits deployment.

### P2P-009 [INFO] — BLOCKS Response Broadcast to All Peers
**Description:** When serving GET_BLOCKS, the node broadcasts to ALL peers instead of replying only to requester. This is wasteful but not a security issue.
