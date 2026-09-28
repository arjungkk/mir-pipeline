from fastapi import FastAPI, UploadFile
from pydantic import BaseModel, ValidationError
from typing import List, Dict, Any
from pathlib import Path
import json
import uuid

app = FastAPI()

PROCESSED_DIR = Path(__file__).parent / "processed"
PROCESSED_DIR.mkdir(exist_ok=True)


class FeatureRecord(BaseModel):
    lowlevel: Dict[str, Any]
    rhythm: Dict[str, Any]
    tonal: Dict[str, Any]
    metadata: Dict[str, Any]


@app.get("/health")
def health():
    return {"status": "ok"}

import asyncio
import logging

logger = logging.getLogger("ingest")


def process_one(filename: str, content: bytes) -> tuple[str, Any]:
    """Blocking work: parse, validate, write. Runs in a worker thread."""
    try:
        data = json.loads(content)
        record = FeatureRecord(**data)
        raw_id = record.metadata["tags"]["musicbrainz_recordingid"][0]
        recording_id = str(uuid.UUID(raw_id))
        with open(PROCESSED_DIR / f"{recording_id}.json", "w") as f:
            json.dump(data, f)
        return "accepted", recording_id
    except (json.JSONDecodeError, ValidationError, KeyError, IndexError, ValueError) as e:
        return "rejected", {"file": filename, "error": f"invalid file: {e}"}
    except Exception:
        logger.exception("unexpected error processing %s", filename)  # full traceback in the server log
        return "rejected", {"file": filename, "error": "internal error"}


@app.post("/ingest")
async def ingest_batch(files: List[UploadFile]):
    results = {"accepted": [], "rejected": []}
    for file in files:
        content = await file.read()
        status, payload = await asyncio.to_thread(process_one, file.filename, content)
        results[status].append(payload)
    return results