"""Project integration remains inside the existing isolation boundary."""

import json

import pytest

from membench.runner import memory_e2e_hosts as host
from membench.runner.memory_host_types import HostLaunch


@pytest.mark.parametrize("name", ["claude", "codex"])
def test_project_loading_is_enabled_without_changing_old_launch(name):
    args = (
        [
            "claude",
            "--disable-slash-commands",
            "--setting-sources",
            "",
            "--tools",
            "Bash,Read,Write,Edit",
            "--allowedTools",
            "Bash,Read,Write,Edit",
            "-p",
            "task",
        ]
        if name == "claude"
        else [
            "codex",
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "-c",
            "project_doc_max_bytes=0",
            "task",
        ]
    )
    old = HostLaunch(args, {"HOME": "/preserved", "AUTH_TEST": "private"})
    new = host.enable_project(name, old)
    assert old.argv == args and new.argv is not old.argv
    assert new.env == old.env
    assert "private" not in json.dumps(new.public_settings)
    if name == "claude":
        assert "--disable-slash-commands" not in new.argv
        assert new.argv[new.argv.index("--setting-sources") + 1] == "project"
        assert "Skill" in new.argv[new.argv.index("--tools") + 1].split(",")
    else:
        assert "--ignore-user-config" in new.argv
        assert "--ignore-rules" not in new.argv
        assert "project_doc_max_bytes=0" not in new.argv


def test_unknown_host_is_not_silently_qualified():
    with pytest.raises(ValueError):
        host.enable_project("unimplemented", HostLaunch([], {}))
