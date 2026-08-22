# Cara Join Network ARCHE (ARC)

Panduan ini untuk siapa saja yang ingin menjalankan node ARCHE dan mulai mining.

---

## Syarat

- Python 3.11 atau lebih baru
- RAM minimal 1 GB
- Storage minimal 1 GB
- Koneksi internet

---

## Langkah 1 — Download ARCHE

```bash
git clone https://github.com/rezkyaditya21/arche-blockchain.git
cd arche-blockchain
```

Tidak punya git? Download ZIP langsung:
- Buka https://github.com/rezkyaditya21/arche-blockchain
- Klik tombol hijau **Code** → **Download ZIP**
- Extract ke folder mana saja

---

## Langkah 2 — Install dependencies

```bash
pip install -r requirements.txt
```

Kalau error `pip not found`, coba:
```bash
python -m pip install -r requirements.txt
```

---

## Langkah 3 — Buat wallet

```bash
python -m wallet.cli_wallet create --base58
```

Output contoh:
```json
{
  "address_hex": "4782fc318e605987dc49266a7ef395802e02c41f",
  "address_base58": "ANHzY8BvJ2gR7MUWNtyYK8FkdBSaf5Txpr",
  "mnemonic": "word1 word2 word3 ... word12"
}
```

**PENTING: Simpan 12 kata mnemonic di tempat aman. Itu satu-satunya cara recovery wallet kamu.**

---

## Langkah 4 — Jalankan node dan mulai mining

Ganti `<ALAMAT_KAMU>` dengan address dari langkah 3:

```bash
python -m node.node \
  --data ./arc-data \
  --port 9333 \
  --http-port 9334 \
  --difficulty 1 \
  --mine \
  --miner <ALAMAT_KAMU> \
  --network testnet
```

**Windows:**
```bash
python -m node.node --data ./arc-data --port 9333 --http-port 9334 --difficulty 1 --mine --miner <ALAMAT_KAMU> --network testnet
```

Node akan otomatis:
- Connect ke seed nodes
- Download blockchain terbaru
- Mulai mining dan dapat reward ARC

---

## Langkah 5 — Cek balance

```bash
python -m wallet.cli_wallet balance <ALAMAT_KAMU> --rpc http://127.0.0.1:9334
```

---

## Langkah 6 — Buka Explorer (opsional)

```bash
python -m rpc.explorer --data ./arc-data --port 8080
```

Buka browser: http://127.0.0.1:8080/ui/index.html

---

## Kirim ARC ke orang lain

```bash
python -m wallet.cli_wallet send <ALAMAT_TUJUAN> <JUMLAH_BASE_UNIT> \
  --wallet ~/.arc_wallet/default.json \
  --rpc http://127.0.0.1:9334 \
  --fee 1000 \
  --wait 60
```

Contoh kirim 1 ARC (= 100,000,000 base units):
```bash
python -m wallet.cli_wallet send ANHz...xxxx 100000000 \
  --wallet ~/.arc_wallet/default.json \
  --rpc http://127.0.0.1:9334 \
  --fee 1000 \
  --wait 60
```

---

## Recovery wallet dari mnemonic

Kalau ganti komputer atau kehilangan wallet file:

```bash
python -m wallet.cli_wallet recover \
  --seed "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12"
```

---

## FAQ

**Q: Berapa lama sync blockchain?**
A: Tergantung panjang chain. Untuk testnet awal, biasanya di bawah 1 menit.

**Q: Berapa reward mining?**
A: 50 ARC per block. Halving setiap 500,000 block.

**Q: Coinbase reward bisa langsung dipakai?**
A: Tidak. Harus menunggu 100 block setelah block reward diterima (coinbase maturity).

**Q: Port berapa yang perlu dibuka di firewall?**
A: Port 9333 (P2P) agar node kamu bisa ditemukan orang lain. Port 9334 (HTTP API) opsional.

**Q: Apakah data aman kalau komputer mati?**
A: Ya. Semua data tersimpan di folder `arc-data`. Node lanjut dari block terakhir saat dinyalakan lagi.

---

## Masalah umum

**`ModuleNotFoundError: No module named 'coincurve'`**
```bash
pip install coincurve
```

**`RIPEMD160 unavailable`**
Install OpenSSL versi yang support legacy algorithms. Di Ubuntu:
```bash
sudo apt install python3-dev libssl-dev
```

**Node tidak bisa connect ke peer**
Pastikan port 9333 tidak diblokir firewall. Di Windows, izinkan Python di Windows Firewall.
