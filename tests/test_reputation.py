"""
ARCHE AI Reputation System — Test Suite (Phase 8)
"""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ai.reputation import (
    ReputationManager, ReputationStore, EventType,
    INITIAL_SCORE, SCORE_MIN, SCORE_MAX, compute_tier,
)

ADDR_A = "aa" * 20
ADDR_B = "bb" * 20


@pytest.fixture
def mgr():
    d = tempfile.mkdtemp()
    yield ReputationManager(ReputationStore(d))
    shutil.rmtree(d)


class TestReputationBasic:

    def test_new_address_gets_initial_score(self, mgr):
        rec = mgr.get_or_create(ADDR_A)
        assert rec.score == INITIAL_SCORE
        assert rec.tier == "PROBATION"

    def test_initial_score_not_100(self, mgr):
        """New worker starts at 60, not 100 — prevents Sybil advantage."""
        rec = mgr.get_or_create(ADDR_A)
        assert rec.score < 100.0

    def test_job_success_increases_score(self, mgr):
        mgr.get_or_create(ADDR_A)
        rec = mgr.record_event(ADDR_A, EventType.JOB_SUCCESS)
        assert rec.score > INITIAL_SCORE
        assert rec.successful_jobs == 1

    def test_job_failed_decreases_score(self, mgr):
        mgr.get_or_create(ADDR_A)
        rec = mgr.record_event(ADDR_A, EventType.JOB_FAILED)
        assert rec.score < INITIAL_SCORE
        assert rec.failed_jobs == 1

    def test_timeout_decreases_score_significantly(self, mgr):
        mgr.get_or_create(ADDR_A)
        before = mgr.get_score(ADDR_A)
        rec = mgr.record_event(ADDR_A, EventType.TIMEOUT)
        assert rec.score < before - 20

    def test_score_cannot_exceed_max(self, mgr):
        mgr.get_or_create(ADDR_A)
        for _ in range(100):
            mgr.record_event(ADDR_A, EventType.JOB_SUCCESS)
        rec = mgr.store.get(ADDR_A)
        assert rec.score <= SCORE_MAX

    def test_score_cannot_go_below_min(self, mgr):
        mgr.get_or_create(ADDR_A)
        for _ in range(100):
            mgr.record_event(ADDR_A, EventType.JOB_FAILED)
        rec = mgr.store.get(ADDR_A)
        assert rec.score >= SCORE_MIN

    def test_dispute_lost_large_penalty(self, mgr):
        mgr.get_or_create(ADDR_A)
        before = mgr.get_score(ADDR_A)
        rec = mgr.record_event(ADDR_A, EventType.DISPUTE_LOST)
        assert rec.score < before - 10

    def test_history_appended(self, mgr):
        mgr.get_or_create(ADDR_A)
        mgr.record_event(ADDR_A, EventType.JOB_SUCCESS, job_id="j1")
        mgr.record_event(ADDR_A, EventType.JOB_FAILED, job_id="j2")
        rec = mgr.store.get(ADDR_A)
        assert len(rec.history) == 2

    def test_persistence(self, mgr):
        mgr.get_or_create(ADDR_A)
        mgr.record_event(ADDR_A, EventType.JOB_SUCCESS)
        score = mgr.get_score(ADDR_A)
        # Reload from same dir
        mgr2 = ReputationManager(mgr.store)
        assert mgr2.get_score(ADDR_A) == score


