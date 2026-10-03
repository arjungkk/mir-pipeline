from celery import Celery
import redis as redis_lib
import json
import uuid
import logging
from pathlib import Path
from pydantic import ValidationError
from shared import FeatureRecord

celery_app = Celery('mir_pipeline', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
r = redis_lib.Redis(host='localhost', port=6379, decode_responses=True)
logger = logging.getLogger("tasks")

PROCESSED_DIR = Path(__file__).parent / "processed"
PROCESSED_DIR.mkdir(exist_ok=True)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def finalize_batch(batch_id: str):
    """Check if all files in the batch are processed; update the status and write on disk."""
    job_key = f"job:{batch_id}"
    results_list_key = f"job_results:{batch_id}"

    raw_results = r.lrange(results_list_key, 0, -1)

    try:
        results_path = RESULTS_DIR / f"{batch_id}.json"
        with open(results_path, "w") as f:
            f.write("[" + ",".join(raw_results) + "]")
        r.delete(results_list_key)
        r.hset(job_key, "status", "completed")
    except OSError as e:
        logger.error(f"Failed to write results for batch {batch_id}: {e}")
        r.hset(job_key, "status", "completed_with_errors")


@celery_app.task
def process_one_task(batch_id: str, filename: str, content: bytes):
    """Blocking work: parse, validate, write. Runs in a worker process."""
    job_key = f"job:{batch_id}"
    results_list_key = f"job_results:{batch_id}"

    try:
        data = json.loads(content)
        record = FeatureRecord(**data)
        raw_id = record.metadata["tags"]["musicbrainz_recordingid"][0]
        recording_id = str(uuid.UUID(raw_id))
        with open(PROCESSED_DIR / f"{recording_id}.json", "w") as f:
            json.dump(data, f)
        outcome = {"status": "accepted", "recording_id": recording_id}
    except (json.JSONDecodeError, ValidationError, KeyError, IndexError, ValueError) as e:
        outcome = {"status": "rejected", "file": filename, "error": f"invalid file: {e}"}
    except Exception as e:
        outcome = {"status": "rejected", "file": filename, "error": "internal error"}

    # Update the processed count in Redis
    r.rpush(results_list_key, json.dumps(outcome))
    new_count = r.hincrby(job_key, "processed_count", 1)

    total_files = int(r.hget(job_key, "total_files"))
    if new_count == total_files:
        finalize_batch(batch_id)

    return outcome