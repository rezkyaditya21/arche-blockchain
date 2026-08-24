"""
ARCHE Proof-of-Useful-Work (PoUW) — Phase 13 Research Module

STATUS: EXPERIMENTAL — Jangan gunakan sebagai consensus utama.

Tujuan:
    Miner melakukan pekerjaan yang punya utility AI/compute
    sekaligus berkontribusi pada keamanan network.

Konsep:
    Normal PoW  → hash arbitrary data sampai dapat nonce valid
    PoUW        → hash output AI computation + block header

Cara kerja (simplified):
    1. Miner ambil AI Job dari network
    2. Jalankan inferensi → dapat output
    3. Hash(output + block_header) harus meet target
    4. Jika valid → block diterima + miner dapat reward + job payment

Analisis keamanan (WAJIB dibaca sebelum adopsi):

    ✅ Keuntungan vs normal PoW:
    - Energi yang dipakai menghasilkan nilai ekonomi (AI computation)
    - Lebih ramah lingkungan secara teoritis

    ❌ Masalah yang belum terpecahkan:
    1. Verifikasi: bagaimana membuktikan miner benar-benar jalankan model?
       Tanpa ZK proof, miner bisa fake output.
    2. ASIC resistance: jika AI workload bisa dioptimasi ke ASIC,
       keunggulan GPU hilang.
    3. Fairness: miner dengan GPU lebih baik dapat reward lebih besar,
       tapi bukan karena hashrate — karena inference speed.
       Ini mengubah incentive structure secara fundamental.
    4. Difficulty adjustment: sulit menyesuaikan difficulty karena
       output AI tidak deterministik (kecuali temperature=0).
    5. Attack: miner bisa submit garbage output dan tetap dapat PoW reward
       jika verification tidak ketat.
    6. Latency: inference bisa butuh beberapa detik — block time terganggu.

    Kesimpulan saat ini:
    PoUW feasible sebagai LAYER TAMBAHAN di atas PoW biasa,
    bukan sebagai pengganti. Miner tetap solve PoW, tapi juga
    opsional bisa include AI work untuk bonus reward.

Benchmark yang dibutuhkan sebelum adopsi:
    - Waktu inference rata-rata per model tier
    - Biaya verification per job
    - Perbandingan security budget: normal PoW vs PoUW
    - Resistance terhadap fake output attack
    - GPU/CPU parity analysis
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# PoUW Block Extension (tambahan ke block header normal)
# ---------------------------------------------------------------------------

@dataclass
class PoUWExtension:
    """
    Extension data yang miner include di block jika melakukan AI work.
    Bersifat OPSIONAL — block tetap valid tanpa ini.
    """
    job_id: str
    model_id: str
    input_hash: str         # SHA256 hash of input
    output_hash: str        # SHA256 hash of output
    inference_time_ms: int  # Waktu inference dalam milidetik
    worker_address: str
    signature: str          # Tanda tangan miner atas job_id+output_hash

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "model_id": self.model_id,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "inference_time_ms": self.inference_time_ms,
            "worker_address": self.worker_address,
            "signature": self.signature,
        }

    def compute_work_hash(self, block_header_bytes: bytes) -> str:
        """
        Hash yang menggabungkan AI output dengan block header.
        Ini yang harus meet PoW target.

        Security note: output_hash harus verified sebelum block diterima.
        Tanpa verification, miner bisa submit random output_hash.
        """
        data = block_header_bytes + bytes.fromhex(self.output_hash)
        return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()


# ---------------------------------------------------------------------------
# PoUW Validator
# ---------------------------------------------------------------------------

class PoUWValidator:
    """
    Validasi PoUW extension di block.

    PENTING: Ini adalah research validator.
    Dalam production, Level 2 (redundant) atau Level 4 (PoL)
    verification harus dijalankan sebelum block diterima.
    """

    def validate_extension(
        self,
        ext: PoUWExtension,
        block_header_bytes: bytes,
        difficulty: int,
    ) -> tuple[bool, str]:
        """
        Validasi PoUW extension.

        Returns:
            (valid: bool, reason: str)
        """
        # 1. Hash format check
        if len(ext.input_hash) != 64 or len(ext.output_hash) != 64:
            return False, "Invalid hash format"

        # 2. PoW check: work_hash must meet difficulty
        work_hash = ext.compute_work_hash(block_header_bytes)
        hash_int = int(work_hash, 16)
        target = (1 << (256 - difficulty * 4)) - 1
        if hash_int > target:
            return False, "Work hash does not meet difficulty"

        # 3. Inference time sanity check
        if ext.inference_time_ms <= 0 or ext.inference_time_ms > 300_000:
            return False, "Inference time out of range"

        # 4. AI output verification (STUB)
        # In production: call VerificationManager.verify_hash() or
        # VerificationManager.evaluate_redundant()
        # For now, we trust the output_hash (INSECURE — research only)

        return True, "OK"

    def compute_bonus_reward(
        self,
        base_subsidy: int,
        ext: Optional[PoUWExtension],
        bonus_rate: float = 0.1,
    ) -> int:
        """
        Hitung bonus reward untuk miner yang include AI work.
        Bonus = base_subsidy * bonus_rate (default 10%)

        Catatan: bonus ini dari fee pool, bukan dari inflasi baru.
        """
        if ext is None:
            return 0
        return int(base_subsidy * bonus_rate)


# ---------------------------------------------------------------------------
# PoUW Benchmark Tool
# ---------------------------------------------------------------------------

def benchmark_inference_time(
    model_callable,
    input_data: bytes,
    runs: int = 10,
) -> dict:
    """
    Benchmark waktu inference sebuah model.
    Gunakan ini untuk menentukan apakah model cocok untuk PoUW.

    Parameters
    ----------
    model_callable : callable yang menerima bytes dan return bytes
    input_data     : sample input
    runs           : jumlah run untuk averaging

    Returns
    -------
    dict dengan stats: mean_ms, min_ms, max_ms, std_ms
    """
    import statistics
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        try:
            model_callable(input_data)
        except Exception:
            pass
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

    return {
        "mean_ms": round(statistics.mean(times), 2),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "std_ms": round(statistics.stdev(times) if len(times) > 1 else 0, 2),
        "runs": runs,
        "feasible_for_pouw": statistics.mean(times) < 5000,  # < 5 detik
    }


# ---------------------------------------------------------------------------
# Security Analysis Report
# ---------------------------------------------------------------------------

SECURITY_ANALYSIS = {
    "name": "Proof-of-Useful-Work Security Analysis",
    "status": "RESEARCH",
    "attacks": {
        "fake_output": {
            "description": "Miner submit garbage AI output dan tetap dapat PoW reward",
            "severity": "CRITICAL",
            "mitigation": "Require Level 2 redundant verification before block acceptance",
            "current_status": "NOT MITIGATED in this prototype",
        },
        "model_substitution": {
            "description": "Miner jalankan model berbeda dari yang diminta",
            "severity": "HIGH",
            "mitigation": "Model hash verification + PoL",
            "current_status": "NOT MITIGATED",
        },
        "asic_dominance": {
            "description": "ASIC miner untuk specific AI workload dominates network",
            "severity": "HIGH",
            "mitigation": "Rotate AI workload types, use diverse models",
            "current_status": "OPEN RESEARCH QUESTION",
        },
        "latency_attack": {
            "description": "Slow inference menyebabkan miner skip AI work → unfair advantage",
            "severity": "MEDIUM",
            "mitigation": "Make AI work optional (bonus only), not required for block validity",
            "current_status": "MITIGATED by optional design",
        },
        "incentive_misalignment": {
            "description": "Miner prefer jobs dengan output mudah di-fake vs jobs yang benar-benar useful",
            "severity": "MEDIUM",
            "mitigation": "Job selection committee, reputation weighting",
            "current_status": "OPEN DESIGN QUESTION",
        },
    },
    "recommendation": (
        "PoUW should remain OPTIONAL and additive. "
        "Implement as bonus reward layer only. "
        "Do NOT replace core PoW until fake_output and model_substitution "
        "attacks are fully mitigated with cryptographic proofs (ZKML)."
    ),
}
