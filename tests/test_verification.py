"""
ARCHE AI Verification Layer — Test Suite (Phase 7)
Tests for all 5 verification levels.
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ai.verification import (
    HashVerifier, RedundantVerifier, ChallengeVerifier,
    ProofOfLogits, ZKMLVerifier, VerificationManager,
    VerificationPolicy, VerificationLevel, VerificationResult,
    WorkerSubmission, ChallengeStatus,
)

JOB_ID   = "job-test-001"
HASH_A   = "a" * 64
HASH_B   = "b" * 64
WORKER_A = "aa" * 20
WORKER_B = "bb" * 20
WORKER_C = "cc" * 20


# ── Level 1: Hash Verification ────────────────────────

class TestHashVerifier:

    def test_matching_hashes_verified(self):
        v = HashVerifier()
        rec = v.verify(JOB_ID, HASH_A, HASH_A)
        assert rec.result == VerificationResult.VERIFIED
        assert rec.level == VerificationLevel.HASH

    def test_mismatched_hashes_failed(self):
        v = HashVerifier()
        rec = v.verify(JOB_ID, HASH_A, HASH_B)
        assert rec.result == VerificationResult.FAILED

    def test_case_insensitive(self):
        v = HashVerifier()
        rec = v.verify(JOB_ID, HASH_A.upper(), HASH_A.lower())
        assert rec.result == VerificationResult.VERIFIED

    def test_hash_output(self):
        v = HashVerifier()
        h = v.hash_output(b"hello world")
        assert len(h) == 64

    def test_hash_output_deterministic(self):
        v = HashVerifier()
        assert v.hash_output(b"test") == v.hash_output(b"test")

    def test_different_inputs_different_hash(self):
        v = HashVerifier()
        assert v.hash_output(b"input1") != v.hash_output(b"input2")

    def test_record_has_job_id(self):
        v = HashVerifier()
        rec = v.verify("my-job-123", HASH_A, HASH_A)
        assert rec.job_id == "my-job-123"

    def test_record_completed_at_set(self):
        v = HashVerifier()
        rec = v.verify(JOB_ID, HASH_A, HASH_A)
        assert rec.completed_at is not None


# ── Level 2: Redundant Execution ─────────────────────

class TestRedundantVerifier:

    def test_majority_verified(self):
        v = RedundantVerifier()
        subs = []
        v.add_submission(subs, WORKER_A, HASH_A)
        v.add_submission(subs, WORKER_B, HASH_A)
        v.add_submission(subs, WORKER_C, HASH_A)
        rec, winner = v.evaluate(JOB_ID, subs)
        assert rec.result == VerificationResult.VERIFIED
        assert winner == HASH_A

    def test_no_majority_disputed(self):
        v = RedundantVerifier()
        subs = []
        v.add_submission(subs, WORKER_A, HASH_A)
        v.add_submission(subs, WORKER_B, HASH_B)
        v.add_submission(subs, WORKER_C, "c" * 64)
        rec, winner = v.evaluate(JOB_ID, subs)
        assert rec.result == VerificationResult.DISPUTED
        assert winner is None

    def test_not_enough_submissions_pending(self):
        v = RedundantVerifier()
        subs = []
        v.add_submission(subs, WORKER_A, HASH_A)
        v.add_submission(subs, WORKER_B, HASH_A)
        rec, winner = v.evaluate(JOB_ID, subs)
        assert rec.result == VerificationResult.PENDING
        assert winner is None

    def test_duplicate_worker_rejected(self):
        v = RedundantVerifier()
        subs = []
        v.add_submission(subs, WORKER_A, HASH_A)
        with pytest.raises(ValueError):
            v.add_submission(subs, WORKER_A, HASH_A)

    def test_dishonest_workers_identified(self):
        v = RedundantVerifier()
        subs = []
        v.add_submission(subs, WORKER_A, HASH_A)
        v.add_submission(subs, WORKER_B, HASH_A)
        v.add_submission(subs, WORKER_C, HASH_B)  # dishonest
        rec, _ = v.evaluate(JOB_ID, subs)
        assert WORKER_C in rec.details["dishonest_workers"]
        assert WORKER_A not in rec.details["dishonest_workers"]

    def test_2_vs_1_is_majority(self):
        v = RedundantVerifier()
        subs = []
        v.add_submission(subs, WORKER_A, HASH_A)
        v.add_submission(subs, WORKER_B, HASH_A)
        v.add_submission(subs, WORKER_C, HASH_B)
        rec, winner = v.evaluate(JOB_ID, subs)
        assert rec.result == VerificationResult.VERIFIED
        assert winner == HASH_A


# ── Level 3: Challenge / Dispute ─────────────────────

class TestChallengeVerifier:

    def test_open_challenge(self):
        v = ChallengeVerifier()
        c = v.open_challenge(JOB_ID, WORKER_A, WORKER_B, "Wrong output")
        assert c.status == ChallengeStatus.OPEN
        assert c.challenger == WORKER_A
        assert c.challenged == WORKER_B

    def test_worker_respond(self):
        v = ChallengeVerifier()
        c = v.open_challenge(JOB_ID, WORKER_A, WORKER_B, "Wrong output")
        proof = {"logs": "step1=ok, step2=ok", "intermediate_hash": "x" * 64}
        c = v.respond_to_challenge(c, WORKER_B, proof)
        assert c.status == ChallengeStatus.RESPONDED
        assert c.response is not None

    def test_wrong_worker_cannot_respond(self):
        v = ChallengeVerifier()
        c = v.open_challenge(JOB_ID, WORKER_A, WORKER_B, "Wrong output")
        with pytest.raises(ValueError):
            v.respond_to_challenge(c, WORKER_A, {})

    def test_resolve_challenge_upheld(self):
        v = ChallengeVerifier()
        c = v.open_challenge(JOB_ID, WORKER_A, WORKER_B, "Wrong output")
        v.respond_to_challenge(c, WORKER_B, {"proof": "fake"})
        c, rec = v.resolve_challenge(c, "arbiter", upheld=True, reasoning="Proof invalid")
        assert c.resolution == "UPHELD"
        assert rec.result == VerificationResult.FAILED

    def test_resolve_challenge_dismissed(self):
        v = ChallengeVerifier()
        c = v.open_challenge(JOB_ID, WORKER_A, WORKER_B, "Wrong output")
        v.respond_to_challenge(c, WORKER_B, {"proof": "valid_proof"})
        c, rec = v.resolve_challenge(c, "arbiter", upheld=False, reasoning="Proof valid")
        assert c.resolution == "DISMISSED"
        assert rec.result == VerificationResult.VERIFIED

    def test_timeout_auto_upheld(self):
        v = ChallengeVerifier()
        c = v.open_challenge(JOB_ID, WORKER_A, WORKER_B, "No response")
        # Force deadline to past
        c.deadline = int(time.time()) - 1
        c, rec = v.resolve_challenge(c, "system", upheld=False)
        # Should auto-uphold due to timeout
        assert rec.result == VerificationResult.FAILED


# ── Level 4: Proof of Logits ──────────────────────────

class TestProofOfLogits:

    def test_identical_logits_verified(self):
        v = ProofOfLogits(tolerance=1e-4)
        logits = [0.1, 0.5, 0.3, 0.1]
        rec = v.verify_logits(JOB_ID, logits, logits)
        assert rec.result == VerificationResult.VERIFIED

    def test_within_tolerance_verified(self):
        v = ProofOfLogits(tolerance=1e-3)
        ref = [0.1, 0.5, 0.3, 0.1]
        sub = [0.1001, 0.4999, 0.3001, 0.1]
        rec = v.verify_logits(JOB_ID, sub, ref)
        assert rec.result == VerificationResult.VERIFIED

    def test_outside_tolerance_failed(self):
        v = ProofOfLogits(tolerance=1e-4)
        ref = [0.1, 0.5, 0.3, 0.1]
        sub = [0.1, 0.7, 0.1, 0.1]  # Big difference
        rec = v.verify_logits(JOB_ID, sub, ref)
        assert rec.result == VerificationResult.FAILED

    def test_length_mismatch_failed(self):
        v = ProofOfLogits()
        rec = v.verify_logits(JOB_ID, [0.1, 0.9], [0.1, 0.9, 0.0])
        assert rec.result == VerificationResult.FAILED
        assert rec.error is not None

    def test_logits_hash_deterministic(self):
        v = ProofOfLogits()
        logits = [0.1, 0.5, 0.3, 0.1]
        assert v.compute_logits_hash(logits) == v.compute_logits_hash(logits)

    def test_different_logits_different_hash(self):
        v = ProofOfLogits()
        assert v.compute_logits_hash([0.1, 0.9]) != v.compute_logits_hash([0.9, 0.1])

    def test_security_note_in_details(self):
        """Pastikan security warning ada di hasil verification."""
        v = ProofOfLogits()
        logits = [0.5, 0.5]
        rec = v.verify_logits(JOB_ID, logits, logits)
        assert "security_note" in rec.details


# ── Level 5: ZKML (Stub) ──────────────────────────────

class TestZKMLVerifier:

    def test_zkml_returns_skipped(self):
        v = ZKMLVerifier()
        rec = v.verify_proof(JOB_ID, b"proof", {})
        assert rec.result == VerificationResult.SKIPPED
        assert rec.level == VerificationLevel.ZKML

    def test_zkml_has_not_implemented_status(self):
        v = ZKMLVerifier()
        rec = v.verify_proof(JOB_ID, b"", {})
        assert rec.details.get("status") == "NOT_IMPLEMENTED"

    def test_zkml_has_error_field(self):
        v = ZKMLVerifier()
        rec = v.verify_proof(JOB_ID, b"", {})
        assert rec.error is not None


# ── Verification Manager ──────────────────────────────

class TestVerificationManager:

    def test_hash_verification(self):
        mgr = VerificationManager()
        rec = mgr.verify_hash(JOB_ID, HASH_A, HASH_A)
        assert rec.result == VerificationResult.VERIFIED

    def test_pol_skipped_when_disabled(self):
        policy = VerificationPolicy(enable_pol=False)
        mgr = VerificationManager(policy)
        rec = mgr.verify_logits(JOB_ID, [0.5], [0.5])
        assert rec.result == VerificationResult.SKIPPED

    def test_pol_runs_when_enabled(self):
        policy = VerificationPolicy(enable_pol=True)
        mgr = VerificationManager(policy)
        rec = mgr.verify_logits(JOB_ID, [0.5, 0.5], [0.5, 0.5])
        assert rec.result == VerificationResult.VERIFIED

    def test_zkml_always_skipped(self):
        mgr = VerificationManager()
        rec = mgr.verify_zkml(JOB_ID, b"proof", {})
        assert rec.result == VerificationResult.SKIPPED

    def test_redundant_full_flow(self):
        mgr = VerificationManager()
        subs = []
        mgr.redundant_verifier.add_submission(subs, WORKER_A, HASH_A)
        mgr.redundant_verifier.add_submission(subs, WORKER_B, HASH_A)
        mgr.redundant_verifier.add_submission(subs, WORKER_C, HASH_A)
        rec, winner = mgr.evaluate_redundant(JOB_ID, subs)
        assert winner == HASH_A

    def test_challenge_flow(self):
        mgr = VerificationManager()
        c = mgr.open_challenge(JOB_ID, WORKER_A, WORKER_B, "Bad result")
        assert c.status == ChallengeStatus.OPEN
        c, rec = mgr.resolve_challenge(c, "arbiter", upheld=True)
        assert rec.result == VerificationResult.FAILED

    def test_select_level_hash_when_expected_hash_present(self):
        mgr = VerificationManager()
        job = {"expected_result_hash": HASH_A, "compute_requirement": {}}
        level = mgr.select_level(job)
        assert level == VerificationLevel.HASH
