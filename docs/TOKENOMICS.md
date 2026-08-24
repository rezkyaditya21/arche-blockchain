# ARCHE Tokenomics

> **Status: Implemented (fixed supply model)**

---

## Identitas ARC

ARC bukan sekadar coin transfer. ARC adalah unit ekonomi dari seluruh ekosistem ARCHE — dari pembayaran komputasi AI sampai kontrak otonom antar mesin.

---

## Kegunaan ARC

| Use Case | Keterangan |
|----------|------------|
| Transaction fee | Biaya setiap transaksi on-chain |
| AI computation | Bayar worker untuk menjalankan model AI |
| Model access | Bayar per inference ke model berbayar |
| Agent payment | AI agent bayar AI agent lain |
| Marketplace | Bayar layanan di AI marketplace |
| Worker reward | Reward untuk worker yang selesaikan job |
| Escrow | Jaminan pembayaran selama job berlangsung |
| Smart contract | Trigger aksi berdasarkan hasil AI |

---

## Supply Tetap

```
Max Supply      : 50,000,000 ARC
Initial Reward  : 50 ARC per block
Halving         : Setiap 500,000 block
Block Time      : 2 menit (target)
Total Base Units: 5,000,000,000,000,000 (1 ARC = 100,000,000 base units)
```

Supply tidak bisa ditambah. Tidak ada inflasi setelah semua ARC habis ditambang.

**Jadwal supply:**

| Era | Block | Reward | ARC Ditambang |
|-----|-------|--------|---------------|
| 0 | 0 – 499,999 | 50 ARC | 25,000,000 |
| 1 | 500k – 999k | 25 ARC | 12,500,000 |
| 2 | 1M – 1.5M | 12.5 ARC | 6,250,000 |
| … | … | … | … |
| Total | | | ≈50,000,000 ARC |

---

## AI Compute Rewards (Model Saat Ini)

Worker AI mendapat reward langsung dari requester via escrow — bukan dari inflasi protokol. Supply tetap tidak terganggu oleh AI layer.

```
Worker reward = agreed_price (dari requester)
              = worker_fee + model_call_fee
```

---

## Research: Dynamic Compute Economy

> **Status: Research — Belum Diimplementasikan**

Opsi yang sedang dikaji untuk simulasi testnet:
- Pool reward khusus untuk AI compute workers
- Dynamic reward berdasarkan demand/supply
- Tidak akan mengubah max supply 50,000,000 ARC

Simulasi harus selesai sebelum implementasi.
