"""
ARCHE AI Network — Test Suite
Tests for Phase 1-6: Jobs, Workers, Models, Payments, Agents, Marketplace
"""
import sys, os, json, time, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ai.job import AIJob, JobManager, JobStore, JobStatus, PaymentStatus, hash_input
from ai.worker import AIWorker, WorkerManager, WorkerStore, WorkerCapability, WorkerStatus
from ai.registry import AIModel, ModelRegistry, ModelStore
from ai.payment import PaymentManager, PaymentStore, EscrowStatus
from ai.marketplace import AIMarketplace
from agents.registry import AgentRegistry, AgentStore, AgentCapability, AgentStatus


# ── Fixtures ──────────────────────────────────────────

@pytest.fixture
def tmpdir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)

@pytest.fixture
def job_mgr(tmpdir):
    return JobManager(JobStore(tmpdir))

@pytest.fixture
def worker_mgr(tmpdir):
    return WorkerManager(WorkerStore(tmpdir))

@pytest.fixture
def model_reg(tmpdir):
    return ModelRegistry(ModelStore(tmpdir))

@pytest.fixture
def payment_mgr(tmpdir):
    return PaymentManager(PaymentStore(tmpdir))

@pytest.fixture
def agent_reg(tmpdir):
    return AgentRegistry(AgentStore(tmpdir))

@pytest.fixture
def marketplace(tmpdir):
    ms = ModelStore(tmpdir)
    ws = WorkerStore(tmpdir)
    js = JobStore(tmpdir)
    return AIMarketplace(ModelRegistry(ms), WorkerManager(ws), JobManager(js))

ADDR_USER   = "aa" * 20
ADDR_WORKER = "bb" * 20
ADDR_AGENT  = "cc" * 20
PUBKEY      = "03" + "ab" * 32
VALID_HASH  = "a" * 64
VALID_TXID  = "b" * 64


# ── Phase 1: AI Job System ────────────────────────────

