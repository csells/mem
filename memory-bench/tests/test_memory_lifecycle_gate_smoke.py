from pathlib import Path

import pytest

from scripts.memory_lifecycle_gate_smoke import assert_observation, reserve_output


def test_infrastructure_cannot_satisfy_an_expected_block() -> None:
    observation = {
        "returncode": 2,
        "gate_events": [{"passed": False, "reasons": ["invalid_receipts"]}],
    }
    with pytest.raises(RuntimeError, match="infrastructure"):
        assert_observation(observation, blocked=True)


def test_expected_block_requires_actual_gate_event() -> None:
    with pytest.raises(RuntimeError, match="gate evidence"):
        assert_observation({"returncode": 2, "gate_events": []}, blocked=True)


def test_output_is_exclusive_even_when_empty(tmp_path: Path) -> None:
    out = tmp_path / "result"
    reserve_output(out)
    with pytest.raises(FileExistsError):
        reserve_output(out)


def test_wrong_returncode_is_not_a_success() -> None:
    with pytest.raises(AssertionError):
        assert_observation(
            {"returncode": 1, "gate_events": [{"passed": True, "reasons": []}]},
            blocked=False,
        )
