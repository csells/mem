"""Read-only delivery matching against scratch text and saved host evidence."""

import json

import delivery_exposure as exposure
import pytest


def test_full_numbered_file_read_matches_but_truncated_or_scrambled_does_not():
    expected = "# Memory\n\nCapture deliberately.\nRead completely.\n"
    output = "1\t# Memory\n2\t\n3\tCapture deliberately.\n4\tRead completely.\n"
    assert exposure.full_reference(output, expected)
    assert not exposure.full_reference(output.rsplit("\n4", 1)[0], expected)
    assert not exposure.full_reference(
        "# Memory\n\nRead completely.\nCapture deliberately.", expected
    )


def test_json_output_envelope_matches_and_arguments_alone_do_not():
    expected = "# Memory\nExact procedure."
    assert exposure.full_reference({"output": expected}, expected)
    assert not exposure.full_reference({"arguments": expected}, expected)


def test_startup_echo_requires_exact_user_message_not_substring_or_assistant():
    prompt = "Briefing\n\nTask\nWork on issue."
    assert exposure.exact_codex_echo(
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]},
        prompt,
    )
    assert not exposure.exact_codex_echo(
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "input_text", "text": prompt}],
        },
        prompt,
    )
    assert not exposure.exact_codex_echo(
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": prompt + "extra"}],
        },
        prompt,
    )


@pytest.mark.parametrize(
    "command,matched", [("bd prime --no-memories", False), ("cat references/memory.md", True)]
)
def test_reference_read_is_separate_from_same_content_in_prime(tmp_path, command, matched):
    reference = tmp_path / "memory.md"
    reference.write_text("# Memory\nExact procedure.")
    (tmp_path / "launch-prompt.txt").write_text("Briefing\nTask")
    (tmp_path / "tool-calls.json").write_text(
        json.dumps([{"arguments": {"command": command}, "result": reference.read_text()}])
    )
    row = {
        "evidence_root": str(tmp_path),
        "source_sha256": {},
        "host": "claude",
        "slot": "slot",
        "profile_id": "claude",
        "arm": "startup-briefing",
        "startup_submitted": True,
        "actual_prime_output_exposure": True,
    }
    workflow = tmp_path / "workflow.json"
    workflow.write_text(json.dumps(row))
    result = exposure.inspect(workflow, reference)
    assert result["memory_reference_full_read_verified"] is matched
    assert result["actual_prime_full_output_verified"] is True
    assert result["startup_exact_host_echo_observed"] is None