class TestAIJobSystem:

    def test_create_job(self, job_mgr):
        job = job_mgr.create_job(
            requester=ADDR_USER,
            model_id="model-1",
            input_hash=VALID_HASH,
            input_reference="ipfs://Qm...",
            compute_requirement={"gpu": False},
            max_price=1000,
            deadline=int(time.time()) + 3600,
        )
        assert job.status == JobStatus.PENDING
        assert job.requester == ADDR_USER
        assert len(job.job_id) > 0

    def test_create_job_invalid_price(self, job_mgr):
        with pytest.raises(ValueError):
            job_mgr.create_job(
                requester=ADDR_USER, model_id="m", input_hash=VALID_HASH,
                input_reference="", compute_requirement={},
                max_price=0, deadline=int(time.time()) + 3600,
            )

    def test_create_job_expired_deadline(self, job_mgr):
        with pytest.raises(ValueError):
            job_mgr.create_job(
                requester=ADDR_USER, model_id="m", input_hash=VALID_HASH,
                input_reference="", compute_requirement={},
                max_price=100, deadline=int(time.time()) - 1,
            )

    def test_full_job_lifecycle(self, job_mgr):
        job = job_mgr.create_job(
            requester=ADDR_USER, model_id="m", input_hash=VALID_HASH,
            input_reference="ipfs://x", compute_requirement={},
            max_price=1000, deadline=int(time.time()) + 3600,
        )
        # Assign
        job = job_mgr.assign_job(job.job_id, ADDR_WORKER, agreed_price=500)
        assert job.status == JobStatus.ASSIGNED
        assert job.assigned_worker == ADDR_WORKER

        # Start
        job = job_mgr.start_job(job.job_id, ADDR_WORKER)
        assert job.status == JobStatus.RUNNING

        # Submit result
        job = job_mgr.submit_result(
            job.job_id, ADDR_WORKER, VALID_HASH, "ipfs://result"
        )
        assert job.status == JobStatus.VERIFYING

        # Verify success
        job = job_mgr.verify_job(job.job_id, ADDR_USER, success=True)
        assert job.status == JobStatus.COMPLETED

    def test_job_cancel_by_requester(self, job_mgr):
        job = job_mgr.create_job(
            requester=ADDR_USER, model_id="m", input_hash=VALID_HASH,
            input_reference="", compute_requirement={},
            max_price=100, deadline=int(time.time()) + 3600,
        )
        job = job_mgr.cancel_job(job.job_id, ADDR_USER, "changed mind")
        assert job.status == JobStatus.CANCELLED

    def test_cancel_by_wrong_user_fails(self, job_mgr):
        job = job_mgr.create_job(
            requester=ADDR_USER, model_id="m", input_hash=VALID_HASH,
            input_reference="", compute_requirement={},
            max_price=100, deadline=int(time.time()) + 3600,
        )
        with pytest.raises(ValueError):
            job_mgr.cancel_job(job.job_id, ADDR_WORKER)

    def test_assign_over_max_price_fails(self, job_mgr):
        job = job_mgr.create_job(
            requester=ADDR_USER, model_id="m", input_hash=VALID_HASH,
            input_reference="", compute_requirement={},
            max_price=100, deadline=int(time.time()) + 3600,
        )
        with pytest.raises(ValueError):
            job_mgr.assign_job(job.job_id, ADDR_WORKER, agreed_price=200)

    def test_wrong_worker_cannot_start(self, job_mgr):
        job = job_mgr.create_job(
            requester=ADDR_USER, model_id="m", input_hash=VALID_HASH,
            input_reference="", compute_requirement={},
            max_price=100, deadline=int(time.time()) + 3600,
        )
        job_mgr.assign_job(job.job_id, ADDR_WORKER, 50)
        with pytest.raises(ValueError):
            job_mgr.start_job(job.job_id, "wrong_worker")

    def test_verify_fail_sets_disputed(self, job_mgr):
        job = job_mgr.create_job(
            requester=ADDR_USER, model_id="m", input_hash=VALID_HASH,
            input_reference="", compute_requirement={},
            max_price=100, deadline=int(time.time()) + 3600,
        )
        job_mgr.assign_job(job.job_id, ADDR_WORKER, 50)
        job_mgr.start_job(job.job_id, ADDR_WORKER)
        job_mgr.submit_result(job.job_id, ADDR_WORKER, VALID_HASH, "ipfs://r")
        job = job_mgr.verify_job(job.job_id, ADDR_USER, success=False, reason="Wrong output")
        assert job.status == JobStatus.DISPUTED

    def test_escrow_recorded(self, job_mgr):
        job = job_mgr.create_job(
            requester=ADDR_USER, model_id="m", input_hash=VALID_HASH,
            input_reference="", compute_requirement={},
            max_price=100, deadline=int(time.time()) + 3600,
        )
        job = job_mgr.set_escrow(job.job_id, VALID_TXID)
        assert job.payment_status == PaymentStatus.ESCROWED
        assert job.escrow_txid == VALID_TXID

    def test_hash_input(self):
        h = hash_input(b"hello world")
        assert len(h) == 64

    def test_job_persistence(self, tmpdir):
        store = JobStore(tmpdir)
        mgr = JobManager(store)
        job = mgr.create_job(
            requester=ADDR_USER, model_id="m", input_hash=VALID_HASH,
            input_reference="", compute_requirement={},
            max_price=100, deadline=int(time.time()) + 3600,
        )
        job_id = job.job_id
        # Reload store
        store2 = JobStore(tmpdir)
        loaded = store2.get(job_id)
        assert loaded is not None
        assert loaded.requester == ADDR_USER


# ── Phase 2: AI Worker ────────────────────────────────

