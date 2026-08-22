<div align="center">

# ⛓ ARCHE Blockchain

<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
<img src="https://img.shields.io/badge/Status-Private%20Testnet%20Ready-6c63ff?style=for-the-badge" />
<img src="https://img.shields.io/badge/Tests-319%20passing-22d3a4?style=for-the-badge" />

**A production-grade blockchain written from scratch in Python.**

[Features](#features) · [Quick Start](#quick-start) · [Architecture](#architecture) · [Tests](#tests) · [Docs](#documentation)

</div>

---

## What is ARCHE?

ARCHE is a fully functional blockchain implementation built for real-world use — not education.
It implements the same core concepts as Bitcoin: UTXO model, Proof of Work, P2P networking,
and cryptographic transaction signing — with modern security hardening applied throughout.

```
Coin name   : ARCHE
Ticker      : ARC
Max supply  : 50,000,000 ARC
Block time  : 2 minutes
Block reward: 50 ARC (halving every 500,000 blocks)
Algorithm   : double-SHA256 PoW
Address     : Base58Check, prefix "A"
```

---

## Features

### Core Consensus
- **UTXO model** — Bitcoin-style unspent transaction outputs, persisted to disk
- **double-SHA256 PoW** — 80-byte binary header, 256-bit integer target comparison
- **Difficulty retarget** — every 2016 blocks, clamped ±4x (Bitcoin-compatible)
- **Coinbase maturity** — 100 block lockup enforced at consensus level
- **Fork / Reorg** — cumulative chain-work based chain selection with UTXO rollback
- **Fee market** — `fee = inputs − outputs`, coinbase capped at `subsidy + fees`

### Security
- **Replay protection** — `chain_id` in signing domain (mainnet/testnet/regtest)
- **Network magic** — P2P handshake rejects wrong-network peers immediately
- **libsecp256k1** — via `coincurve` binding (no timing side-channel, unlike pure-Python `ecdsa`)
- **Encrypted wallets** — AES-256-GCM + scrypt KDF, private key never stored in plaintext
- **Resource limits** — `MAX_BLOCK_SIZE`, `MAX_TX_INPUTS`, `MAX_TX_OUTPUTS` enforced at consensus
- **P2P rate limiting** — 100 msg/s per peer, 125 max inbound connections, ban mechanism
- **API protection** — 1 MB max POST, 30 req/min rate limit per IP

### Wallet
- **BIP39** — full 2048-word wordlist, 128-bit entropy, checksum validation
- **HD derivation** — BIP32-style key derivation from mnemonic seed
- **CLI wallet** — create, recover, balance, send with `--fee`, `--wait` confirmation polling

### Networking
- **Persistent P2P** — long-lived TCP connections with auto-reconnect
- **IBD** — Initial Block Download via `GET_BLOCKS / BLOCKS` protocol
- **Bidirectional peers** — `listen_port` in HELLO for automatic peer exchange
- **Inventory dedup** — same message from multiple peers processed only once

### Network Modes
| Network  | chain_id | Magic        | P2P Port | HTTP Port |
|----------|----------|--------------|----------|-----------|
| mainnet  | 1        | `ACACE101`   | 9333     | 9334      |
| testnet  | 2        | `ACACE102`   | 19333    | 19334     |
| regtest  | 3        | `ACACE103`   | 29333    | 29334     |

### Web Explorer
Live block/transaction/address browser with auto-refresh, search, and mempool view.

## Join the Network

Want to run a node and start mining ARC?

```bash
# 1. Clone
git clone https://github.com/rezkyaditya21/arche-blockchain.git
cd arche-blockchain

# 2. Install
pip install -r requirements.txt

# 3. Create wallet
python -m wallet.cli_wallet create --base58

# 4. Run node & mine
python -m node.node --data ./arc-data --port 9333 --http-port 9334 \
  --difficulty 1 --mine --miner <YOUR_ADDRESS> --network testnet
```

Full guide: **[INSTALL.md](INSTALL.md)**

---



### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Create a wallet
```bash
python -m wallet.cli_wallet create --base58
# Save the mnemonic shown — it's your recovery phrase
```

### 3. Create genesis block
```bash
python -m scripts.genesis \
  --data ./arc-data \
  --address <YOUR_ADDRESS> \
  --difficulty 1
```

### 4. Run a node
```bash
python -m node.node \
  --data ./arc-data \
  --port 9333 \
  --http-port 9334 \
  --difficulty 1 \
  --mine \
  --miner <YOUR_ADDRESS> \
  --no-retarget \
  --network testnet
```

### 5. Open the explorer
```bash
python -m rpc.explorer --data ./arc-data --port 8080
# Open http://127.0.0.1:8080/ui/index.html
```

---

## Regtest Demo

Full end-to-end demo — wallet creation, mining, transaction, persistence, replay protection:

```bash
python scripts/regtest_demo.py
```

Expected output:
```
[PASS] Genesis block created
[PASS] Chain at height 101
[PASS] Transaction validates against chain UTXO
[PASS] Bob received funds (bob=10.0 ARC)
[PASS] Height persists after restart
[PASS] Regtest tx INVALID on mainnet (replay protection)
Total: 20  Passed: 20  Failed: 0
```

---

## Tests

```bash
python test_all.py
```

```
Total suites : 7
Passed       : 7
Failed       : 0
```

| Suite | Tests | Coverage |
|-------|-------|----------|
| Regression baseline | 127 | Core blockchain, wallet, API, P2P |
| Consensus | 39 | Block validity, difficulty, fees, maturity |
| Reorg + Chain Work | 11 | Fork detection, UTXO rollback, persistence |
| Wallet Security | 52 | Encryption, replay protection, fuzz |
| P2P Security | 8 | Network magic, rate limit, ban, dedup |
| Regtest Demo | 20 | Full lifecycle end-to-end |
| Syntax check | 1 | All modules |

---

## Architecture

```
arche-blockchain/
│
├── coin_params.py          # Single source of truth for all constants
│
├── node/
│   ├── block.py            # Block header, hashing, PoW target
│   ├── chain.py            # Blockchain state, validation, reorg
│   ├── tx.py               # Transactions, UTXO set, signing
│   ├── pow.py              # Mining loop, difficulty retarget
│   ├── storage.py          # LevelDB / JSON crash-safe KV store
│   ├── p2p.py              # TCP P2P layer, magic, rate limit
│   ├── node.py             # Full node orchestration + HTTP API
│   └── network.py          # mainnet / testnet / regtest params
│
├── wallet/
│   ├── wallet.py           # BIP39, HD keys, AES-256-GCM storage
│   └── cli_wallet.py       # CLI — create, recover, send, balance
│
├── rpc/
│   └── explorer.py         # HTTP API + web explorer backend
│
├── explorer/               # Web frontend (HTML / CSS / JS)
│
├── scripts/
│   ├── genesis.py          # Genesis block generator
│   └── regtest_demo.py     # End-to-end lifecycle demo
│
├── tests/                  # All test suites
├── docs/                   # CONSENSUS.md, THREAT_MODEL.md
└── audit/                  # Security audit reports
```

---

## Documentation

- [Consensus Specification](docs/CONSENSUS.md) — block format, tx rules, PoW, chain selection
- [Threat Model](docs/THREAT_MODEL.md) — attack vectors and mitigations
- [Consensus Audit](audit/consensus_audit.md)
- [Security Audit](audit/security_audit.md)
- [P2P Audit](audit/p2p_audit.md)
- [Persistence Audit](audit/persistence_audit.md)

---

## Readiness

| Subsystem | Status |
|-----------|--------|
| Consensus | ✅ Ready |
| Mining | ✅ Ready |
| UTXO | ✅ Ready |
| Transactions | ✅ Ready |
| Mempool | ✅ Ready |
| Storage | ✅ Ready |
| Wallet | ✅ Ready |
| P2P | ✅ Ready |
| HTTP API | ✅ Ready |
| Reorg | ✅ Ready |
| Network separation | ✅ Ready |
| Security | ✅ Ready |

**Overall: PRIVATE TESTNET READY**

---

## License

MIT © 2026 rezkyaditya21
