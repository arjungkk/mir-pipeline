from fastapi import FastAPI, HTTPException, UploadFile
from typing import List
from pathlib import Path
import redis as redis_lib
import json
import uuid
import asyncio

from shared import FeatureRecord
from tasks import process_one_task

app = FastAPI()
r = redis_lib.Redis(host='localhost', port=6379, decode_responses=True)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

MAX_BATCH_SIZE = 500

def dispatch_all(batch_id: str, files_content: list[tuple[str, bytes]]):
    for filename, content in files_content:
        process_one_task.delay(batch_id, filename, content)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
async def ingest_batch(files: List[UploadFile]):
    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(status_code=429, detail=f"Batch size exceeds maximum of {MAX_BATCH_SIZE}")

    batch_id = str(uuid.uuid4())
    job_key = f"job:{batch_id}"
    r.hset(job_key, mapping={
        "status": "processing",
        "total_files": len(files),
        "processed_count": 0
    })

    files_content = [(f.filename, await f.read()) for f in files]
    await asyncio.to_thread(dispatch_all, batch_id, files_content)
    
    return {"batch_id": batch_id}


@app.get("/jobs/{batch_id}")
def get_job_status(batch_id: str):
    """Get the status of a batch job."""
    job_key = f"job:{batch_id}"
    job_data = r.hgetall(job_key)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")

    total_files = int(job_data.get("total_files", 0))
    processed_count = int(job_data.get("processed_count", 0))

    response = {
        "batch_id": batch_id,
        "status": job_data.get("status"),
        "total_files": total_files,
        "processed_count": processed_count
    }

    response["results_url"] = f"/jobs/{batch_id}/results"

    return response


@app.get("/jobs/{batch_id}/results")
def get_job_results(batch_id: str):
    """Get the results of a completed batch job."""
    job_key = f"job:{batch_id}"
    job_data = r.hgetall(job_key)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")

    results_path = RESULTS_DIR / f"{batch_id}.json"
    if not results_path.exists():
        raise HTTPException(status_code=404, detail="Results not available yet")

    with open(results_path, "r") as f:
        results = json.load(f)

    return {"batch_id": batch_id, "results": results}

