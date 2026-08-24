# Panduan Install ARCHE (ARC)

Panduan lengkap untuk menjalankan node ARCHE dari nol.

> ⚠️ **Status saat ini:** Network belum publik. Node kamu akan berjalan secara lokal.
> Setelah VPS publik di-deploy, node kamu akan otomatis terhubung ke jaringan.

---

## Syarat Sistem

| Kebutuhan | Minimum |
|-----------|---------|
| OS | Windows 10/11, macOS 12+, Ubuntu 20.04+ |
| Python | 3.11 atau lebih baru |
| RAM | 1 GB |
| Storage | 1 GB |
| Internet | Diperlukan untuk sync antar node |

---

## Langkah 0 — Install Python (jika belum ada)

**Cek apakah Python sudah ada:**
```bash
python --version
```

Jika belum ada atau versinya di bawah 3.11:

**Windows:**
- Download dari https://python.org/downloads
- Saat install, centang **"Add Python to PATH"**
- Restart terminal setelah install

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.11 python3.11-pip
```

**macOS:**
```bash
brew install python@3.11
```

---

## Langkah 1 — Download ARCHE

**Cara 1 — Git (direkomendasikan):**
```bash
git clone https://github.com/rezkyaditya21/arche-blockchain.git
cd arche-blockchain
```

**Cara 2 — Download ZIP:**
- Buka https://github.com/rezkyaditya21/arche-blockchain
- Klik tombol hijau **Code** → **Download ZIP**
- Extract ke folder mana saja
- Buka terminal di folder tersebut

---

## Langkah 2 — Install Dependencies

```bash
pip install -r requirements.txt
```

Jika error `pip not found`:
```bash
python -m pip install -r requirements.txt
```

Jika ada error `coincurve`:
```bash
pip install coincurve
```

> **Catatan Windows:** LevelDB (database cepat) tidak tersedia di Windows tanpa
> Microsoft C++ Build Tools. ARCHE akan otomatis menggunakan JSON store sebagai
> pengganti — ini normal dan tidak bermasalah untuk testnet.

---

## Langkah 3 — Buat Wallet

```bash
python -m wallet.cli_wallet create --base58
```

Contoh output:
```json
{
  "address_hex": "4782fc318e605987dc49266a7ef395802e02c41f",
  "address_base58": "ANHzY8BvJ2gR7MUWNtyYK8FkdBSaf5Txpr",
  "mnemonic": "soldier mountain legend alert rice valid access hurdle hand boss fantasy tent",
  "encrypted": false
}
```

> ⚠️ **PENTING:** Simpan 12 kata mnemonic di tempat yang aman (tulis di kertas).
> Ini satu-satunya cara untuk memulihkan wallet kamu jika file hilang.
> Jangan share mnemonic ke siapapun.

**Buat wallet dengan password (lebih aman):**
```bash
python -m wallet.cli_wallet create --base58 --password "passwordkamu"
```

---

## Langkah 4 — Buat Genesis Block

Langkah ini hanya perlu dilakukan **sekali** saat pertama kali setup.

```bash
python -m scripts.genesis \
  --data ./arc-data \
  --address <ALAMAT_KAMU> \
  --difficulty 1
```

**Windows:**
```bash
python -m scripts.genesis --data ./arc-data --address <ALAMAT_KAMU> --difficulty 1
```

Ganti `<ALAMAT_KAMU>` dengan `address_hex` dari langkah 3.

---

## Langkah 5 — Jalankan Node & Mining

```bash
python -m node.node \
  --data ./arc-data \
  --port 9333 \
  --http-port 9334 \
  --difficulty 1 \
  --mine \
  --miner <ALAMAT_KAMU> \
  --no-retarget \
  --network testnet
