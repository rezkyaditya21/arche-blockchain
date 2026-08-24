<div align="center">

# ⛓ ARCHE

### The Currency of Decentralized Intelligence

<img src="https://img.shields.io/badge/Ticker-ARC-6c63ff?style=for-the-badge" />
<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/Tests-477%20passing-22d3a4?style=for-the-badge" />
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
<img src="https://img.shields.io/badge/Network-Testnet%20Ready-f59e0b?style=for-the-badge" />

**ARCHE is a blockchain built for one purpose:**
**making artificial intelligence accessible, verifiable, and payable by anyone.**

[Quick Start](#quick-start) · [Join Network](#join-the-network) · [Features](#features) · [Architecture](#architecture) · [Status](#project-status) · [Roadmap](#roadmap)

</div>

---

## What is ARCHE?

ARCHE is a blockchain built from scratch — not a fork, not a modification of any existing project.

On top of a proven UTXO + Proof of Work foundation, ARCHE adds something that did not exist before: a **native AI economy layer**. ARC is the currency for paying AI computation, autonomous agents, model verification, and AI-condition smart contracts.

The vision of ARCHE is a world where:
- Anyone can pay for AI computation without intermediaries
- Machines can transact directly with other machines using ARC
- AI computation results can be cryptographically verified
- No single party controls the network

```
Name      : ARCHE
Ticker    : ARC
Supply    : 50,000,000 ARC (fixed, cannot be increased)
Reward    : 50 ARC/block → halving every 500,000 blocks
Block time: 2 minutes (target)
Algorithm : double-SHA256 Proof of Work
Address   : Base58Check, prefix "A"
```

---

## Why ARCHE?

| Problem | ARCHE Solution |
|---------|----------------|
| AI computation is expensive and centralized | Anyone can be a worker, price set by market |
| No standard way to verify AI results | 5-level on-chain verification layer |
| AI agents have no economic identity | Native agent registry + agent wallet |
| Smart contracts cannot interact with AI | AI-condition smart contracts |
| AI payments must go through centralized platforms | ARC escrow built into the protocol |

---

## Project Status

> **Current stage: Private Testnet Ready**
> The network runs locally. Deployment to a public server is the next milestone.

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
| AI Smart Contracts | ✅ Production | AI-condition programmable contracts |
| PoUW | 🔬 Research | Security not proven — NOT in consensus |
| ZKML | 🔬 Research | Placeholder — technology not ready |
| Federated Learning | 🔬 Prototype | Basic aggregation only |
| Dynamic Economy | 📋 Planned | Simulation needed first |
| VPS Deployment | ❌ Not Done | Next milestone |
| AI Worker Runtime | ❌ Not Done | Needs inference engine (PyTorch/ONNX) |
| Explorer UI (AI) | ❌ Not Done | No web UI for jobs/agents yet |

---

## Known Issues

### Critical (blocking public testnet)
- **No public node running** — network only works locally. Nobody can connect from the internet yet.
- **AI Worker has no runtime** — `ai/worker.py` defines the protocol but there is no inference engine. Needs manual integration with PyTorch/ONNX.

### High
- **Payment not automated** — escrow is recorded, but ARC transactions must be created manually via wallet CLI.
- **No UI for AI features** — web explorer only shows blockchain data. Jobs, Workers, Models, Agents have no visual interface yet.
- **LevelDB unavailable on Windows** — requires C++ Build Tools. Falls back to JSON store automatically.

### Medium
- **Seed nodes empty** — `SEED_NODES` in `coin_params.py` is not filled. New nodes cannot auto-discover peers.
- **ZKML is a stub** — raises `NotImplementedError`. Technology not production-ready anywhere in the industry.

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
python -m node.node --data ./arc-data --port 9333 --http-port 9334 \
  --difficulty 1 --mine --miner <YOUR_ADDRESS> \
  --no-retarget --network testnet

# 6. Open explorer
python -m rpc.explorer --data ./arc-data --port 8080
# Open: http://127.0.0.1:8080/ui/index.html

# 7. Run AI API (optional)
python -m ai.api --data ./arc-data --port 9444
```

---

## Join the Network

> ⚠️ No public node deployed yet. These steps will work once a VPS is online.

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

  Regression Baseline           127 tests
  Consensus                      39 tests
  Reorg + Persistence            11 tests
  Wallet Security + Fuzz         52 tests
  P2P Security                    8 tests
  AI Network (Phase 1-6)         45 tests
  AI Verification                37 tests
  AI Reputation                  23 tests
  Experimental (PoUW/ZKML/FL)    27 tests
  AI Smart Contracts             26 tests
  Regtest Demo                   20 tests
  Syntax Check                    1 test
```

---

## Features

### Blockchain Core
- UTXO model — persisted, crash-safe, auto-rebuilt on startup
- double-SHA256 Proof of Work with fixed 80-byte binary block header
- Automatic difficulty adjustment every 2016 blocks (±4x clamp)
- Coinbase maturity: 100-block lockup enforced at consensus level
- Fork/reorg via cumulative chain-work selection with UTXO rollback
- Replay protection: `chain_id` in signing domain (mainnet/testnet/regtest)
- Network magic: wrong-network peers rejected at handshake
- P2P: persistent connections, 100 msg/s rate limiting, ban mechanism

### AI Economy Layer
- **AI Jobs** — create computation jobs, pay with ARC, full lifecycle
- **AI Workers** — register compute capability, matched to jobs automatically
- **ARC Escrow** — escrow/release/refund with dispute handling
- **Model Registry** — metadata + hash on-chain, model file off-chain
- **AI Marketplace** — search, price quotes, auto-assign best worker
- **AI Agents** — autonomous agents with ARC wallet and on-chain memory hash
- **Verification** — 5 levels from hash comparison to ZKML (research)
- **Reputation** — tier system (Probation→Elite), ban, score decay
- **Smart Contracts** — AI-condition programmable transactions

### Network Modes
| Network | chain_id | P2P Port | HTTP Port |
|---------|----------|----------|-----------|
| mainnet | 1 | 9333 | 9334 |
| testnet | 2 | 19333 | 19334 |
| regtest | 3 | 29333 | 29334 |

---

## Architecture

```
arche-blockchain/
│
├── coin_params.py       ← Single source of truth for all constants
│
├── node/                ← Blockchain core
│   ├── block.py         ← Block header, hashing, PoW
│   ├── chain.py         ← State, UTXO, validation, reorg
│   ├── tx.py            ← Transactions, signing, validation
│   ├── pow.py           ← Mining, difficulty retarget
│   ├── storage.py       ← LevelDB / JSON crash-safe KV store
│   ├── p2p.py           ← TCP P2P, network magic, rate limit
│   ├── node.py          ← Full node + HTTP API
│   └── network.py       ← mainnet / testnet / regtest params
│
├── wallet/              ← Wallet (BIP39, HD keys, encryption)
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
├── experimental/        ← Research (not production)
│   ├── pouw/            ← Proof-of-Useful-Work research
│   ├── zkml/            ← ZKML placeholder
│   └── federated/       ← Federated learning prototype
│
├── scripts/             ← Genesis, regtest demo
├── tests/               ← 477 tests, 12 suites
├── docs/                ← Consensus spec, threat model, vision
└── audit/               ← Security audit reports
```

---

## Roadmap

### v1.1 — Deploy (next)
- [ ] Deploy node to public VPS
- [ ] Fill seed nodes in `coin_params.py`
- [ ] Build `worker_runner.py` — AI inference runtime
- [ ] Add AI features to web explorer UI

### v1.2
- [ ] Automate payment escrow
- [ ] GUI wallet (desktop or web)
- [ ] Multi-node testnet (3+ nodes)

### v1.3 — Mainnet Prep
- [ ] Final mainnet genesis block
- [ ] External security audit
- [ ] DNS seed nodes

### Research (no timeline)
- [ ] ZKML — waiting for mature ZK library
- [ ] PoUW — security analysis in progress
- [ ] Dynamic compute economy — simulation needed

---

## Documentation

| Document | Description |
|----------|-------------|
| [INSTALL.md](INSTALL.md) | Step-by-step installation guide |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [docs/VISION.md](docs/VISION.md) | Vision and identity of ARCHE |
| [docs/CONSENSUS.md](docs/CONSENSUS.md) | ARCHE consensus specification |
| [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) | Security threat analysis |
| [docs/AI_NETWORK.md](docs/AI_NETWORK.md) | AI layer documentation |
| [docs/TOKENOMICS.md](docs/TOKENOMICS.md) | ARC economic model |
| [audit/](audit/) | Security audit reports |

---

## License

MIT © 2026 [rezkyaditya21](https://github.com/rezkyaditya21)
