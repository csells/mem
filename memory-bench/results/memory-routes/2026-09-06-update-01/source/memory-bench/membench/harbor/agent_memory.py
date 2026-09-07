"""Where injected prior-session memory must land so the agent actually READS it.

The trace-explorer audit (2026-07-05) found the memory arms inject a file the agent
never reads: every ``ours``/``oracle`` run checked
``/logs/agent/sessions/projects/-app/memory/MEMORY.md`` (Claude Code's OWN
native-memory path) and, finding it empty, proceeded with no memory. The injected
``/memory/MEMORY.md`` was ignored — the native-memory system-prompt block outranks the
task instruction. 0 of 50 memory-bearing traces consumed the injected file.

Root cause is deterministic, from Harbor's own source:

- ``harbor/agents/installed/claude_code.py`` sets
  ``CLAUDE_CONFIG_DIR = <agent_dir>/sessions`` = ``/logs/agent/sessions`` and the agent's
  native-memory feature reads ``$CLAUDE_CONFIG_DIR/projects/<cwd-slug>/memory/MEMORY.md``.
- ``/logs/agent`` is a RUNTIME bind mount (``EnvironmentPaths``: "Mounted from
  trial_dir/agent/"), so a build-time ``COPY`` into the native path is shadowed by the
  mount — baking there cannot work.

The fix: relocate ``CLAUDE_CONFIG_DIR`` to a build-bakeable directory OUTSIDE ``/app``
(so an agent write is classified ``OUTSIDE_WORK_DIR``, never polluting the candidate
diff) and OUTSIDE ``/logs`` (so a build-time ``COPY`` survives), then bake the injected
memory at the native sub-path under it. The override reaches the agent through the
installed agent's ``extra_env`` (``harbor/agents/factory.py`` ``extra_env=config.env``),
which is merged OVER the adapter's env at exec (``agents/installed/base.py``
``merged_env.update(self._extra_env)``), so it wins over the hard-coded default. Harvest
is unaffected — it reads ``/logs/agent/claude-code.txt`` (the adapter's ``tee`` target,
independent of ``CLAUDE_CONFIG_DIR``).

Side effect (inert for this pipeline, documented so it is not a surprise): relocating
``CLAUDE_CONFIG_DIR`` off ``/logs/agent`` moves Claude Code's session artifacts (JSONL
transcripts, ``.claude.json``, todos) out of the only tree Harbor mounts and collects.
So for injected legs Harbor's own ``trajectory.json`` / ``cost_usd`` / token bookkeeping
(``trial.py`` ``_get_session_dir`` looks under the fixed ``/logs/agent/sessions``) and its
post-run log download go unpopulated. The probe never reads those — it scores from
``claude-code.txt`` and parses efficiency from that stream — and the local spike never
injects, so nothing here regresses; but a future consumer of ``harvest_job_dir``'s
``trajectory.json`` on an injected leg would find it absent (it falls back to the stream).

Pure module: constants + string helpers only and no membench imports, so ``probe_gate``
can depend on it without dragging in ``probe_gate``'s heavy transitive deps (and a future
``harbor_exec`` default could too). ``harbor_exec`` currently stays decoupled via a generic
``Mapping`` param, so no import edge exists today.
"""

from __future__ import annotations

from collections.abc import Mapping

# The agent's container working directory (Harbor's WORKDIR; the probe instruction names
# it). The single source of truth — ``probe_gate`` imports it as ``CONTAINER_WORKDIR``.
AGENT_WORKDIR = "/app"

# Relocated Claude Code config dir. OUTSIDE /app and OUTSIDE /logs (see module docstring).
AGENT_CONFIG_DIR = "/agent-memory"

# The in-container path the fixed probe instruction names (kept as a belt-and-suspenders
# delivery target for an agent that DOES follow the instruction literally).
INSTRUCTION_MEMORY_PATH = "/memory/MEMORY.md"