class TestAIWorker:

    def _cap(self):
        return WorkerCapability(
            cpu_cores=4, ram_gb=8.0, has_gpu=False,
            gpu_name=None, gpu_vram_gb=None,
            supported_frameworks=["onnx"],
            supported_models=[],
            max_concurrent_jobs=1,
            bandwidth_mbps=100.0,
            os_info="Linux",
        )

    def test_register_worker(self, worker_mgr):
        w = worker_mgr.register(
            address=ADDR_WORKER, public_key=PUBKEY,
            endpoint="127.0.0.1:8888",
            capability=self._cap(),
            price_per_job=100,
        )
        assert w.status == WorkerStatus.ACTIVE
        assert w.address == ADDR_WORKER

    def test_register_updates_existing(self, worker_mgr):
        worker_mgr.register(ADDR_WORKER, PUBKEY, "127.0.0.1:8888", self._cap(), 100)
        w2 = worker_mgr.register(ADDR_WORKER, PUBKEY, "127.0.0.1:9999", self._cap(), 200)
        assert w2.endpoint == "127.0.0.1:9999"
        assert w2.price_per_job == 200

    def test_heartbeat(self, worker_mgr):
        w = worker_mgr.register(ADDR_WORKER, PUBKEY, "127.0.0.1:8888", self._cap(), 100)
        time.sleep(0.01)
        w2 = worker_mgr.heartbeat(w.worker_id)
        assert w2.last_seen >= w.last_seen

    def test_assign_job(self, worker_mgr):
        w = worker_mgr.register(ADDR_WORKER, PUBKEY, "127.0.0.1:8888", self._cap(), 100)
        w = worker_mgr.assign_job(w.worker_id, "job-1")
        assert w.status == WorkerStatus.BUSY
        assert w.current_job == "job-1"

    def test_assign_busy_worker_fails(self, worker_mgr):
        w = worker_mgr.register(ADDR_WORKER, PUBKEY, "127.0.0.1:8888", self._cap(), 100)
        worker_mgr.assign_job(w.worker_id, "job-1")
        with pytest.raises(ValueError):
            worker_mgr.assign_job(w.worker_id, "job-2")

    def test_complete_job_updates_reputation(self, worker_mgr):
        w = worker_mgr.register(ADDR_WORKER, PUBKEY, "127.0.0.1:8888", self._cap(), 100)
        worker_mgr.assign_job(w.worker_id, "job-1")
        w = worker_mgr.complete_job(w.worker_id, success=True, earned=500)
        assert w.completed_jobs == 1
        assert w.total_earned == 500
        assert w.status == WorkerStatus.ACTIVE

    def test_failed_job_reduces_reputation(self, worker_mgr):
        w = worker_mgr.register(ADDR_WORKER, PUBKEY, "127.0.0.1:8888", self._cap(), 100)
        worker_mgr.assign_job(w.worker_id, "job-1")
        w = worker_mgr.complete_job(w.worker_id, success=False)
        assert w.failed_jobs == 1
        assert w.reputation_score < 100.0

    def test_can_handle_no_gpu_job(self):
        cap = self._cap()
        w = AIWorker(
            worker_id="w1", address=ADDR_WORKER, public_key=PUBKEY,
            endpoint="", capability=cap, price_per_job=100,
            registered_at=0, last_seen=int(time.time()),
        )
        assert w.can_handle({"gpu": False, "min_ram_gb": 4})
        assert not w.can_handle({"gpu": True})

    def test_find_suitable_workers(self, worker_mgr):
        worker_mgr.register(ADDR_WORKER, PUBKEY, "127.0.0.1:8888", self._cap(), 100)
        workers = worker_mgr.find_suitable_workers(
            compute_req={"gpu": False},
            max_price=200,
        )
        assert len(workers) == 1


# ── Phase 3: ARC Payment ──────────────────────────────

