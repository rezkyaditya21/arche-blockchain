# Berkontribusi ke ARCHE

Terima kasih sudah tertarik berkontribusi ke ARCHE.

---

## Setup Awal

```bash
git clone https://github.com/rezkyaditya21/arche-blockchain.git
cd arche-blockchain
pip install -r requirements-dev.txt
python test_all.py  # Semua 12 suite harus pass sebelum mulai
```

---

## Aturan Wajib

1. **Test dulu** — Tulis test yang gagal sebelum memperbaiki bug atau menambah fitur
2. **Semua test harus pass** — `python test_all.py` harus `Failed: 0` sebelum PR
3. **Jangan kompromi keamanan konsensus** — jangan mock consensus untuk membuat test pass
4. **Jangan commit private key** — periksa `.gitignore`, jangan commit wallet file
5. **Baca VISION.md dulu** — pahami tujuan proyek sebelum mengusulkan perubahan besar

---

## Area yang Butuh Kontribusi

| Prioritas | Area | Keterangan |
|-----------|------|------------|
| 🔴 Tinggi | VPS deployment | Setup node publik |
| 🔴 Tinggi | AI Worker runtime | Integrasi PyTorch/ONNX |
| 🟡 Menengah | Explorer UI untuk AI | Tampilkan jobs/workers di browser |
| 🟡 Menengah | Payment automation | Otomatisasi escrow transaction |
| 🟢 Rendah | Dokumentasi | Perbaiki atau tambah panduan |
| 🔬 Research | ZKML | Ikuti perkembangan library ZK |

Lihat juga: [audit/](audit/) untuk daftar bug dan masalah yang sudah teridentifikasi.

---

## Pull Request

- Branch: `feature/...` atau `fix/...`
- Satu perubahan logis per commit
- Jelaskan apa yang diubah dan mengapa di deskripsi PR
- Pastikan tidak ada referensi ke proyek lain yang tidak perlu

## Code Style

- Python 3.11+, type hints di mana practical
- `snake_case` untuk fungsi dan variabel
- Semua konstanta network di `coin_params.py` — jangan hardcode
- Baca `docs/VISION.md` untuk memahami arah proyek
