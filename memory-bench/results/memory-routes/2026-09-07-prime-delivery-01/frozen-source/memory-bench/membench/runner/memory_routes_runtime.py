"""Process isolation for the local macOS memory-delivery experiment.

The profile grants only caller-selected runtime and workspace paths. In particular,
it never grants a workspace's parent, where the experiment's hidden evidence may
live. Authentication comes from Claude's existing Keychain store. The token helper
returns an access token for transient child-process use without writing or logging
credential material.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

_SOURCE_REPO = Path(__file__).resolve().parents[3]
_PRIVATE_ROOTS = tuple(
    Path(value) for value in ("/Users", "/private/tmp", "/private/var/folders", "/Volumes")
)
_INHERITED_ENV = frozenset(
    {
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "TERM",
        "COLORTERM",
        "__CF_USER_TEXT_ENCODING",
    }
)


def _root(path: Path) -> Path:
    root = path.resolve()
    if any(private.is_relative_to(root) for private in _PRIVATE_ROOTS):
        raise ValueError(f"Refusing broad sandbox allowance: {root}")
    if root.is_relative_to(_SOURCE_REPO) or _SOURCE_REPO.is_relative_to(root):
        raise ValueError(f"Refusing source repository sandbox allowance: {root}")
    return root


def _selector(path: Path) -> str:
    kind = "literal" if path.is_file() else "subpath"
    return f"({kind} {json.dumps(str(path), ensure_ascii=False)})"


def make_profile(path: Path, writable_roots: list[Path], readable_roots: list[Path]) -> Path:
    """Create a new Seatbelt profile, refusing broad or source-tree allowances.

    Writable roots also receive read access. Callers must name the actual Python
    runtime (for example ``Path(sys.base_prefix).resolve()``), not a source-tree
    virtualenv or its parent. A standalone shim belongs in its own scratch folder.
    Existing profiles are preserved: the destination is opened exclusively.
    """
    writable = sorted({_root(root) for root in writable_roots})
    readable = sorted({*writable, *(_root(root) for root in readable_roots)})
    lines = ["(version 1)", "(allow default)", "(deny file-write*)"]
    write_selectors = [_selector(root) for root in writable]
    write_selectors.extend(['(literal "/dev/null")', '(literal "/dev/tty")'])
    lines.append(f"(allow file-write* {' '.join(write_selectors)})")
    denied = [*_PRIVATE_ROOTS, _SOURCE_REPO]
    lines.append(f"(deny file-read* {' '.join(_selector(root) for root in denied)})")
    # Runtimes resolve temp directories and traverse ancestors before opening
    # files. Metadata access does not expose hidden evidence file contents.
    lines.append("(allow file-read-metadata)")
    if readable:
        lines.append(f"(allow file-read* {' '.join(_selector(root) for root in readable)})")
    # bd 1.2.1 loads every user config whose stat succeeds. Hide those exact
    # files so denied content reads do not prevent loading project settings.
    user_config_files = (
        Path.home() / ".config/bd/config.yaml",
        Path.home() / ".beads/config.yaml",
        Path.home() / "Library/Application Support/bd/config.yaml",
    )
    config_selectors = [
        f"(literal {json.dumps(str(config), ensure_ascii=False)})" for config in user_config_files
    ]
    lines.append(f"(deny file-read-metadata {' '.join(config_selectors)})")
    with path.open("x", encoding="utf-8") as profile:
        profile.write("\n".join(lines) + "\n")
    return path


def experiment_env(config: Path, tmp: Path, bin_dir: Path) -> dict[str, str]:
    """Return an isolated environment using the existing subscription login.

    Only basic OS identity, locale and terminal settings survive.
    This excludes inherited Beads routing, Python imports, shell startup hooks,
    provider settings and credential variables without maintaining a token-name
    blacklist. An API key is refused rather than silently changing its billing
    route. This helper creates no directories and never changes ``HOME``.
    """
    if "ANTHROPIC_API_KEY" in os.environ:
        raise ValueError("ANTHROPIC_API_KEY is set; subscription experiment refused")
    env = {
        key: value
        for key, value in os.environ.items()
        if key in _INHERITED_ENV or key.startswith("LC_")
    }
    config = config.resolve()
    tmp = tmp.resolve()
    bin_dir = bin_dir.resolve()
    env.update(
        {
            "CLAUDE_CONFIG_DIR": str(config),
            # Empty explicitly selects the default Keychain entry in 2.1.263.
            "CLAUDE_SECURESTORAGE_CONFIG_DIR": "",
            "TMPDIR": str(tmp),
            "TMP": str(tmp),
            "TEMP": str(tmp),
            # Claude's macOS temp resolver otherwise uses literal /tmp.
            "CLAUDE_CODE_TMPDIR": str(tmp),
            "XDG_RUNTIME_DIR": str(tmp),
            "XDG_CONFIG_HOME": str(config / "xdg"),
            "DOLT_ROOT_PATH": str(config / "dolt-root"),
            "GIT_CONFIG_GLOBAL": str(config / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "BD_NON_INTERACTIVE": "1",
            "BD_DISABLE_METRICS": "1",
            "PATH": str(bin_dir) + ":/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        }
    )
    return env


def subscription_token() -> str:
    """Read an unexpired subscription access token without persisting it.

    The caller may supply the return value only to the child process environment;
    it must never include that environment in receipts, diagnostics or artifacts.
    This deliberately does not refresh credentials or alter the Keychain.
    """
    unavailable = "Claude subscription credentials are unavailable"
    try:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-s",
                "Claude Code-credentials",
                "-w",
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError(unavailable) from None
    if result.returncode != 0:
        raise RuntimeError(unavailable)
    try:
        payload = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise RuntimeError(unavailable) from None
    if not isinstance(payload, dict):
        raise RuntimeError(unavailable)
    oauth = payload.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        raise RuntimeError(unavailable)
    token = oauth.get("accessToken")
    expiry = oauth.get("expiresAt")
    if (
        not isinstance(token, str)
        or not token.strip()
        or not isinstance(expiry, int)
        or isinstance(expiry, bool)
    ):
        raise RuntimeError(unavailable)
    if expiry <= time.time() * 1000:
        raise RuntimeError("Claude subscription credentials are expired")
    return token
