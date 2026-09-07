"""Child-only shell startup files preserve the experiment's executable routing.

macOS /etc/zprofile runs path_helper, moving global bins ahead of an inherited
PATH even when the host inherits that environment faithfully. Restore the same
declared PATH after system login setup. No real HOME or user startup file changes.
"""

from __future__ import annotations

import shlex
from pathlib import Path


def shell_environment(local: Path, env: dict[str, str]) -> dict[str, str]:
    shell = local / "config/shell"
    shell.mkdir(exist_ok=False)
    contents = "export PATH=" + shlex.quote(env["PATH"]) + "\n"
    for name in (".zshenv", ".zprofile", ".zlogin", "bash-env.sh"):
        with (shell / name).open("x") as target:
            target.write(contents)
    return {**env, "ZDOTDIR": str(shell), "BASH_ENV": str(shell / "bash-env.sh")}

