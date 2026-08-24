# ARCHE AI Network

> **Status: Production Feature (Phase 1-8, 12)**

---

## Overview

ARCHE AI Network is the AI economy layer running on top of the ARCHE blockchain. ARC is used as the native payment for all AI services in this ecosystem.

```
ARCHE BLOCKCHAIN CORE
    UTXO + PoW + P2P + Wallet + Explorer

         +

ARCHE AI LAYER (modular, separate from core)
    AI Jobs → AI Workers → ARC Payment
    Model Registry → AI Marketplace
    AI Agents → Agent Economy
    Verification → Reputation → Smart Contracts
```

---

## Components

### 1. AI Job System (`ai/job.py`)
A unit of AI computation paid in ARC.

**Status flow:**
```
PENDING → ASSIGNED → RUNNING → VERIFYING → COMPLETED
                                          → FAILED
                                          → DISPUTED
PENDING → CANCELLED
```

### 2. AI Worker (`ai/worker.py`)
A separate node that runs AI inference.
- Blockchain node does **not** need a GPU
- Workers register their capability (CPU/GPU/RAM/framework)
- Auto-matched to compatible jobs

### 3. ARC Payment (`ai/payment.py`)
Escrow system using ARCHE UTXO.
- **Escrow**: ARC locked before job starts
- **Release**: ARC sent to worker after verification
- **Refund**: ARC returned if job fails or is cancelled
- **Dispute**: ARC held until resolved

### 4. Model Registry (`ai/registry.py`)
AI model metadata recorded on-chain.
- Model files stored off-chain (URL or storage reference)
- Blockchain stores only: hash, owner, version, metadata
- Searchable by task, framework, price, GPU requirement

### 5. AI Marketplace (`ai/marketplace.py`)
Connects requesters, models, and workers.
- Browse available models and workers
- Get price quotes
- Auto-assign the best available worker

### 6. AI Agents (`agents/registry.py`)
Autonomous agents as first-class participants.
- Have their own ARC wallet
- Can request and pay for AI jobs
- Memory hash recorded on-chain, stored off-chain
- Agent-to-agent payment via ARC

### 7. Verification Layer (`ai/verification.py`)
5 levels of AI result verification:

| Level | Name | Description | Status |
|-------|------|-------------|--------|
| 1 | Hash | Compare output hash | ✅ Production |
| 2 | Redundant | Majority vote from multiple workers | ✅ Production |
| 3 | Challenge | Worker must prove result | ✅ Production |
| 4 | Proof of Logits | Verify model output distribution | 🔬 Research |
| 5 | ZKML | Zero-knowledge proof | 🔬 Placeholder |

### 8. Reputation System (`ai/reputation.py`)
Scoring system for workers and agents.
- **Tiers**: PROBATION → STANDARD → TRUSTED → ELITE
- **Ban**: automatic when score drops too low
- **Decay**: score decreases slowly when inactive
- **Leaderboard**: ranked by score

### 9. AI Smart Contracts (`ai/contracts.py`)
Programmable contracts triggered by AI results.
- Conditions: `gte`, `lte`, `eq`, `contains`, `not_null`
- Actions: `TRANSFER_ARC`, `RELEASE_ESCROW`, `EMIT_EVENT`, `TRIGGER_JOB`
- Security: AI result **must** be verified before contract executes

---

## API Endpoints

Start the AI API:
```bash
python -m ai.api --data ./arc-data --port 9444
```

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /ai/jobs | Create AI job |
| GET | /ai/jobs | List jobs |
| GET | /ai/jobs/:id | Job detail |
| POST | /ai/jobs/:id/result | Worker submits result |
| POST | /ai/jobs/:id/verify | Verify result |
| POST | /ai/jobs/:id/cancel | Cancel job |
| POST | /ai/workers | Register worker |
| GET | /ai/workers | List available workers |
| POST | /ai/models | Register model |
| GET | /ai/models | Search models |
| GET | /ai/marketplace | Browse listings |
| GET | /ai/marketplace/quotes/:id | Price quotes |
| POST | /ai/payments/escrow | Create escrow |
| POST | /ai/payments/:id/release | Release payment |
| POST | /ai/agents | Register agent |
| GET | /ai/agents | List agents |
| POST | /ai/verify/hash | Level 1 verification |
| POST | /ai/verify/redundant/submit | Submit to redundant pool |
| POST | /ai/verify/logits | Level 4 verification (research) |

---

## Security Notes

- Blockchain node does not execute arbitrary AI code
- Workers run in a separate process with their own sandbox
- Double payment prevented by txid tracking
- Replay attacks prevented by chain_id in signing domain
- Unauthorized claims: only the assigned worker can submit results
- Unverified AI results cannot trigger smart contracts
