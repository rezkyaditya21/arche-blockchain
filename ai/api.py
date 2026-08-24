"""
ARCHE AI Network HTTP API

Endpoint untuk AI Jobs, Workers, Models, Agents, dan Marketplace.
Berjalan terpisah dari node.py — bisa di port berbeda.
"""
from __future__ import annotations

import os
from typing import Optional

from flask import Flask, jsonify, request

from ai.job import JobManager, JobStore, JobStatus, hash_input
from ai.worker import WorkerManager, WorkerStore, WorkerCapability
from ai.registry import ModelRegistry, ModelStore
from ai.payment import PaymentManager, PaymentStore
from ai.marketplace import AIMarketplace
from agents.registry import AgentRegistry, AgentStore


def create_ai_app(data_dir: str) -> Flask:
    app = Flask("arche-ai")
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

    # CORS
    @app.after_request
    def cors(r):
        r.headers["Access-Control-Allow-Origin"] = "*"
        r.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return r

    # Init stores & managers
    job_store     = JobStore(data_dir)
    worker_store  = WorkerStore(data_dir)
    model_store   = ModelStore(data_dir)
    payment_store = PaymentStore(data_dir)
    agent_store   = AgentStore(data_dir)

    job_mgr     = JobManager(job_store)
    worker_mgr  = WorkerManager(worker_store)
    model_reg   = ModelRegistry(model_store)
    payment_mgr = PaymentManager(payment_store)
    agent_reg   = AgentRegistry(agent_store)
    marketplace = AIMarketplace(model_reg, worker_mgr, job_mgr)

    # ── Health ──────────────────────────────────────────
    @app.get("/ai/health")
    def health():
        return jsonify(marketplace.get_stats())

    # ── Jobs ────────────────────────────────────────────
    @app.post("/ai/jobs")
    def create_job():
        d = request.get_json(force=True, silent=True) or {}
        required = ["requester", "model_id", "input_hash",
                    "input_reference", "max_price", "deadline"]
        missing = [k for k in required if k not in d]
        if missing:
            return jsonify({"error": f"Missing fields: {missing}"}), 400
        try:
            job = marketplace.submit_job(
                requester=d["requester"],
                model_id=d["model_id"],
                input_hash=d["input_hash"],
                input_reference=d["input_reference"],
                max_price=int(d["max_price"]),
                deadline=int(d["deadline"]),
                preferred_worker=d.get("preferred_worker"),
            )
            return jsonify(job.to_dict()), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    @app.get("/ai/jobs")
    def list_jobs():
        status = request.args.get("status")
        requester = request.args.get("requester")
        worker = request.args.get("worker")
        jobs = job_store.all()
        if status:
            try:
                jobs = [j for j in jobs if j.status == JobStatus(status)]
            except ValueError:
                return jsonify({"error": f"Invalid status: {status}"}), 400
        if requester:
            jobs = [j for j in jobs if j.requester == requester]
        if worker:
            jobs = [j for j in jobs if j.assigned_worker == worker]
        return jsonify({"jobs": [j.to_dict() for j in jobs], "count": len(jobs)})

    @app.get("/ai/jobs/<job_id>")
    def get_job(job_id: str):
        job = job_store.get(job_id)
        if not job:
            return jsonify({"error": "not found"}), 404
        return jsonify(job.to_dict())

    @app.post("/ai/jobs/<job_id>/result")
    def submit_result(job_id: str):
        d = request.get_json(force=True, silent=True) or {}
        try:
            job = job_mgr.submit_result(
                job_id=job_id,
                worker=d["worker"],
                result_hash=d["result_hash"],
                result_reference=d["result_reference"],
            )
            return jsonify(job.to_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    @app.post("/ai/jobs/<job_id>/verify")
    def verify_job(job_id: str):
        d = request.get_json(force=True, silent=True) or {}
        try:
            job = job_mgr.verify_job(
                job_id=job_id,
                verifier=d["verifier"],
                success=bool(d.get("success", False)),
                reason=d.get("reason", ""),
            )
            return jsonify(job.to_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    @app.post("/ai/jobs/<job_id>/cancel")
    def cancel_job(job_id: str):
        d = request.get_json(force=True, silent=True) or {}
        try:
            job = job_mgr.cancel_job(
                job_id=job_id,
                requester=d["requester"],
                reason=d.get("reason", ""),
            )
            return jsonify(job.to_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    # ── Workers ─────────────────────────────────────────
    @app.post("/ai/workers")
    def register_worker():
        d = request.get_json(force=True, silent=True) or {}
        required = ["address", "public_key", "endpoint", "price_per_job"]
        missing = [k for k in required if k not in d]
        if missing:
            return jsonify({"error": f"Missing: {missing}"}), 400
        try:
            cap_data = d.get("capability", {})
            if not cap_data:
                cap = WorkerCapability.detect_local()
            else:
                cap = WorkerCapability.from_dict(cap_data)
            worker = worker_mgr.register(
                address=d["address"],
                public_key=d["public_key"],
                endpoint=d["endpoint"],
                capability=cap,
                price_per_job=int(d["price_per_job"]),
            )
            return jsonify(worker.to_dict()), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    @app.get("/ai/workers")
    def list_workers():
        workers = worker_store.available()
        return jsonify({"workers": [w.to_dict() for w in workers],
                        "count": len(workers)})

    @app.get("/ai/workers/<worker_id>")
    def get_worker(worker_id: str):
        w = worker_store.get(worker_id)
        if not w:
            return jsonify({"error": "not found"}), 404
        return jsonify(w.to_dict())

    @app.post("/ai/workers/<worker_id>/heartbeat")
    def worker_heartbeat(worker_id: str):
        try:
            w = worker_mgr.heartbeat(worker_id)
            return jsonify({"status": "ok", "last_seen": w.last_seen})
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    # ── Models ──────────────────────────────────────────
    @app.post("/ai/models")
    def register_model():
        d = request.get_json(force=True, silent=True) or {}
        required = ["owner", "name", "model_hash", "version",
                    "framework", "architecture", "task", "storage_reference"]
        missing = [k for k in required if k not in d]
        if missing:
            return jsonify({"error": f"Missing: {missing}"}), 400
        try:
            model = model_reg.register(
                owner=d["owner"],
                name=d["name"],
                model_hash=d["model_hash"],
                version=d["version"],
                framework=d["framework"],
                architecture=d["architecture"],
                task=d["task"],
                requirements=d.get("requirements", {}),
                storage_reference=d["storage_reference"],
                price_per_call=int(d.get("price_per_call", 0)),
                metadata=d.get("metadata", {}),
                tags=d.get("tags", []),
            )
            return jsonify(model.to_dict()), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    @app.get("/ai/models")
    def list_models():
        task = request.args.get("task")
        framework = request.args.get("framework")
        results = model_store.search(task=task, framework=framework)
        return jsonify({"models": [m.to_dict() for m in results],
                        "count": len(results)})

    @app.get("/ai/models/<model_id>")
    def get_model(model_id: str):
        m = model_store.get(model_id)
        if not m:
            return jsonify({"error": "not found"}), 404
        return jsonify(m.to_dict())

    # ── Marketplace ─────────────────────────────────────
    @app.get("/ai/marketplace")
    def marketplace_listings():
        listings = marketplace.get_listings()
        return jsonify({
            "listings": [
                {
                    "model": l.model.to_dict(),
                    "available_workers": len(l.available_workers),
                    "min_price": l.min_price,
                    "max_price": l.max_price,
                    "avg_reputation": l.avg_reputation,
                }
                for l in listings
            ],
            "count": len(listings),
        })

    @app.get("/ai/marketplace/quotes/<model_id>")
    def get_quotes(model_id: str):
        max_price = int(request.args.get("max_price", 999_999_999))
        try:
            quotes = marketplace.get_quotes(model_id, max_price)
            return jsonify({
                "quotes": [
                    {
                        "worker_id": q.worker.worker_id,
                        "worker_address": q.worker.address,
                        "price": q.price,
                        "reputation": q.reputation_score,
                        "endpoint": q.worker.endpoint,
                    }
                    for q in quotes
                ],
                "count": len(quotes),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    # ── Payments ────────────────────────────────────────
    @app.post("/ai/payments/escrow")
    def create_escrow():
        d = request.get_json(force=True, silent=True) or {}
        required = ["job_id", "requester", "worker",
                    "amount", "lock_txid", "expires_at"]
        missing = [k for k in required if k not in d]
        if missing:
            return jsonify({"error": f"Missing: {missing}"}), 400
        try:
            record = payment_mgr.create_escrow(
                job_id=d["job_id"],
                requester=d["requester"],
                worker=d["worker"],
                amount=int(d["amount"]),
                lock_txid=d["lock_txid"],
                expires_at=int(d["expires_at"]),
            )
            return jsonify(record.to_dict()), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    @app.post("/ai/payments/<job_id>/release")
    def release_payment(job_id: str):
        d = request.get_json(force=True, silent=True) or {}
        try:
            record = payment_mgr.release_to_worker(
                job_id=job_id,
                release_txid=d["release_txid"],
                authorized_by=d["authorized_by"],
            )
            return jsonify(record.to_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    @app.get("/ai/payments/<job_id>")
    def get_payment(job_id: str):
        record = payment_mgr.get_escrow(job_id)
        if not record:
            return jsonify({"error": "not found"}), 404
        return jsonify(record.to_dict())

    from ai.verification import (
        VerificationManager, VerificationPolicy, VerificationLevel,
        WorkerSubmission,
    )
    verif_mgr = VerificationManager(VerificationPolicy(
        min_level=VerificationLevel.HASH,
        require_redundant_workers=3,
        enable_pol=False,
    ))
    # In-memory redundant submission pools per job
    _redundant_pools: dict = {}

    # ── Verification ────────────────────────────────────
    @app.post("/ai/verify/hash")
    def verify_hash():
        d = request.get_json(force=True, silent=True) or {}
        required = ["job_id", "result_hash", "expected_hash"]
        missing = [k for k in required if k not in d]
        if missing:
            return jsonify({"error": f"Missing: {missing}"}), 400
        rec = verif_mgr.verify_hash(
            job_id=d["job_id"],
            result_hash=d["result_hash"],
            expected_hash=d["expected_hash"],
            verifier=d.get("verifier", "system"),
        )
        return jsonify(rec.to_dict())

    @app.post("/ai/verify/redundant/submit")
    def redundant_submit():
        d = request.get_json(force=True, silent=True) or {}
        required = ["job_id", "worker", "result_hash"]
        missing = [k for k in required if k not in d]
        if missing:
            return jsonify({"error": f"Missing: {missing}"}), 400
        job_id = d["job_id"]
        if job_id not in _redundant_pools:
            _redundant_pools[job_id] = []
        try:
            verif_mgr.redundant_verifier.add_submission(
                _redundant_pools[job_id], d["worker"], d["result_hash"]
            )
            return jsonify({
                "status": "submitted",
                "submissions": len(_redundant_pools[job_id]),
                "required": verif_mgr.redundant_verifier.MIN_WORKERS,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    @app.post("/ai/verify/redundant/evaluate")
    def redundant_evaluate():
        d = request.get_json(force=True, silent=True) or {}
        job_id = d.get("job_id")
        if not job_id:
            return jsonify({"error": "Missing job_id"}), 400
        submissions = _redundant_pools.get(job_id, [])
        rec, winner = verif_mgr.evaluate_redundant(
            job_id, submissions, d.get("verifier", "system")
        )
        return jsonify({"record": rec.to_dict(), "winning_hash": winner})

    @app.post("/ai/verify/challenge")
    def open_challenge():
        d = request.get_json(force=True, silent=True) or {}
        required = ["job_id", "challenger", "worker", "reason"]
        missing = [k for k in required if k not in d]
        if missing:
            return jsonify({"error": f"Missing: {missing}"}), 400
        try:
            c = verif_mgr.open_challenge(
                d["job_id"], d["challenger"], d["worker"], d["reason"]
            )
            return jsonify(c.to_dict()), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    @app.post("/ai/verify/logits")
    def verify_logits():
        d = request.get_json(force=True, silent=True) or {}
        required = ["job_id", "submitted_logits", "reference_logits"]
        missing = [k for k in required if k not in d]
        if missing:
            return jsonify({"error": f"Missing: {missing}"}), 400
        rec = verif_mgr.verify_logits(
            job_id=d["job_id"],
            submitted_logits=d["submitted_logits"],
            reference_logits=d["reference_logits"],
            verifier=d.get("verifier", "system"),
        )
        return jsonify(rec.to_dict())
    @app.post("/ai/agents")
    def register_agent():
        d = request.get_json(force=True, silent=True) or {}
        required = ["owner", "name", "public_key", "address"]
        missing = [k for k in required if k not in d]
        if missing:
            return jsonify({"error": f"Missing: {missing}"}), 400
        try:
            from agents.registry import AgentCapability
            cap_data = d.get("capabilities", {})
            cap = AgentCapability.from_dict(cap_data) if cap_data else AgentCapability()
            agent = agent_reg.register(
                owner=d["owner"],
                name=d["name"],
                public_key=d["public_key"],
                address=d["address"],
                capabilities=cap,
                metadata=d.get("metadata", {}),
                tags=d.get("tags", []),
            )
            return jsonify(agent.to_dict()), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    @app.get("/ai/agents")
    def list_agents():
        owner = request.args.get("owner")
        agents = agent_store.active()
        if owner:
            agents = [a for a in agents if a.owner == owner]
        return jsonify({"agents": [a.to_dict() for a in agents],
                        "count": len(agents)})

    @app.get("/ai/agents/<agent_id>")
    def get_agent(agent_id: str):
        a = agent_store.get(agent_id)
        if not a:
            return jsonify({"error": "not found"}), 404
        return jsonify(a.to_dict())

    return app


def main() -> None:
    import argparse, logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    p = argparse.ArgumentParser(description="ARCHE AI Network API")
    p.add_argument("--data", default="./arc-data")
    p.add_argument("--port", type=int, default=9444)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()

    app = create_ai_app(args.data)
    try:
        from waitress import serve
        logging.info("ARCHE AI API on http://%s:%d", args.host, args.port)
        serve(app, host=args.host, port=args.port, threads=4)
    except ImportError:
        app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
