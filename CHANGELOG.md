# Changelog

---

## v1.0.0 — 2026-08-22 (Current)

### Blockchain Core
- UTXO model persisted to LevelDB / crash-safe JSON store
- double-SHA256 PoW with 80-byte binary header
- ARCHE block header: 80-byte fixed binary format
- Difficulty retarget every 2016 blocks (±4x clamp)
- Coinbase maturity: 100-block lockup enforced at consensus level
- Fork/reorg: cumulative chain-work selection with UTXO rollback
- Startup integrity check with automatic UTXO rebuild
- Replay protection: chain_id in signing domain
- Network magic bytes per network (mainnet/testnet/regtest)
- P2P: persistent connections, rate limiting, ban mechanism, inventory dedup
- Web explorer: live block/tx/address browser with search

### AI Economy Layer (Phase 1-8, 12)
- **Phase 1** — AI Job System: full lifecycle (PENDING→COMPLETED), escrow tracking
- **Phase 2** — AI Worker: capability registry, reputation, heartbeat
- **Phase 3** — ARC Payment: escrow, release, refund, dispute
- **Phase 4** — Model Registry: metadata + hash on-chain
- **Phase 5** — AI Marketplace: search, price quotes, auto-assign
- **Phase 6** — AI Agents: wallet, memory hash, agent economy
- **Phase 7** — Verification Layer: 5 levels (Hash/Redundant/Challenge/PoL/ZKML)
- **Phase 8** — Reputation System: tier system, ban, score decay, leaderboard
- **Phase 12** — AI Smart Contracts: AI-condition programmable contracts

### Experimental Research (Phase 9-11)
- **Phase 9** — PoUW research module + security analysis
- **Phase 10** — ZKML placeholder + feasibility checker
- **Phase 11** — Federated Learning prototype

### Testing
- 12 test suites, 477 total tests, all passing
- Consensus tests, reorg tests, wallet security, P2P security
- AI network tests, verification tests, reputation tests
- Smart contract tests, experimental module tests
- Regtest demo (full end-to-end lifecycle)

### Known Issues in v1.0.0
- No public node deployed yet
- AI Worker has no inference runtime
- Payment not fully automated
- No Explorer UI for AI features
- LevelDB unavailable on Windows without C++ Build Tools

---

## Planned: v1.1.0

- Deploy public testnet VPS
- Add seed node to coin_params.py
- Build worker_runner.py (inference runtime)
- AI features in web explorer UI

## Planned: v1.2.0

- AI Worker payment automation
- GUI wallet
- Multi-node testnet

## Planned: v1.3.0

- Mainnet genesis preparation
- External security audit
- DNS seed nodes
