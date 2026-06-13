from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Job, Transaction, JobSummary
from app.schemas import (
    UploadResponse, JobStatusOut, JobResultsOut,
    TransactionOut, JobSummaryOut
)
from app.pipeline.worker import enqueue_processing

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files are accepted")

    content = await file.read()
    csv_text = content.decode("utf-8-sig")

    job = Job(filename=file.filename)
    db.add(job)
    db.commit()
    db.refresh(job)

    enqueue_processing(job.id, csv_text)

    return UploadResponse(
        job_id=job.id,
        filename=job.filename,
        status=job.status,
    )


@router.get("", response_model=list[JobStatusOut])
async def list_jobs(
    status: str = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
    jobs = query.order_by(Job.created_at.desc()).all()
    return jobs


@router.get("/{job_id}/status", response_model=JobStatusOut)
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/{job_id}/results", response_model=JobResultsOut)
async def get_job_results(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    if job.status not in ("completed", "failed"):
        raise HTTPException(400, f"Job is still {job.status}. Wait for completion.")

    return JobResultsOut(
        job_id=job.id,
        filename=job.filename,
        status=job.status,
        row_count_raw=job.row_count_raw,
        row_count_clean=job.row_count_clean,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
        transactions=[TransactionOut.model_validate(t) for t in job.transactions],
        summary=JobSummaryOut.model_validate(job.summary) if job.summary else None,
    )
