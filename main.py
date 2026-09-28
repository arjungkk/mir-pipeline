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

@app.post("/ingest")
async def ingest_batch(files: List[UploadFile]):
    results = {"accepted": [], "rejected": []}

    for file in files:
        try:
            content = await file.read()
            data = json.loads(content)
            record = FeatureRecord(**data)

            raw_id = record.metadata["tags"]["musicbrainz_recordingid"][0]
            recording_id = str(uuid.UUID(raw_id))  # raises ValueError if not a real UUID

            with open(PROCESSED_DIR / f"{recording_id}.json", "w") as f:
                json.dump(data, f)

            results["accepted"].append(recording_id)

        except (json.JSONDecodeError, ValidationError, KeyError, IndexError, ValueError) as e:
            results["rejected"].append({"file": file.filename, "error": f"invalid file: {e}"})
        except Exception as e:
            results["rejected"].append({"file": file.filename, "error": f"unexpected error: {e}"})

    return results