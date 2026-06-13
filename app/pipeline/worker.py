import io
from datetime import datetime

import redis
from rq import Queue

from app.config import settings
from app.database import SessionLocal
from app.models import Job, Transaction, JobSummary
from app.pipeline.cleaner import clean_csv
from app.pipeline.anomalies import detect_anomalies
from app.pipeline.llm_client import classify_transactions, generate_summary

redis_conn = redis.from_url(settings.REDIS_URL)
queue = Queue(connection=redis_conn)


def enqueue_processing(job_id: str, csv_content: str):
    queue.enqueue(process_job, job_id, csv_content)


def process_job(job_id: str, csv_content: str):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return

        job.status = "processing"
        db.commit()

        raw_rows = csv_content.strip().split("\n")
        job.row_count_raw = len(raw_rows) - 1
        db.commit()

        cleaned = clean_csv(csv_content)
        job.row_count_clean = len(cleaned)
        db.commit()

        cleaned = detect_anomalies(cleaned)

        cleaned = classify_transactions(cleaned)

        anomaly_count = sum(1 for r in cleaned if r.get("is_anomaly"))

        summary = generate_summary(cleaned, anomaly_count)

        for r in cleaned:
            txn = Transaction(
                job_id=job_id,
                txn_id=r.get("txn_id"),
                date=r.get("date"),
                merchant=r.get("merchant"),
                amount=r.get("amount"),
                currency=r.get("currency"),
                status=r.get("status"),
                category=r.get("category"),
                account_id=r.get("account_id"),
                notes=r.get("notes"),
                is_anomaly=r.get("is_anomaly", False),
                anomaly_reason=r.get("anomaly_reason"),
                llm_category=r.get("llm_category"),
                llm_raw_response=r.get("llm_raw_response"),
                llm_failed=r.get("llm_failed", False),
            )
            db.add(txn)

        job_summary = JobSummary(
            job_id=job_id,
            total_spend_inr=summary.get("total_spend_inr", 0.0) if summary else 0.0,
            total_spend_usd=summary.get("total_spend_usd", 0.0) if summary else 0.0,
            top_merchants=summary.get("top_merchants", []) if summary else [],
            anomaly_count=anomaly_count,
            narrative=summary.get("narrative") if summary else "Summary generation failed.",
            risk_level=summary.get("risk_level", "low") if summary else "low",
        )
        db.add(job_summary)

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