```

**Windows (satu baris):**
```bash
python -m node.node --data ./arc-data --port 9333 --http-port 9334 --difficulty 1 --mine --miner <ALAMAT_KAMU> --no-retarget --network testnet
```

Node berhasil jalan jika muncul log seperti:
```
[ARCHE] Node started  height=0
[ARC] Mined block h=1  0a3f...
[ARC] Mined block h=2  0b7c...
```

---

## Langkah 6 — Buka Explorer (Opsional)

Buka terminal baru, lalu:

```bash
python -m rpc.explorer --data ./arc-data --port 8080
```

Buka di browser: **http://127.0.0.1:8080/ui/index.html**

---

## Langkah 7 — Cek Balance

```bash
python -m wallet.cli_wallet balance <ALAMAT_KAMU> --rpc http://127.0.0.1:9334
```

> **Catatan:** Mining reward (coinbase) tidak bisa langsung dipakai.
> Harus menunggu **100 block** setelah reward diterima (coinbase maturity rule).

---

## Kirim ARC ke Orang Lain

```bash
python -m wallet.cli_wallet send <ALAMAT_TUJUAN> <JUMLAH> \
  --wallet ~/.arc_wallet/default.json \
  --rpc http://127.0.0.1:9334 \
  --fee 1000 \
  --wait 60
```

Contoh kirim **1 ARC** (= 100,000,000 base units):
```bash
python -m wallet.cli_wallet send ANHz...xxxx 100000000 --wallet ~/.arc_wallet/default.json --rpc http://127.0.0.1:9334 --fee 1000 --wait 60
```

---

## Recovery Wallet dari Mnemonic

Jika ganti komputer atau file wallet hilang:

```bash
python -m wallet.cli_wallet recover \
  --seed "kata1 kata2 kata3 kata4 kata5 kata6 kata7 kata8 kata9 kata10 kata11 kata12"
```

---

## Demo Lengkap (Regtest)

Untuk mencoba semua fitur secara otomatis:

```bash
python scripts/regtest_demo.py
```

Demo ini akan:
- Buat wallet Alice dan Bob
- Mining 101 block
- Kirim transaksi dari Alice ke Bob
- Verifikasi balance
- Test persistence setelah restart

---

## FAQ

**Q: Berapa lama sync blockchain?**
A: Sangat cepat untuk testnet awal (< 1 menit). Tergantung panjang chain.

**Q: Berapa reward mining?**
A: 50 ARC per block. Halving setiap 500,000 block. Total supply 50 juta ARC.

**Q: Kenapa reward mining tidak langsung bisa dipakai?**
A: Ini adalah **Coinbase Maturity Rule** — keamanan standar di semua blockchain serius. Mining reward harus menunggu 100 block sebelum bisa dibelanjakan.

**Q: Port apa yang perlu dibuka?**
A: Port **9333** (P2P) — agar node kamu terlihat oleh node lain. Port 9334 (HTTP API) opsional.

**Q: Data aman kalau komputer mati?**
A: Ya. Semua data tersimpan di folder `arc-data`. Node lanjut dari block terakhir saat dinyalakan lagi.

**Q: Bisa connect ke node lain sekarang?**
A: Belum. Network publik belum di-deploy. Node kamu akan jalan lokal dulu. Update akan menyusul.

**Q: Apakah bisa jalan di HP Android?**
A: Belum. Butuh Python 3.11 yang tidak tersedia di Android secara native.

---

## Troubleshooting

| Error | Solusi |
|-------|--------|
| `ModuleNotFoundError: coincurve` | `pip install coincurve` |
| `ModuleNotFoundError: flask` | `pip install flask` |
| `RIPEMD160 unavailable` | Install OpenSSL legacy: `sudo apt install libssl-dev` |
| `Port already in use` | Ganti `--port` ke nomor lain, misal `9334` |
| `Address already in use` | Node sudah jalan di background. Tutup dulu atau ganti port |
| Node tidak mining | Pastikan `--mine` dan `--miner` sudah diisi |
| Balance 0 padahal sudah mining | Tunggu 100 block (coinbase maturity) |
