# ARCHE Tokenomics

> **Status: Implemented (fixed supply model)**

---

## ARC Utility

ARC bukan hanya coin transfer. ARC adalah economic unit dari ARCHE AI Network.

| Use Case | Description |
|----------|-------------|
| Transaction fee | Biaya setiap transaksi on-chain |
| AI computation | Bayar worker untuk menjalankan model |
| Model access | Bayar per inference call ke model berbayar |
| Agent payment | AI agent bayar AI agent |
| Marketplace | Bayar layanan di AI marketplace |
| Worker reward | Reward untuk worker yang selesaikan job |
| Escrow | Jaminan pembayaran selama job berlangsung |

---

## Fixed Supply

```
Max Supply      : 50,000,000 ARC
Initial Reward  : 50 ARC per block
Halving         : Setiap 500,000 block
Block Time      : 2 menit (target)
```

**Supply schedule:**
| Era | Block range | Reward | ARC mined |
|-----|-------------|--------|-----------|
| 0 | 0 – 499,999 | 50 ARC | 25,000,000 |
| 1 | 500k – 999k | 25 ARC | 12,500,000 |
| 2 | 1M – 1.5M | 12.5 ARC | 6,250,000 |
| ... | ... | ... | ... |
| ∞ | → | 0 | ≈50,000,000 total |

---

## AI Compute Rewards (Current Model)

AI workers mendapat reward langsung dari requester via escrow — bukan dari protocol inflation.

```
Worker reward = agreed_price (dari requester)
              = worker_fee + model_call_fee
```

Ini memastikan fixed supply tidak terganggu oleh AI layer.

---

## Future: AI Compute Reward Pool (Research)

> **Status: Research / Not implemented**

Opsi yang sedang dipertimbangkan untuk testnet simulation:
- Dedikasikan sebagian block reward untuk AI compute workers
- Dynamic reward berdasarkan demand/supply
- Tidak mengubah max supply 50M ARC

Simulasi harus dilakukan sebelum implementasi.
