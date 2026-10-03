import json
import uuid
from pathlib import Path
import tasks
from tasks import process_one_task, celery_app, r

celery_app.conf.update(task_always_eager=True)


def make_valid_feature_record(recording_id: str = None) -> bytes:
    rid = recording_id or str(uuid.uuid4())
    data = {
        "lowlevel": {"feature1": 0.1},
        "rhythm": {"feature2": 0.2},
        "tonal": {"feature3": 0.3},
        "metadata": {"tags": {"musicbrainz_recordingid": [rid]}}
    }
    return json.dumps(data).encode("utf-8")


def test_valid_record_through_celery_dispatch():
    rid = str(uuid.uuid4())
    content = make_valid_feature_record(rid)
    batch_id = "test_batch_single"
    job_key = f"job:{batch_id}"

    r.hset(job_key, mapping={"status": "processing", "total_files": 1, "processed_count": 0})

    async_result = process_one_task.delay(batch_id, "valid_record.json", content)
    outcome = async_result.get(timeout=10)

    assert outcome["status"] == "accepted"
    assert outcome["recording_id"] == rid

    job = r.hgetall(job_key)
    assert job["status"] == "completed"
    assert job["processed_count"] == "1"

    results_path = tasks.RESULTS_DIR / f"{batch_id}.json"
    assert results_path.exists()

    with open(results_path) as f:
        results = json.load(f)
    assert len(results) == 1
    assert results[0]["recording_id"] == rid

    r.delete(job_key)
    results_path.unlink()