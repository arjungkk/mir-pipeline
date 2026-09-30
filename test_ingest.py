import json
import uuid
from unittest.mock import patch
from main import process_one

def make_valid_record(recording_id: str = None) -> bytes:
    """Create a valid FeatureRecord dictionary for testing."""
    rid = recording_id or str(uuid.uuid4())
    data = {
        "lowlevel": {"feature1": 1},
        "rhythm": {"feature2": 2},
        "tonal": {"feature3": 3},
        "metadata": {
            "tags": {
                "musicbrainz_recordingid": [rid]
            }
        }
    }
    return json.dumps(data).encode("utf-8")

def test_valid_record_is_accepted(tmp_path):
    """Test that a valid record is accepted and processed correctly."""
    rid = str(uuid.uuid4())
    content = make_valid_record(rid)
    status, payload = process_one("test.json", content, output_dir=tmp_path)
    assert status == "accepted"
    assert payload == rid
    assert (tmp_path / f"{rid}.json").exists()

def test_missing_top_level_section_is_rejected():
    """Test that a record missing a top-level section is rejected."""
    data = {"lowlevel": {}, "rhythm": {}, "tonal": {}}  # metadata missing
    content = json.dumps(data).encode("utf-8")

    status, payload = process_one("test.json", content)

    assert status == "rejected"
    assert payload["file"] == "test.json"

def test_non_uuid_recording_id_is_rejected():
    """Test that a record with a non-UUID recording ID is rejected."""
    content = make_valid_record(recording_id="not-a-uuid")
    status, payload = process_one("test.json", content)
    assert status == "rejected"
    assert "invalid file" in payload["error"]

def test_malformed_json_is_rejected():
    """Test that malformed JSON is rejected."""
    content = b"{invalid json}"
    status, payload = process_one("test.json", content)
    assert status == "rejected"
    assert "invalid file" in payload["error"]

def test_unexpected_error_returns_generic_message(caplog):
    """Test that an unexpected error returns a generic error message."""
    content = make_valid_record()

    with patch("builtins.open", side_effect=OSError("disk full")):
        status, payload = process_one("test.json", content)

        assert status == "rejected"
        assert payload["error"] == "internal error"
        assert "unexpected error processing" in caplog.text