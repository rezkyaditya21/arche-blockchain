# ARCHE AI Network

> **Status: Production Feature (Phase 1-8, 12)**

---

## Gambaran Umum

ARCHE AI Network adalah layer ekonomi AI yang berjalan di atas blockchain ARCHE. ARC digunakan sebagai native payment untuk semua layanan AI dalam ekosistem ini.

```
ARCHE BLOCKCHAIN CORE
    UTXO + PoW + P2P + Wallet + Explorer

         +

ARCHE AI LAYER (modular, terpisah dari core)
    AI Jobs → AI Workers → ARC Payment
    Model Registry → AI Marketplace
    AI Agents → Agent Economy
    Verification → Reputation → Smart Contracts
```

---

## Komponen

### 1. AI Job System (`ai/job.py`)
Unit kerja komputasi yang dibayar ARC.

**Status flow:**
```
PENDING → ASSIGNED → RUNNING → VERIFYING → COMPLETED
                                          → FAILED
                                          → DISPUTED
PENDING → CANCELLED
```

### 2. AI Worker (`ai/worker.py`)
Node terpisah yang menjalankan AI inference.
- Blockchain node **tidak** butuh GPU
- Worker mendaftarkan capability (CPU/GPU/RAM/framework)
- Auto-matched dengan job yang compatible

### 3. ARC Payment (`ai/payment.py`)
Escrow system menggunakan UTXO ARCHE.
- **Escrow**: ARC dikunci sebelum job dimulai
- **Release**: ARC dilepas ke worker setelah verified
- **Refund**: ARC dikembalikan jika job gagal/cancelled
- **Dispute**: ARC ditahan sampai resolved

### 4. Model Registry (`ai/registry.py`)
Metadata model AI di-record on-chain.
- Model file disimpan off-chain (URL/storage reference)
- Blockchain hanya menyimpan: hash, owner, version, metadata
- Search by task, framework, price, GPU requirement

### 5. AI Marketplace (`ai/marketplace.py`)
Penghubung antara requester, model, dan worker.
- Browse model + worker yang tersedia
- Dapatkan price quotes
- Auto-assign worker terbaik untuk job

### 6. AI Agents (`agents/registry.py`)
Agent otonom sebagai first-class participant.
- Punya ARC wallet sendiri
- Bisa request dan bayar AI job
- Memory di-hash on-chain, disimpan off-chain
- Agent-to-agent payment via ARC

### 7. Verification Layer (`ai/verification.py`)
5 level verifikasi hasil AI:

| Level | Nama | Deskripsi | Status |
|-------|------|-----------|--------|
| 1 | Hash | Bandingkan hash output | ✅ Production |
| 2 | Redundant | Majority vote dari banyak worker | ✅ Production |
| 3 | Challenge | Worker wajib buktikan hasil | ✅ Production |
| 4 | Proof of Logits | Verifikasi distribusi output model | 🔬 Research |
| 5 | ZKML | Zero-knowledge proof | 🔬 Placeholder |

### 8. Reputation System (`ai/reputation.py`)
Sistem scoring untuk worker dan agent.
- **Tier**: PROBATION → STANDARD → TRUSTED → ELITE
- **Ban**: otomatis jika score terlalu rendah
- **Decay**: score turun perlahan jika tidak aktif
- **Leaderboard**: ranking berdasarkan score

### 9. AI Smart Contracts (`ai/contracts.py`)
Kontrak programmable yang trigger berdasarkan hasil AI.
- Condition: `gte`, `lte`, `eq`, `contains`, `not_null`
- Action: `TRANSFER_ARC`, `RELEASE_ESCROW`, `EMIT_EVENT`, `TRIGGER_JOB`
- Keamanan: hasil AI **harus** diverifikasi sebelum contract execute

---

## API Endpoints

Jalankan AI API:
```bash
python -m ai.api --data ./arc-data --port 9444
```

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| POST | /ai/jobs | Buat AI job |
| GET | /ai/jobs | List jobs |
| GET | /ai/jobs/:id | Detail job |
| POST | /ai/jobs/:id/result | Worker submit hasil |
| POST | /ai/jobs/:id/verify | Verifikasi hasil |
| POST | /ai/jobs/:id/cancel | Cancel job |
| POST | /ai/workers | Daftarkan worker |
| GET | /ai/workers | List worker tersedia |
| POST | /ai/models | Daftarkan model |
| GET | /ai/models | Search model |
| GET | /ai/marketplace | Browse listings |
| GET | /ai/marketplace/quotes/:id | Price quotes |
| POST | /ai/payments/escrow | Buat escrow |
| POST | /ai/payments/:id/release | Release payment |
| POST | /ai/agents | Daftarkan agent |
| GET | /ai/agents | List agents |
| POST | /ai/verify/hash | Verifikasi level 1 |
| POST | /ai/verify/redundant/submit | Submit ke redundant pool |
| POST | /ai/verify/logits | Verifikasi level 4 (research) |

---

## Catatan Keamanan

- Blockchain node tidak mengeksekusi kode AI arbitrary
- Worker berjalan di proses terpisah dengan sandbox sendiri
- Double payment dicegah dengan tracking txid
- Replay attack dicegah dengan chain_id di signing domain
- Unauthorized claim: hanya assigned worker yang bisa submit hasil
- AI result yang tidak diverifikasi tidak bisa trigger smart contract