class TestTierSystem:

    def test_probation_for_new_worker(self, mgr):
        assert mgr.get_tier(ADDR_A) == "PROBATION"

    def test_tier_upgrades_with_jobs(self, mgr):
        mgr.get_or_create(ADDR_A)
        # Do 5 successful jobs to reach STANDARD
        for _ in range(5):
            mgr.record_event(ADDR_A, EventType.JOB_SUCCESS)
        rec = mgr.store.get(ADDR_A)
        assert rec.tier in ("STANDARD", "TRUSTED", "ELITE")

    def test_compute_tier_logic(self):
        assert compute_tier(0, 0) == "PROBATION"
        assert compute_tier(50, 5) == "STANDARD"
        assert compute_tier(70, 20) == "TRUSTED"
        assert compute_tier(90, 50) == "ELITE"

    def test_probation_has_price_limit(self, mgr):
        mgr.get_or_create(ADDR_A)
        assert mgr.can_take_job(ADDR_A, 100_000) is True
        assert mgr.can_take_job(ADDR_A, 999_999_999) is False

    def test_elite_has_no_price_limit(self, mgr):
        mgr.get_or_create(ADDR_A)
        # Simulate elite: set score and jobs manually
        rec = mgr.store.get(ADDR_A)
        rec.score = 95.0
        rec.total_jobs = 60
        rec.successful_jobs = 58
        rec.tier = "ELITE"
        mgr.store.put(rec)
        assert mgr.can_take_job(ADDR_A, 999_999_999) is True


class TestBanSystem:

    def test_ban_after_low_score_and_timeouts(self, mgr):
        mgr.get_or_create(ADDR_A)
        # Drive score very low with timeouts
        for _ in range(10):
            mgr.record_event(ADDR_A, EventType.TIMEOUT)
        rec = mgr.store.get(ADDR_A)
        assert rec.is_banned is True

    def test_banned_worker_cannot_take_job(self, mgr):
        mgr.get_or_create(ADDR_A)
        for _ in range(10):
            mgr.record_event(ADDR_A, EventType.TIMEOUT)
        assert mgr.can_take_job(ADDR_A, 1) is False

    def test_banned_worker_events_ignored(self, mgr):
        mgr.get_or_create(ADDR_A)
        for _ in range(10):
            mgr.record_event(ADDR_A, EventType.TIMEOUT)
        banned_score = mgr.get_score(ADDR_A)
        # Try to improve score after ban — should be ignored
        mgr.record_event(ADDR_A, EventType.JOB_SUCCESS)
        assert mgr.get_score(ADDR_A) == banned_score

    def test_unban_resets_score(self, mgr):
        mgr.get_or_create(ADDR_A)
        for _ in range(10):
            mgr.record_event(ADDR_A, EventType.TIMEOUT)
        mgr.unban(ADDR_A)
        rec = mgr.store.get(ADDR_A)
        assert rec.is_banned is False
        assert rec.score == INITIAL_SCORE

    def test_is_banned_check(self, mgr):
        mgr.get_or_create(ADDR_A)
        assert mgr.is_banned(ADDR_A) is False
        for _ in range(10):
            mgr.record_event(ADDR_A, EventType.TIMEOUT)
        assert mgr.is_banned(ADDR_A) is True


class TestLeaderboard:

    def test_leaderboard_sorted_by_score(self, mgr):
        mgr.get_or_create(ADDR_A)
        mgr.get_or_create(ADDR_B)
        for _ in range(5):
            mgr.record_event(ADDR_A, EventType.JOB_SUCCESS)
        board = mgr.leaderboard()
        assert board[0].address == ADDR_A

    def test_banned_excluded_from_leaderboard(self, mgr):
        mgr.get_or_create(ADDR_A)
        for _ in range(10):
            mgr.record_event(ADDR_A, EventType.TIMEOUT)
        board = mgr.leaderboard()
        assert all(r.address != ADDR_A for r in board)

    def test_success_rate_calculation(self, mgr):
        mgr.get_or_create(ADDR_A)
        mgr.record_event(ADDR_A, EventType.JOB_SUCCESS)
        mgr.record_event(ADDR_A, EventType.JOB_SUCCESS)
        mgr.record_event(ADDR_A, EventType.JOB_FAILED)
        rec = mgr.store.get(ADDR_A)
        assert abs(rec.success_rate - 2/3) < 0.01
