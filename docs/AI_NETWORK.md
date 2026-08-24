# ARCHE AI Network

> **Status: Production Feature (Phase 1-6)**

ARCHE AI Network adalah layer AI economy di atas blockchain ARCHE.
ARC digunakan sebagai native payment untuk semua layanan AI.

---

## Architecture

```
ARCHE BLOCKCHAIN CORE (tidak berubah)
    UTXO + PoW + P2P + Wallet + Explorer

         +

ARCHE AI LAYER (modular, terpisah)
    AI Jobs → AI Workers → ARC Payment
    Model Registry → AI Marketplace
    AI Agents → Agent Economy
```

---

## Components

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
- Tidak membutuhkan GPU untuk blockchain node
- Worker mendaftarkan capability (CPU/GPU/RAM/framework)
- Auto-matched dengan jobs yang compatible

### 3. ARC Payment (`ai/payment.py`)
Escrow system menggunakan UTXO ARCHE.
- Escrow: ARC dikunci sebelum job dimulai
- Release: ARC direlease ke worker setelah verified
- Refund: ARC dikembalikan jika job gagal/cancelled
- Dispute: ARC ditahan sampai resolved

### 4. Model Registry (`ai/registry.py`)
Metadata AI models di-record on-chain.
- Model file disimpan off-chain (IPFS/URL)
- Blockchain hanya menyimpan: hash, owner, version, metadata
- Search by task, framework, price, GPU requirement

### 5. AI Marketplace (`ai/marketplace.py`)
Penghubung antara requester, models, dan workers.
- Browse available models + workers
- Get price quotes
- Auto-assign best worker untuk job

### 6. AI Agents (`agents/registry.py`)
Agent otonom sebagai first-class participant.
- Punya ARC wallet sendiri
- Bisa request dan bayar AI jobs
- Memory di-hash on-chain, disimpan off-chain
- Agent-to-agent payment via ARC

---

## API Endpoints

Start AI API:
```bash
python -m ai.api --data ./arc-data --port 9444
```

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /ai/jobs | Create AI job |
| GET | /ai/jobs | List jobs |
| GET | /ai/jobs/:id | Get job detail |
| POST | /ai/jobs/:id/result | Worker submit result |
| POST | /ai/jobs/:id/verify | Verify result |
| POST | /ai/jobs/:id/cancel | Cancel job |
| POST | /ai/workers | Register worker |
| GET | /ai/workers | List available workers |
| POST | /ai/workers/:id/heartbeat | Worker heartbeat |
| POST | /ai/models | Register model |
| GET | /ai/models | Search models |
| GET | /ai/marketplace | Browse listings |
| GET | /ai/marketplace/quotes/:model_id | Get price quotes |
| POST | /ai/payments/escrow | Create escrow |
| POST | /ai/payments/:job_id/release | Release payment |
| POST | /ai/agents | Register agent |
| GET | /ai/agents | List agents |

---

## Security Notes

- Blockchain node tidak mengeksekusi arbitrary AI code
- AI Worker berjalan di proses terpisah dengan sandbox sendiri
- Double payment dicegah dengan tracking txid
- Replay attack dicegah dengan chain_id di signing domain
- Unauthorized claim: hanya assigned worker yang bisa submit result
