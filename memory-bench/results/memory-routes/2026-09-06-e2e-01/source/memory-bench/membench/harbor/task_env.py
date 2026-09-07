"""Harbor task.toml ``[environment]`` network policy (harbor>=0.13 schema).

Harbor 0.13 deprecated the boolean ``allow_internet`` field in favour of
``[environment].network_mode`` (``public`` | ``no-network`` | ``allowlist``) plus
``allowed_hosts`` (allowlist mode only). We expose that full enum at our own API
surface and emit the current harbor fields HERE, at the single TOML-emission seam,
so the deprecated field is never written and no DeprecationWarning fires when
harbor validates the task config.

Real replay/probe runs default to ``allowlist``, never ``public`` (mem-yeoz): each
replayed fix landed weeks earlier on a public GitHub repo named in-band by the
baked snapshot (go.mod / package.json repository), so public egress would let any
arm — including the no_memory floor — fetch the landed gold diff. The allowlist
covers only what a real run legitimately needs: the Claude Code agent's own hosts
and the rigs' package registries. ``public`` remains an explicit escape hatch.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

# harbor.models.task.config.NetworkMode values; kept as bare strings so this module
# imports nothing from harbor (the skeleton must build without the optional pkg).
NetworkMode = Literal["public", "no-network", "allowlist"]

_MODES: frozenset[str] = frozenset(("public", "no-network", "allowlist"))

# What a real replay run legitimately needs and nothing else; github.com is
# deliberately absent — that is the host the landed gold fix lives on.
REPLAY_ALLOWED_HOSTS: tuple[str, ...] = (
    # Claude Code agent: the Anthropic API plus the native-installer download
    # hosts (claude.ai serves install.sh; the binary comes from GCS).
    "api.anthropic.com",
    "claude.ai",
    "storage.googleapis.com",
    # Package registries the replayed rigs' builds resolve dependencies from
    # (node:22 rigs → npm; golang:1.23 rigs → module proxy + sumdb; python
    # rigs → PyPI; rust rigs → crates.io).
    "registry.npmjs.org",
    "proxy.golang.org",
    "sum.golang.org",
    "pypi.org",
    "files.pythonhosted.org",
    "crates.io",
    "static.crates.io",
    "index.crates.io",
)


def environment_network(
    mode: NetworkMode, *, allowed_hosts: Sequence[str] = REPLAY_ALLOWED_HOSTS
) -> dict[str, str | list[str]]:
    """The ``[environment]`` network-policy fragment for a harbor task.toml.

    ``allowed_hosts`` rides along only in ``allowlist`` mode — harbor rejects the
    field on any other mode."""
    if mode not in _MODES:
        raise ValueError(f"unknown network mode {mode!r}; known: {sorted(_MODES)}")
    if mode == "allowlist":
        return {"network_mode": mode, "allowed_hosts": list(allowed_hosts)}
    return {"network_mode": mode}
