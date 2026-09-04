"""Ensures the membench package (memory-bench/) is importable during tests."""

import pytest

from membench.runner.e1_grid import NATIVE_MEMORY_ENV_INLETS


@pytest.fixture(autouse=True)
def _scrub_ambient_native_memory_inlets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite hermetic against the env vars that outrank E1's R0 native-memory pin.

    Same lesson as the API-key fixture below, and it is not hypothetical here: this suite is
    launched from a Claude Code session, and every name in ``NATIVE_MEMORY_ENV_INLETS`` is one
    that session may itself export. ``e1_grid``'s precedence guard refuses a paid entrypoint while
    any of them reaches the child, so an ambient one would red the suite in exactly the shell the
    guard exists to protect — invisible to CI's clean env (mem-9bh93). Clearing them here makes
    the ambient value irrelevant; a test that wants one SET sets it explicitly on the same
    ``monkeypatch``, which runs after this fixture and wins."""
    for name in NATIVE_MEMORY_ENV_INLETS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _scrub_ambient_anthropic_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite hermetic against a developer's exported ``ANTHROPIC_API_KEY``.

    The paid-run gate (mem-9bh93, ``headless_agent.a_paid_run_carries_the_metered_api_key``) refuses
    a non-dry run when this key is set. Any test that drives a paid entrypoint with an ambient key
    present would trip the gate and fail — a red suite in the exact dev shell the gate exists to
    protect, and invisible to CI's clean env. Clearing it here makes the ambient value irrelevant; a
    test that wants the key SET still sets it explicitly (``monkeypatch.setenv`` in the test body
    runs after this fixture, on the same ``monkeypatch``, so it wins)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
