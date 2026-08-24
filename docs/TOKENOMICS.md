# ARCHE Tokenomics

> **Status: Implemented (fixed supply model)**

---

## ARC Identity

ARC is not just a transfer coin. ARC is the economic unit of the entire ARCHE ecosystem — from paying for AI computation to autonomous machine-to-machine contracts.

---

## ARC Utility

| Use Case | Description |
|----------|-------------|
| Transaction fee | Cost of every on-chain transaction |
| AI computation | Pay workers to run AI models |
| Model access | Pay per inference call to paid models |
| Agent payment | AI agent pays another AI agent |
| Marketplace | Pay for services in the AI marketplace |
| Worker reward | Reward for workers who complete jobs |
| Escrow | Payment guarantee while job is in progress |
| Smart contract | Trigger actions based on AI results |

---

## Fixed Supply

```
Max Supply      : 50,000,000 ARC
Initial Reward  : 50 ARC per block
Halving         : Every 500,000 blocks
Block Time      : 2 minutes (target)
Base Units      : 1 ARC = 100,000,000 base units
```

Supply is fixed. No inflation after all ARC is mined.

**Supply schedule:**

| Era | Blocks | Reward | ARC Mined |
|-----|--------|--------|-----------|
| 0 | 0 – 499,999 | 50 ARC | 25,000,000 |
| 1 | 500k – 999k | 25 ARC | 12,500,000 |
| 2 | 1M – 1.5M | 12.5 ARC | 6,250,000 |
| … | … | … | … |
| Total | | | ≈50,000,000 ARC |

---

## AI Compute Rewards (Current Model)

AI workers receive rewards directly from requesters via escrow — not from protocol inflation. The fixed supply is not affected by the AI layer.

```
Worker reward = agreed_price (from requester)
              = worker_fee + model_call_fee
```

---

## Research: Dynamic Compute Economy

> **Status: Research — Not Implemented**

Options under consideration for testnet simulation:
- Dedicated reward pool for AI compute workers
- Dynamic reward based on demand/supply balance
- Will not change the 50,000,000 ARC max supply

Simulation must be completed before any implementation.
