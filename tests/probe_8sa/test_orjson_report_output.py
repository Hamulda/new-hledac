"""
D.12: report_dict → orjson.dumps() → orjson.loads() round-trip zachová strukturu.
"""
import sys
import orjson

sys.path.insert(0, ".")


def test_orjson_report_output():
    report = {
        "sprint_id": "8sa_test",
        "query": "ransomware",
        "duration_s": 300.0,
        "accepted_findings": 5,
        "cycles_completed": 3,
        "final_phase": "TEARDOWN",
        "aborted": False,
        "phase_timing": {"BOOT": 0.0, "WARMUP": 0.5, "ACTIVE": 5.0},
    }

    # Serialize with orjson
    data = orjson.dumps(report, option=orjson.OPT_INDENT_2)
    assert isinstance(data, bytes)

    # Deserialize
    decoded = orjson.loads(data)
    assert decoded["sprint_id"] == "8sa_test"
    assert decoded["accepted_findings"] == 5
    assert decoded["phase_timing"]["ACTIVE"] == 5.0
    assert isinstance(decoded["phase_timing"], dict)

    print("PASS: orjson round-trip preserves structure")


if __name__ == "__main__":
    test_orjson_report_output()