class TestARCPayment:

    def test_create_escrow(self, payment_mgr):
        r = payment_mgr.create_escrow(
            job_id="job-1", requester=ADDR_USER,
            worker=ADDR_WORKER, amount=1000,
            lock_txid=VALID_TXID,
            expires_at=int(time.time()) + 3600,
        )
        assert r.status == EscrowStatus.LOCKED
        assert r.amount == 1000

    def test_duplicate_escrow_fails(self, payment_mgr):
        payment_mgr.create_escrow(
            "job-1", ADDR_USER, ADDR_WORKER, 1000,
            VALID_TXID, int(time.time()) + 3600,
        )
        with pytest.raises(ValueError):
            payment_mgr.create_escrow(
                "job-1", ADDR_USER, ADDR_WORKER, 500,
                "c" * 64, int(time.time()) + 3600,
            )

    def test_release_to_worker(self, payment_mgr):
        r = payment_mgr.create_escrow(
            "job-1", ADDR_USER, ADDR_WORKER, 1000,
            VALID_TXID, int(time.time()) + 3600,
        )
        r = payment_mgr.release_to_worker("job-1", "d" * 64, ADDR_USER)
        assert r.status == EscrowStatus.RELEASED

    def test_double_payment_prevented(self, payment_mgr):
        payment_mgr.create_escrow(
            "job-1", ADDR_USER, ADDR_WORKER, 1000,
            VALID_TXID, int(time.time()) + 3600,
        )
        payment_mgr.release_to_worker("job-1", "d" * 64, ADDR_USER)
        with pytest.raises(ValueError):
            payment_mgr.release_to_worker("job-1", "e" * 64, ADDR_USER)

    def test_refund_to_requester(self, payment_mgr):
        payment_mgr.create_escrow(
            "job-1", ADDR_USER, ADDR_WORKER, 1000,
            VALID_TXID, int(time.time()) + 3600,
        )
        r = payment_mgr.refund_to_requester("job-1", "f" * 64, "job cancelled")
        assert r.status == EscrowStatus.REFUNDED

    def test_unauthorized_release_fails(self, payment_mgr):
        payment_mgr.create_escrow(
            "job-1", ADDR_USER, ADDR_WORKER, 1000,
            VALID_TXID, int(time.time()) + 3600,
        )
        with pytest.raises(ValueError):
            payment_mgr.release_to_worker("job-1", "d" * 64, "random_addr")

    def test_open_dispute(self, payment_mgr):
        payment_mgr.create_escrow(
            "job-1", ADDR_USER, ADDR_WORKER, 1000,
            VALID_TXID, int(time.time()) + 3600,
        )
        r = payment_mgr.open_dispute("job-1", "Worker sent wrong result")
        assert r.status == EscrowStatus.DISPUTED

    def test_worker_earnings(self, payment_mgr):
        payment_mgr.create_escrow("j1", ADDR_USER, ADDR_WORKER, 500, VALID_TXID, int(time.time())+3600)
        payment_mgr.create_escrow("j2", ADDR_USER, ADDR_WORKER, 300, "c"*64, int(time.time())+3600)
        payment_mgr.release_to_worker("j1", "d"*64, ADDR_USER)
        payment_mgr.release_to_worker("j2", "e"*64, ADDR_USER)
        assert payment_mgr.worker_earnings(ADDR_WORKER) == 800


# ── Phase 4: Model Registry ───────────────────────────

class TestModelRegistry:

    def test_register_model(self, model_reg):
        m = model_reg.register(
            owner=ADDR_USER, name="TestModel",
            model_hash=VALID_HASH, version="1.0.0",
            framework="onnx", architecture="transformer",
            task="text-generation",
            requirements={"gpu": False},
            storage_reference="ipfs://Qm...",
        )
        assert m.owner == ADDR_USER
        assert m.is_active

    def test_invalid_model_hash_fails(self, model_reg):
        with pytest.raises(ValueError):
            model_reg.register(
                owner=ADDR_USER, name="Bad",
                model_hash="not_64_chars",
                version="1.0", framework="onnx",
                architecture="cnn", task="classification",
                requirements={}, storage_reference="",
            )

    def test_search_by_task(self, model_reg):
        model_reg.register(ADDR_USER, "M1", VALID_HASH, "1.0", "onnx",
                           "cnn", "classification", {}, "ipfs://1")
        model_reg.register(ADDR_USER, "M2", "b"*64, "1.0", "onnx",
                           "transformer", "text-generation", {}, "ipfs://2")
        results = model_reg.store.search(task="classification")
        assert len(results) == 1
        assert results[0].name == "M1"

    def test_deactivate_model(self, model_reg):
        m = model_reg.register(ADDR_USER, "M1", VALID_HASH, "1.0",
                               "onnx", "cnn", "cls", {}, "ipfs://x")
        model_reg.deactivate(m.model_id, ADDR_USER)
        m2 = model_reg.store.get(m.model_id)
        assert not m2.is_active

    def test_only_owner_can_deactivate(self, model_reg):
        m = model_reg.register(ADDR_USER, "M1", VALID_HASH, "1.0",
                               "onnx", "cnn", "cls", {}, "ipfs://x")
        with pytest.raises(ValueError):
            model_reg.deactivate(m.model_id, ADDR_WORKER)


# ── Phase 5: Marketplace ──────────────────────────────

