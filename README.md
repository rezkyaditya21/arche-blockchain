<div align="center">

# ⛓ ARCHE

### The Currency of Decentralized Intelligence

<img src="https://img.shields.io/badge/Ticker-ARC-6c63ff?style=for-the-badge" />
<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/Tests-477%20passing-22d3a4?style=for-the-badge" />
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
<img src="https://img.shields.io/badge/Network-Testnet%20Ready-f59e0b?style=for-the-badge" />

**ARCHE adalah blockchain yang dibangun untuk satu tujuan:**
**menjadikan kecerdasan buatan dapat diakses, dapat diverifikasi, dan dapat dibayar oleh siapapun.**

[Mulai](#quick-start) · [Bergabung](#join-the-network) · [Fitur](#features) · [Arsitektur](#architecture) · [Status](#project-status) · [Roadmap](#roadmap)

</div>

---

## Apa itu ARCHE?

ARCHE adalah blockchain yang dibangun dari nol — bukan fork, bukan modifikasi proyek lain.

Di atas fondasi UTXO + Proof of Work yang terbukti aman, ARCHE menambahkan sesuatu yang belum ada sebelumnya: **native AI economy layer**. ARC adalah mata uang untuk membayar komputasi AI, agent otonom, verifikasi hasil model, dan kontrak pintar berbasis AI.

Visi ARCHE adalah dunia di mana:
- Siapapun bisa membayar tugas AI tanpa perantara
- Mesin bisa bertransaksi langsung dengan mesin lain menggunakan ARC
- Hasil komputasi AI bisa diverifikasi secara kriptografis
- Tidak ada satu pihak pun yang memegang kendali atas network

```
Nama      : ARCHE
Ticker    : ARC
Supply    : 50,000,000 ARC (tetap, tidak bisa ditambah)
Reward    : 50 ARC/block → halving setiap 500,000 block
Block time: 2 menit (target)
Algoritma : double-SHA256 Proof of Work
Alamat    : Base58Check, awalan "A"
```

---

## Mengapa ARCHE?

| Masalah | Solusi ARCHE |
|---------|-------------|
| AI computation mahal dan terpusat | Siapapun bisa jadi worker, harga ditentukan pasar |
| Tidak ada cara verifikasi hasil AI | 5-level verification layer on-chain |
| Agent AI tidak punya identitas ekonomi | Agent registry + agent wallet native |
| Smart contract tidak bisa berinteraksi dengan AI | AI-condition smart contracts |
| Pembayaran AI harus lewat platform terpusat | ARC escrow langsung di protokol |

---

## Project Status

> **Stage saat ini: Private Testnet Ready**
> Network berjalan secara lokal. Deployment ke server publik adalah milestone berikutnya.

### Status Fitur

| Modul | Status | Keterangan |
|-------|--------|------------|
| UTXO Model | ✅ Production | Persisted, crash-safe |
| Proof of Work | ✅ Production | double-SHA256, 80-byte header |
| P2P Networking | ✅ Production | Network magic, rate limiting, ban |
| Wallet (BIP39) | ✅ Production | Encrypted AES-256-GCM + scrypt |
| Transaction Signing | ✅ Production | libsecp256k1, replay protection |
| Coinbase Maturity | ✅ Production | 100-block lockup enforced |
| Fork / Reorg | ✅ Production | Cumulative chain-work selection |
| Web Explorer | ✅ Production | Live block/tx/address browser |
| AI Job System | ✅ Production | Full lifecycle dengan escrow |
| AI Worker Registry | ✅ Production | Capability matching, reputation |
| ARC Payment Escrow | ✅ Production | Anti double-pay, dispute |
| Model Registry | ✅ Production | Metadata + hash on-chain |
| AI Marketplace | ✅ Production | Search, quotes, auto-assign |
| AI Agents | ✅ Production | Wallet, memory hash, agent economy |
| Verification Layer | ✅ Production | 5 level (Hash/Redundant/Challenge/PoL/ZKML) |
| Reputation System | ✅ Production | Tier system, ban, decay, leaderboard |
| AI Smart Contracts | ✅ Production | AI-condition programmable contracts |
| PoUW | 🔬 Research | Keamanan belum terbukti — bukan di consensus |
| ZKML | 🔬 Research | Placeholder — teknologi belum siap |
| Federated Learning | 🔬 Prototype | Basic aggregation only |
| Dynamic Economy | 📋 Planned | Perlu simulasi sebelum implementasi |
| VPS Deployment | ❌ Belum | Milestone berikutnya |
| AI Worker Runtime | ❌ Belum | Butuh inference engine (PyTorch/ONNX) |
| Explorer UI (AI) | ❌ Belum | UI untuk jobs/agents belum dibuat |

---

## Known Issues

### Kritis (blocking public testnet)
- **Belum ada node publik** — network hanya berjalan lokal. Belum ada yang bisa connect dari internet.
- **AI Worker belum bisa jalankan model** — `ai/worker.py` mendefinisikan protokol, tapi tidak ada runtime inference. Perlu integrasi manual dengan PyTorch/ONNX.

### Tinggi
- **Payment belum otomatis** — escrow direcord, tapi transaksi ARC harus dibuat manual via wallet CLI.
- **Tidak ada UI untuk AI features** — web explorer hanya tampilkan blockchain. Jobs, Workers, Models, Agents belum bisa dilihat di browser.
- **LevelDB tidak tersedia di Windows** — butuh C++ Build Tools. Otomatis fallback ke JSON store.

### Menengah
- **Seed node kosong** — `SEED_NODES` di `coin_params.py` belum diisi. Node baru tidak bisa auto-discover peer.
- **ZKML adalah stub** — raise `NotImplementedError`. Teknologi belum siap di level industri manapun.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/rezkyaditya21/arche-blockchain.git
cd arche-blockchain

# 2. Install
pip install -r requirements.txt

# 3. Buat wallet
python -m wallet.cli_wallet create --base58

# 4. Buat genesis block
python -m scripts.genesis --data ./arc-data --address <ALAMAT_KAMU> --difficulty 1

# 5. Jalankan node + mining
python -m node.node --data ./arc-data --port 9333 --http-port 9334 \
  --difficulty 1 --mine --miner <ALAMAT_KAMU> \
  --no-retarget --network testnet

# 6. Buka explorer
python -m rpc.explorer --data ./arc-data --port 8080
# Buka: http://127.0.0.1:8080/ui/index.html

# 7. Jalankan AI API (opsional)
python -m ai.api --data ./arc-data --port 9444
```

---

## Join the Network

> ⚠️ Node publik belum di-deploy. Langkah ini akan berfungsi setelah VPS online.

```bash
git clone https://github.com/rezkyaditya21/arche-blockchain.git
cd arche-blockchain
pip install -r requirements.txt
python -m wallet.cli_wallet create --base58
python -m node.node --data ./arc-data --port 9333 --http-port 9334 \
  --difficulty 1 --mine --miner <ALAMAT_KAMU> --network testnet
```

Panduan lengkap: **[INSTALL.md](INSTALL.md)**

---

## Run Tests

```bash
python test_all.py
```

```
Total suites : 12
Passed       : 12
Failed       : 0

  Regression Baseline          127 tests
  Consensus                     39 tests
  Reorg + Persistence           11 tests
  Wallet Security + Fuzz        52 tests
  P2P Security                   8 tests
  AI Network (Phase 1-6)        45 tests
  AI Verification               37 tests
  AI Reputation                 23 tests
  Experimental (PoUW/ZKML/FL)   27 tests
  AI Smart Contracts            26 tests
  Regtest Demo                  20 tests
  Syntax Check                   1 test
```

---

## Features

### Blockchain Core
- UTXO model — persisted, crash-safe, rebuilt automatically on startup
- double-SHA256 Proof of Work dengan 80-byte binary block header
- Difficulty adjustment otomatis setiap 2016 block (clamp ±4x)
- Coinbase maturity: 100 block lockup di level konsensus
- Fork/reorg via cumulative chain-work selection dengan UTXO rollback
- Replay protection: `chain_id` dalam signing domain (mainnet/testnet/regtest)
- Network magic: peer dari network berbeda ditolak saat handshake
- P2P: persistent connections, rate limiting 100 msg/s, ban mechanism

### AI Economy Layer
- **AI Jobs** — buat computation job, bayar dengan ARC, full lifecycle
- **AI Workers** — daftarkan compute capability, matched ke job secara otomatis
- **ARC Escrow** — escrow/release/refund otomatis dengan dispute handling
- **Model Registry** — metadata + hash on-chain, model file off-chain
- **AI Marketplace** — search, price quotes, auto-assign worker terbaik
- **AI Agents** — agent otonom dengan ARC wallet dan memory hash on-chain
- **Verification** — 5 level dari hash comparison sampai ZKML research
- **Reputation** — tier system (Probation→Elite), ban, score decay
- **Smart Contracts** — kontrak dengan AI condition dan programmable actions

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
├── coin_params.py       ← Satu sumber kebenaran untuk semua konstanta
│
├── node/                ← Blockchain core
│   ├── block.py         ← Block header, hashing, PoW
│   ├── chain.py         ← State, UTXO, validasi, reorg
│   ├── tx.py            ← Transaksi, signing, validasi
│   ├── pow.py           ← Mining, difficulty retarget
│   ├── storage.py       ← LevelDB / JSON crash-safe KV store
│   ├── p2p.py           ← TCP P2P, network magic, rate limit
│   ├── node.py          ← Full node + HTTP API
│   └── network.py       ← mainnet / testnet / regtest params
│
├── wallet/              ← Wallet (BIP39, HD keys, enkripsi)
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
├── experimental/        ← Research (bukan production)
│   ├── pouw/            ← Proof-of-Useful-Work research
│   ├── zkml/            ← ZKML placeholder
│   └── federated/       ← Federated learning prototype
│
├── scripts/             ← Genesis, regtest demo
├── tests/               ← 477 tests, 12 suites
├── docs/                ← Spesifikasi konsensus, threat model
└── audit/               ← Laporan audit keamanan
```

---

## Roadmap

### v1.1 — Deploy (segera)
- [ ] Deploy node ke VPS publik
- [ ] Isi seed node di `coin_params.py`
- [ ] Bangun `worker_runner.py` — runtime inference AI
- [ ] Tambahkan AI features ke web explorer

### v1.2
- [ ] Otomatisasi payment escrow
- [ ] GUI wallet (desktop atau web)
- [ ] Multi-node testnet (3+ node)

### v1.3 — Mainnet Prep
- [ ] Genesis block mainnet yang final
- [ ] Audit keamanan eksternal
- [ ] DNS seed nodes

### Research (tanpa timeline)
- [ ] ZKML — menunggu library yang mature
- [ ] PoUW — analisis keamanan masih berlangsung
- [ ] Dynamic compute economy — perlu simulasi

---

## Dokumentasi

| Dokumen | Isi |
|---------|-----|
| [INSTALL.md](INSTALL.md) | Panduan install lengkap dari nol |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Cara berkontribusi |
| [CHANGELOG.md](CHANGELOG.md) | Riwayat perubahan |
| [docs/VISION.md](docs/VISION.md) | Visi dan identitas ARCHE |
| [docs/CONSENSUS.md](docs/CONSENSUS.md) | Spesifikasi konsensus ARCHE |
| [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) | Analisis ancaman keamanan |
| [docs/AI_NETWORK.md](docs/AI_NETWORK.md) | Dokumentasi AI layer |
| [docs/TOKENOMICS.md](docs/TOKENOMICS.md) | Model ekonomi ARC |
| [audit/](audit/) | Laporan audit keamanan |

---

## License

MIT © 2026 [rezkyaditya21](https://github.com/rezkyaditya21)
