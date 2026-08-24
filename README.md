<div align="center">

# ⛓ ARCHE (ARC)

<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/Tests-477%20passing-22d3a4?style=for-the-badge" />
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
<img src="https://img.shields.io/badge/Status-Private%20Testnet%20Ready-6c63ff?style=for-the-badge" />
<img src="https://img.shields.io/badge/Network-Testnet%20Only-f59e0b?style=for-the-badge" />

**A Bitcoin-inspired UTXO blockchain for decentralized AI computation and autonomous machine-to-machine payments.**

[Quick Start](#quick-start) · [Join Network](#join-the-network) · [Features](#features) · [Architecture](#architecture) · [Status](#project-status) · [Roadmap](#roadmap)

</div>

---

## What is ARCHE?

ARCHE is a production-grade blockchain built from scratch in Python, extended with a native AI economy layer. It uses the same proven design as Bitcoin (UTXO + Proof of Work) while adding first-class support for AI computation jobs, AI agents, and machine-to-machine payments using ARC.

```
Coin    : ARCHE
Ticker  : ARC
Supply  : 50,000,000 ARC (fixed, Bitcoin-style halving)
Reward  : 50 ARC/block → halving every 500,000 blocks
Target  : 2 minute block time
PoW     : double-SHA256
Address : Base58Check, prefix "A"
```

---

## Project Status

> **Current stage: Private Testnet Ready**
> The network is not yet publicly deployed. All features run locally.
> Public testnet deployment is the next milestone.

### Feature Status

| Module | Status | Notes |
|--------|--------|-------|
| UTXO Model | ✅ Production | Persisted, crash-safe |
| Proof of Work | ✅ Production | double-SHA256, 80-byte header |
| P2P Networking | ✅ Production | Network magic, rate limiting, ban |
| Wallet (BIP39) | ✅ Production | Encrypted AES-256-GCM + scrypt |
| Transaction Signing | ✅ Production | libsecp256k1, replay protection |
| Coinbase Maturity | ✅ Production | 100-block lockup enforced |
| Fork / Reorg | ✅ Production | Cumulative chain-work selection |
| Web Explorer | ✅ Production | Live block/tx/address browser |
| AI Job System | ✅ Production | Full lifecycle with escrow |
| AI Worker Registry | ✅ Production | Capability matching, reputation |
| ARC Payment Escrow | ✅ Production | Anti double-pay, dispute handling |
| Model Registry | ✅ Production | Metadata + hash on-chain |
| AI Marketplace | ✅ Production | Search, quotes, auto-assign |
| AI Agents | ✅ Production | Wallet, memory hash, agent economy |
| Verification Layer | ✅ Production | 5 levels (Hash/Redundant/Challenge/PoL/ZKML) |
| Reputation System | ✅ Production | Tier system, ban, decay, leaderboard |
| AI Smart Contracts | ✅ Production | AI-condition based programmable contracts |
| PoUW | 🔬 Research | Security not proven — NOT in consensus |
| ZKML | 🔬 Research | Placeholder — technology not ready |
| Federated Learning | 🔬 Prototype | Basic aggregation only |
| Dynamic Economy | 📋 Planned | Simulation needed before implementation |
| VPS Deployment | ❌ Not Done | Next milestone |
| AI Worker Runtime | ❌ Not Done | Needs actual inference engine |
| Explorer UI (AI) | ❌ Not Done | Web UI for jobs/agents not built |

---

## Known Issues & Limitations

### Critical (blocking public testnet)
- **No public node running** — network only works locally. No one can connect from the internet yet.
- **AI Worker has no runtime** — `ai/worker.py` defines the registry and protocol, but there is no `worker_runner.py` that actually runs AI inference. Workers need to integrate PyTorch/ONNX manually.

### High
- **Payment not fully automated** — `ai/payment.py` records escrow, but does not automatically create ARCHE blockchain transactions. User must manually create the ARC transaction via wallet CLI, then paste the txid into the escrow record.
- **No Explorer UI for AI features** — the web explorer only shows blockchain data (blocks, transactions, addresses). AI Jobs, Workers, Models, and Agents have no visual interface yet.
- **LevelDB unavailable on Windows** — requires Microsoft C++ Build Tools. Falls back to JSON store automatically. JSON store is O(n) per write — not suitable for large chains.

### Medium
- **Seed nodes not configured** — `SEED_NODES` in `coin_params.py` is empty. New nodes cannot auto-discover peers until a VPS is deployed and IP is added.
- **No DNS seeds** — peer discovery requires manual `--peer` argument.
- **ZKML is a stub** — `experimental/zkml/zkml.py` raises `NotImplementedError`. Technology not ready in industry.

### Low
- **MetaMask / Trust Wallet not supported** — ARCHE uses its own address format and protocol. EVM compatibility layer not built.
- **No mobile wallet** — CLI only.
- **Windows atomic rename fallback** — on Windows, file replace may fall back to non-atomic write if file is locked by another process (e.g. editor).

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/rezkyaditya21/arche-blockchain.git
cd arche-blockchain

# 2. Install
pip install -r requirements.txt

# 3. Create wallet
python -m wallet.cli_wallet create --base58

# 4. Create genesis block
python -m scripts.genesis --data ./arc-data --address <YOUR_ADDRESS> --difficulty 1

# 5. Run node + mine
python -m node.node \
  --data ./arc-data \
  --port 9333 --http-port 9334 \
  --difficulty 1 --mine \
  --miner <YOUR_ADDRESS> \
  --no-retarget --network testnet

# 6. Start explorer
python -m rpc.explorer --data ./arc-data --port 8080
# Open: http://127.0.0.1:8080/ui/index.html

# 7. Start AI API (optional)
python -m ai.api --data ./arc-data --port 9444
```

---

## Join the Network

> ⚠️ No public node is running yet. These steps will work once a VPS is deployed.

```bash
git clone https://github.com/rezkyaditya21/arche-blockchain.git
cd arche-blockchain
pip install -r requirements.txt
python -m wallet.cli_wallet create --base58
python -m node.node --data ./arc-data --port 9333 --http-port 9334 \
  --difficulty 1 --mine --miner <YOUR_ADDRESS> --network testnet
```

Full guide: **[INSTALL.md](INSTALL.md)**

---

## Run Tests

```bash
python test_all.py
```

```
Total suites : 12
Passed       : 12
Failed       : 0

Suites:
  Regression Baseline     127 tests
  Consensus               39 tests
  Reorg + Persistence     11 tests
  Wallet Security + Fuzz  52 tests
  P2P Security             8 tests
  AI Network (Phase 1-6)  45 tests
  AI Verification          37 tests
  AI Reputation            23 tests
  Experimental (PoUW/ZKML/FL) 27 tests
  AI Smart Contracts       26 tests
  Regtest Demo             20 tests
  Syntax Check              1 test
```

---

## Features

### Blockchain Core
- UTXO model — persisted to LevelDB / crash-safe JSON
- double-SHA256 PoW, 80-byte binary header (Bitcoin-compatible)
- Difficulty retarget every 2016 blocks (±4x clamp)
- Coinbase maturity: 100-block lockup at consensus level
- Fork/reorg via cumulative chain-work selection with UTXO rollback
- Replay protection: `chain_id` in signing domain (mainnet/testnet/regtest)
- Network magic: wrong-network peers rejected at handshake
- P2P: persistent connections, rate limiting (100 msg/s), ban mechanism

### AI Economy Layer
- **AI Jobs** — create computation jobs, pay with ARC, full lifecycle
- **AI Workers** — register compute capability, get matched to jobs
- **ARC Escrow** — automatic escrow/release/refund with dispute handling
- **Model Registry** — metadata + hash on-chain, model file off-chain
- **AI Marketplace** — search, price quotes, auto-assign best worker
- **AI Agents** — autonomous agents with ARC wallet and memory
- **Verification** — 5 levels from hash comparison to ZKML (research)
- **Reputation** — tier system (Probation→Elite), ban, score decay
- **Smart Contracts** — AI-condition based programmable transactions

### Network Modes
| Network | chain_id | Port | Description |
|---------|----------|------|-------------|
| mainnet | 1 | 9333 | Production (not launched) |
| testnet | 2 | 19333 | Public testing (not deployed) |
| regtest | 3 | 29333 | Local instant-mine |

---

## Architecture

```
arche-blockchain/
│
├── coin_params.py       ← Single source of truth for all constants
│
├── node/                ← Blockchain core (DO NOT modify without tests)
│   ├── block.py         ← Block header, hashing, PoW
│   ├── chain.py         ← Blockchain state, UTXO, validation, reorg
│   ├── tx.py            ← Transactions, signing, validation
│   ├── pow.py           ← Mining, difficulty retarget
│   ├── storage.py       ← LevelDB / JSON crash-safe KV store
│   ├── p2p.py           ← TCP P2P, network magic, rate limit
│   ├── node.py          ← Full node + HTTP API
│   └── network.py       ← mainnet / testnet / regtest params
│
├── wallet/              ← Wallet (BIP39, HD keys, AES-256-GCM)
├── rpc/                 ← HTTP explorer + web UI
├── explorer/            ← Web frontend (HTML/CSS/JS)
│
├── ai/                  ← AI Economy Layer
│   ├── job.py           ← AI Job lifecycle
│   ├── worker.py        ← Worker registry
│   ├── payment.py       ← ARC escrow
│   ├── registry.py      ← Model registry
│   ├── marketplace.py   ← Search + matching
│   ├── verification.py  ← 5-level verification
│   ├── reputation.py    ← Scoring + tiers
│   ├── contracts.py     ← AI smart contracts
│   └── api.py           ← HTTP API (port 9444)
│
├── agents/              ← AI Agents
│   └── registry.py      ← Agent registry + memory
│
├── experimental/        ← Research (NOT production)
│   ├── pouw/            ← Proof-of-Useful-Work research
│   ├── zkml/            ← ZKML placeholder
│   └── federated/       ← Federated learning prototype
│
├── scripts/             ← Genesis, regtest demo
├── tests/               ← 477 tests across 12 suites
├── docs/                ← CONSENSUS.md, THREAT_MODEL.md, etc.
└── audit/               ← Security audit reports
```

---

## Roadmap

### Next (v1.1)
- [ ] Deploy public testnet node to VPS
- [ ] Add seed node IP to `coin_params.py`
- [ ] Build `worker_runner.py` — actual AI inference runtime
- [ ] Add AI features to web explorer UI

### v1.2
- [ ] AI Worker payment automation
- [ ] GUI wallet (desktop or web)
- [ ] Multi-node testnet with 3+ nodes

### v1.3
- [ ] Mainnet genesis preparation
- [ ] External security audit
- [ ] DNS seed nodes

### Research (no timeline)
- [ ] ZKML — waiting for mature ZK library
- [ ] PoUW — security analysis in progress
- [ ] Dynamic compute economy — simulation needed
- [ ] EVM compatibility / MetaMask support

---

## Documentation

| Document | Description |
|----------|-------------|
| [INSTALL.md](INSTALL.md) | Step-by-step guide to join the network |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [docs/CONSENSUS.md](docs/CONSENSUS.md) | Full consensus specification |
| [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) | Security threat analysis |
| [docs/AI_NETWORK.md](docs/AI_NETWORK.md) | AI layer documentation |
| [docs/TOKENOMICS.md](docs/TOKENOMICS.md) | ARC economic model |
| [audit/consensus_audit.md](audit/consensus_audit.md) | Consensus audit report |
| [audit/security_audit.md](audit/security_audit.md) | Security audit report |

---

## License

MIT © 2026 [rezkyaditya21](https://github.com/rezkyaditya21)
