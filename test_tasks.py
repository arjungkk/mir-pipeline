import json
import uuid
from tasks import process_one_task, celery_app

celery_app.conf.update(task_always_eager=True)  # Run tasks synchronously for testing


def make_valid_feature_record(recording_id: str = None) -> bytes:
    rid = recording_id or str(uuid.uuid4())
    data = {
        "lowlevel": {"feature1": 0.1},
        "rhythm": {"feature2": 0.2},
        "tonal": {"feature3": 0.3},
        "metadata": {
            "tags": {
                "musicbrainz_recordingid": [rid]
            }
        }
    }
    return json.dumps(data).encode('utf-8')


def test_valid_record_through_celery_dispatch():
    rid = str(uuid.uuid4())
    content = make_valid_feature_record(rid)

    async_result = process_one_task.delay("test_batch", "valid_record.json", content)
    status, payload = async_result.get(timeout=10)  # Wait for the task to complete

    assert status == "accepted"
    assert payload == rid