# The env override handed to the installed agent (via the job config's ``agents[].env``)
# so its native-memory block resolves to `native_memory_path()`. NOT the OAuth token —
# that still flows from the harbor process env, untouched.
AGENT_MEMORY_ENV: Mapping[str, str] = {"CLAUDE_CONFIG_DIR": AGENT_CONFIG_DIR}


def config_slug(workdir: str) -> str:
    """Claude Code's per-project directory name: the absolute cwd with every ``/`` and
    ``.`` replaced by ``-`` (e.g. ``/app`` -> ``-app``, matching Harbor's own hard-coded
    ``projects/-app`` in the claude-code adapter)."""
    return workdir.replace("/", "-").replace(".", "-")


def native_memory_path(config_dir: str = AGENT_CONFIG_DIR, workdir: str = AGENT_WORKDIR) -> str:
    """Where Claude Code's native-memory feature reads ``MEMORY.md`` for ``workdir`` under
    ``config_dir`` — i.e. ``$CLAUDE_CONFIG_DIR/projects/<cwd-slug>/memory/MEMORY.md``."""
    return f"{config_dir}/projects/{config_slug(workdir)}/memory/MEMORY.md"


# Same layout, slug-agnostic: for a sandbox cwd whose slug is not worth reconstructing,
# glob this under a config dir instead of predicting the exact path. Lives here so the
# layout has ONE source of truth — a Claude Code layout change must not leave a globbing
# caller silently finding nothing (which reads as "native memory never engaged").
#
# EVERY .md, not just MEMORY.md: native memory is an INDEX plus TOPIC FILES. MEMORY.md
# holds one-line pointers ("- [Title](topic.md) — hook") and the FACT lives in the sibling
# <topic>.md. Globbing the index alone finds a pointer where the content is, so a WORKING
# native memory reads as engaged=0 — the false mechanism-disabled verdict this constant
# exists to prevent.
NATIVE_MEMORY_GLOB = "projects/*/memory/*.md"


# The two in-container paths a build delivers the injected memory to: the agent's native
# read path (primary — its own instinct finds it) and the instruction path (fallback).
AGENT_NATIVE_MEMORY_PATH = native_memory_path()
DELIVERED_MEMORY_PATHS: tuple[str, ...] = (AGENT_NATIVE_MEMORY_PATH, INSTRUCTION_MEMORY_PATH)

# The native-memory DIRECTORY (parent of the baked file). Claude Code's ``system``/``init``
# event reports the directory it auto-loaded memory from (its ``memory_paths`` field), not
# the file, e.g. ``{"auto": "/agent-memory/projects/-app/memory/"}``.
AGENT_NATIVE_MEMORY_DIR = AGENT_NATIVE_MEMORY_PATH.rsplit("/", 1)[0]


def path_covers_native_memory(loaded_path: str) -> bool:
    """True when ``loaded_path`` — a path from Claude Code's ``system``/``init``
    ``memory_paths`` field — is the relocated native-memory directory we bake into.

    CC reports the CONFIGURED native-memory directory here (with a trailing slash,
    ``/agent-memory/projects/-app/memory/``; some CLI versions the file itself),
    INDEPENDENT of whether a file was found there — verified on CLI 2.1.201: the field is
    byte-identical whether the dir holds a ``MEMORY.md``, is empty, or is absent, and the
    loaded content never reaches the stdout stream. So a match confirms the
    ``CLAUDE_CONFIG_DIR`` RELOCATION reached the agent (CC auto-loads from our baked dir,
    not its default ``/logs`` path) — NOT that content was loaded. Content is guaranteed
    separately, at build, by the non-empty bake at this exact path
    (`probe_gate._bake_memory_into_env`); the two together put the injected memory in the
    agent's context. Exact match (not a prefix test), so a sibling like ``.../memory-old/``
    cannot false-cover."""
    return loaded_path.rstrip("/") in (AGENT_NATIVE_MEMORY_DIR, AGENT_NATIVE_MEMORY_PATH)
