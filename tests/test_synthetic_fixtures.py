import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "synthetic" / "cases.json"


def test_development_case_fixtures_are_explicitly_synthetic() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert payload["cases"]
    for case in payload["cases"]:
        assert case["case_id"].startswith("synthetic-")
        assert case["user_ref"].startswith("synthetic-")
        assert case["chat_ref"].startswith("synthetic-")
        assert case["personal_context"] == {
            "source": "synthetic",
            "contains_real_personal_data": False,
        }
