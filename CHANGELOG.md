# Changelog

All notable changes to ARCHE are documented here.

---

## v1.0.0 — 2026-08-22

### Initial Release

#### Core Blockchain
- UTXO model persisted to LevelDB / JSON store
- double-SHA256 PoW with 80-byte binary header
- Bitcoin-compatible compact target (nBits) encoding
- Difficulty retarget every 2016 blocks (±4x clamp)
- Coinbase maturity: 100 block lockup enforced at consensus
- Fork/reorg via cumulative chain-work selection
- UTXO rollback on reorg
- Startup integrity check with automatic UTXO rebuild

#### Transactions
- Replay protection via chain_id in signing domain
- Transaction malleability prevention (txid excludes signatures)
- libsecp256k1 signing via `coincurve` (no timing side-channel)
- P2PKH address locking (RIPEMD160 + SHA256)
- Fee validation: fee = inputs − outputs ≥ 0

#### Wallet
- BIP39 2048-word mnemonic (128-bit entropy + checksum)
- BIP32-style HD key derivation
- AES-256-GCM encrypted wallet files with scrypt KDF
- Base58Check address encoding (prefix "A" for mainnet)
- CLI: create, recover, balance, send, info

#### P2P Networking
- Network magic bytes (4-byte, per-network)
- Protocol version negotiation
- Length-prefixed binary framing (no newline buffer DoS)
- Persistent outbound connections with auto-reconnect
- Per-peer rate limiting: 100 msg/s
- Inbound connection limit: 125
- Ban mechanism with persistent ban list
- Inventory deduplication
- Bidirectional peer exchange via HELLO

#### Network Modes
- mainnet (chain_id=1, port 9333)
- testnet (chain_id=2, port 19333)
- regtest (chain_id=3, port 29333, instant mining)

#### HTTP API
- GET /health, /block/:height, /tx/:txid
- GET /balance/:address, /utxos/:address
- GET /chain (paginated), /mempool
- POST /tx (with rate limiting + CORS)
- MAX_CONTENT_LENGTH = 1 MB

#### Web Explorer
- Live stats: height, tip, block reward, supply, mempool, peers
- Latest blocks table with pagination
- Block detail: full header + transaction breakdown
- Transaction detail: input/output flows
- Address detail: balance + UTXO list
- Mempool live view
- Search: block height, txid, address

#### Security
- Resource limits: MAX_BLOCK_SIZE (1 MB), MAX_TX_INPUTS (1000), MAX_TX_OUTPUTS (1000)
- Empty block rejection
- Duplicate txid in block rejection
- Coinbase-not-first rejection
- Multi-coinbase rejection
- Inflation attack prevention
- Integer overflow protection in fee calculation

#### Testing
- 319+ tests across 7 suites
- Regression baseline: 127 tests
- Consensus suite: 39 tests
- Reorg + persistence: 11 tests
- Wallet security + fuzz: 52 tests
- P2P security: 8 tests
- Regtest demo: 20 tests
