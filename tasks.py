from celery import Celery
import redis as redis_lib
import json
import uuid
from pathlib import Path
from pydantic import BaseModel, ValidationError
from typing import Dict, Any

celery_app = Celery('mir_pipeline', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
r = redis_lib.Redis(host='localhost', port=6379, decode_responses=True)

PROCESSED_DIR = Path(__file__).parent / "processed"
PROCESSED_DIR.mkdir(exist_ok=True)

class FeatureRecord(BaseModel):
    lowlevel: Dict[str, Any]
    rhythm: Dict[str, Any]
    tonal: Dict[str, Any]
    metadata: Dict[str, Any]

@celery_app.task
def process_one_task(batch_id: str, filename: str, content: bytes):
    """Blocking work: parse, validate, write. Runs in a worker process."""
    job_key = f"job:{batch_id}"
    try:
        data = json.loads(content)
        record = FeatureRecord(**data)
        raw_id = record.metadata["tags"]["musicbrainz_recordingid"][0]
        recording_id = str(uuid.UUID(raw_id))
        with open(PROCESSED_DIR / f"{recording_id}.json", "w") as f:
            json.dump(data, f)
        result = ("accepted", recording_id)
    except (json.JSONDecodeError, ValidationError, KeyError, IndexError, ValueError) as e:
        result = ("rejected", {"file": filename, "error": f"invalid file: {e}"})
    except Exception as e:
        result = ("rejected", {"file": filename, "error": "internal error"})
   
    # Update the processed count in Redis
    r.hincrby(job_key, "processed_count", 1)
    return result