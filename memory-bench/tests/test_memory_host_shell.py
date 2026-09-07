"""A macOS login shell must keep the isolated shim ahead of global executables."""

import subprocess
import sys
from pathlib import Path

import pytest

from membench.runner.memory_host_shell import shell_environment


@pytest.mark.skipif(sys.platform != "darwin", reason="Exercises macOS login path_helper")
def test_login_and_nonlogin_shells_preserve_shim_path_without_global_config(tmp_path):
    local = tmp_path / "session"
    (local / "bin").mkdir(parents=True)
    (local / "config").mkdir()
    command = local / "bin/bd"
    command.write_text("#!/bin/sh\nprintf 'isolated shim\\n'\n")
    command.chmod(0o700)
    inherited = {"HOME": str(Path.home()), "PATH": str(local / "bin") + ":/usr/bin:/bin"}
    env = shell_environment(local, inherited)
    assert inherited["HOME"] == env["HOME"]
    assert "ZDOTDIR" not in inherited
    for argv in (["/bin/zsh", "-lc", "bd"], ["/bin/zsh", "-c", "bd"], ["/bin/bash", "-c", "bd"]):
        result = subprocess.run(argv, env=env, capture_output=True, text=True, check=True)
        assert result.stdout == "isolated shim\n"