class TestMarketplace:

    def _setup(self, marketplace):
        # Register model
        model = marketplace.models.register(
            owner=ADDR_USER, name="TestModel",
            model_hash=VALID_HASH, version="1.0",
            framework="onnx", architecture="transformer",
            task="text-generation",
            requirements={"gpu": False, "min_ram_gb": 2},
            storage_reference="ipfs://x",
            price_per_call=10,
        )
        # Register worker
        cap = WorkerCapability(
            cpu_cores=4, ram_gb=8.0, has_gpu=False,
            gpu_name=None, gpu_vram_gb=None,
            supported_frameworks=["onnx"],
            supported_models=[], max_concurrent_jobs=1,
            bandwidth_mbps=None, os_info="Linux",
        )
        worker = marketplace.workers.register(
            address=ADDR_WORKER, public_key=PUBKEY,
            endpoint="127.0.0.1:8888",
            capability=cap, price_per_job=100,
        )
        return model, worker

    def test_get_quotes(self, marketplace):
        model, _ = self._setup(marketplace)
        quotes = marketplace.get_quotes(model.model_id, max_price=200)
        assert len(quotes) == 1
        assert quotes[0].price == 110  # 100 worker + 10 model

    def test_get_listings(self, marketplace):
        self._setup(marketplace)
        listings = marketplace.get_listings()
        assert len(listings) == 1

    def test_submit_job_auto_assigns(self, marketplace):
        model, _ = self._setup(marketplace)
        job = marketplace.submit_job(
            requester=ADDR_USER,
            model_id=model.model_id,
            input_hash=VALID_HASH,
            input_reference="ipfs://input",
            max_price=500,
            deadline=int(time.time()) + 3600,
        )
        assert job.assigned_worker == ADDR_WORKER
        assert job.status.value in ("ASSIGNED", "PENDING")

    def test_get_stats(self, marketplace):
        self._setup(marketplace)
        stats = marketplace.get_stats()
        assert stats["total_models"] >= 1
        assert stats["total_workers"] >= 1


# ── Phase 6: AI Agents ────────────────────────────────

class TestAIAgents:

    def test_register_agent(self, agent_reg):
        a = agent_reg.register(
            owner=ADDR_USER, name="MyAgent",
            public_key=PUBKEY, address=ADDR_AGENT,
        )
        assert a.status == AgentStatus.ACTIVE
        assert a.owner == ADDR_USER
        assert a.address == ADDR_AGENT

    def test_duplicate_address_fails(self, agent_reg):
        agent_reg.register(ADDR_USER, "A1", PUBKEY, ADDR_AGENT)
        with pytest.raises(ValueError):
            agent_reg.register(ADDR_USER, "A2", PUBKEY, ADDR_AGENT)

    def test_update_memory(self, agent_reg):
        a = agent_reg.register(ADDR_USER, "A", PUBKEY, ADDR_AGENT)
        a = agent_reg.update_memory(a.agent_id, ADDR_USER, VALID_HASH, "ipfs://mem")
        assert a.memory_ref is not None
        assert a.memory_ref.memory_hash == VALID_HASH
        assert a.memory_ref.version == 1

    def test_memory_version_increments(self, agent_reg):
        a = agent_reg.register(ADDR_USER, "A", PUBKEY, ADDR_AGENT)
        agent_reg.update_memory(a.agent_id, ADDR_USER, VALID_HASH, "ipfs://v1")
        a = agent_reg.update_memory(a.agent_id, ADDR_USER, "b"*64, "ipfs://v2")
        assert a.memory_ref.version == 2

    def test_only_owner_updates_memory(self, agent_reg):
        a = agent_reg.register(ADDR_USER, "A", PUBKEY, ADDR_AGENT)
        with pytest.raises(ValueError):
            agent_reg.update_memory(a.agent_id, ADDR_WORKER, VALID_HASH, "ipfs://x")

    def test_deactivate_agent(self, agent_reg):
        a = agent_reg.register(ADDR_USER, "A", PUBKEY, ADDR_AGENT)
        agent_reg.deactivate(a.agent_id, ADDR_USER)
        a2 = agent_reg.store.get(a.agent_id)
        assert a2.status == AgentStatus.INACTIVE

    def test_record_job_stats(self, agent_reg):
        a = agent_reg.register(ADDR_USER, "A", PUBKEY, ADDR_AGENT)
        agent_reg.record_job_request(a.agent_id, spent=500)
        agent_reg.record_job_completed(a.agent_id, earned=200)
        a2 = agent_reg.store.get(a.agent_id)
        assert a2.total_jobs_requested == 1
        assert a2.total_spent == 500
        assert a2.total_jobs_completed == 1
        assert a2.total_earned == 200
