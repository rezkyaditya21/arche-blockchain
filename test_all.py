"""
ARCHE Blockchain — Unified Test Runner (Phase 20-21)
Runs ALL test suites and the audit in one command.
Usage: python test_all.py
"""
import sys, os, subprocess, time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

PASS  = "[PASS]"
FAIL  = "[FAIL]"
SKIP  = "[SKIP]"
results = []

def run_suite(name: str, cmd: list, timeout: int = 120) -> bool:
    print(f"\n{'='*60}")
    print(f"  {name}")
    print('='*60)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, env=env)
        passed = r.returncode == 0
        # Print last 20 lines of output
        output = (r.stdout + r.stderr).strip()
        lines = output.splitlines()
        for line in lines[-20:]:
            print(line)
        status = PASS if passed else FAIL
        print(f"\n{status} {name}")
        results.append((name, passed))
        return passed
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT after {timeout}s")
        results.append((name, False))
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        results.append((name, False))
        return False


print("=" * 60)
print("  ARCHE BLOCKCHAIN — FULL TEST SUITE")
print("=" * 60)
print(f"Python: {sys.version.split()[0]}")
print(f"Time  : {time.strftime('%Y-%m-%d %H:%M:%S')}")

# 1. Original audit (127 tests — regression baseline)
run_suite(
    "Regression Baseline (audit.py — 127 tests)",
    [sys.executable, "audit.py"],
    timeout=180,
)

# 2. Consensus tests
run_suite(
    "Consensus Tests (Phase 2)",
    [sys.executable, "-m", "pytest", "tests/test_consensus.py", "-v", "--tb=short"],
    timeout=120,
)

# 3. Reorg + chain work + persistence tests
run_suite(
    "Reorg + Chain Work + Persistence (Phase 6+7+8)",
    [sys.executable, "-m", "pytest", "tests/test_reorg.py", "-v", "--tb=short"],
    timeout=120,
)

# 4. Wallet security + replay protection + fuzz tests
run_suite(
    "Wallet Security + Replay + Fuzz (Phase 15+17)",
    [sys.executable, "-m", "pytest", "tests/test_wallet_security.py", "-v", "--tb=short"],
    timeout=60,
)

# 5. P2P security tests
run_suite(
    "P2P Security (Phase 9+10)",
    [sys.executable, "-m", "pytest", "tests/test_p2p_security.py", "-v", "--tb=short"],
    timeout=60,
)

# 6. AI Network tests (Phase 1-6)
run_suite(
    "AI Network (Phase 1-6: Jobs/Workers/Payment/Models/Marketplace/Agents)",
    [sys.executable, "-m", "pytest", "tests/test_ai_network.py", "-v", "--tb=short"],
    timeout=60,
)

# 7. Regtest demo (Phase 14)
run_suite(
    "Regtest Demo (Phase 14)",
    [sys.executable, "scripts/regtest_demo.py"],
    timeout=60,
)

# 8. Syntax check all modules
run_suite(
    "Syntax Check (all modules)",
    [sys.executable, "-m", "py_compile",
     "coin_params.py", "node/block.py", "node/chain.py", "node/tx.py",
     "node/pow.py", "node/storage.py", "node/p2p.py", "node/node.py",
     "node/network.py", "wallet/wallet.py", "wallet/cli_wallet.py",
     "rpc/explorer.py", "scripts/genesis.py", "scripts/regtest_demo.py",
     "ai/job.py", "ai/worker.py", "ai/payment.py", "ai/registry.py",
     "ai/marketplace.py", "ai/api.py", "agents/registry.py"],
    timeout=30,
)

# Summary
print("\n" + "=" * 60)
print("  FINAL RESULTS")
print("=" * 60)
total  = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed
print(f"Total suites : {total}")
print(f"Passed       : {passed}")
print(f"Failed       : {failed}")
if failed:
    print("\nFailed suites:")
    for name, ok in results:
        if not ok:
            print(f"  {FAIL} {name}")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
