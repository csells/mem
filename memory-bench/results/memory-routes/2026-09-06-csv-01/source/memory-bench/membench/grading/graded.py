"""Graded quality metric -- the S3 LLM-judge signal (mem-g6a design, mem-r5y wiring).

The binary gold-test anchor (`dual_verifier.score_direct`) has almost no dynamic
range in the failing region: a run that gets *closer* scores identically to one that
did nothing. S1 (per-test-file partial credit) and S2 (always-on diff similarity)
add mechanical resolution underneath the anchor; this module adds the *semantic*
one -- a rubric-scored judgment of the candidate diff against the issue and the gold
diff. It is a SIDE SIGNAL in the score vector, never a gate and never folded into a
single weighted number (mem-r5y locked decision 3: stay on the vector).

The controls are the EnterpriseBench + CodeScaleBench anti-gaming stack the design
locks in (mem-r5y decision 1):

- **Blinding.** The judge view is exactly (issue text, candidate diff, gold diff) --
  `build_graded_view` assembles only those. No arm/condition label, no memory
  payload, no token counts, no harness preamble (CSB preamble-strip).
- **Coarse per-criterion scale + evidence.** Each rubric criterion scores 0 / 0.5 /
  1.0 and must cite code-specific evidence or score 0 (EB 3-point + evidence). The
  judge emits per-criterion scores; the weighted sum is computed in CODE, so the
  semantic judgment is the model's and the arithmetic is ours (ZFC).
- **Pinned model recorded.** The judge model id rides along in the `GradedJudgment`
  so a score is attributable. Temperature 0 is the design's intended control, but the
  ``claude -p`` OAuth seam exposes no temperature flag (unlike the HTTP
  `grading.judge.OssLlmJudge`, which sends ``temperature: 0``); on this seam
  determinism instead rests on the N-round median vote below. A temperature-capable
  backend wired in later should set 0.
- **N-round majority vote, median tie-break** (CSB `judge/engine.py`): the judge is
  called `rounds` times and the median is the score; round spread becomes a
  confidence. This is the variance control that stands in for temp 0 on the CLI seam.
- **Mechanical-vs-judge divergence flag** (EB rescore comparator): when the judge
  score and the mechanical reference (the S2 diff-sim) disagree by more than
  `GRADED_DIVERGENCE_THRESHOLD`, the run is flagged for review.

Judge backend (mem-r5y decision 1): Claude Sonnet 4.6 via the local ``claude -p``
OAuth seam -- the same seam `bbon.comparative_judge.ClaudeComparativeJudge` uses,
free under our subscription and NOT a paid managed API, so it does not trip the
D4/D16 fence the single-output `grading.judge.OssLlmJudge` guards. `StubRubricJudge`
is the deterministic, offline judge the whole pipeline and every test run on.

Calibration (mem-r5y decision 4) is OUT of band: Opus 4.8 + Codex review the diffs
against project history and intent, REPLACING the hand-labeled kappa gate. The judge
(Sonnet) and the calibrators (Opus/Codex) stay separate so the judge never grades
against itself. This module therefore carries no kappa gate and gates nothing on
calibration -- the judge is always a reported signal, flagged when it diverges.

ZFC: the per-criterion judgment is the model's; this module is pure plumbing --
prompt assembly, subprocess IO, JSON parsing, structural validation, and the
weighted-sum / median / divergence arithmetic over the model's outputs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from statistics import median
from typing import Protocol

from membench._claude_cli import first_json_object, unwrap_cli_json
from membench.grading.judge import Rubric, RubricCriterion, score_completion
from membench.judge_config import (
    IsolatedClaudeCallsite,
    IsolatedJudgeConfig,
    run_isolated_claude,
)
from membench.spawn import Runner

# Judge score and the mechanical reference disagree by more than this -> flag the run
# for review (EB rescore comparator's 0.3 threshold).
GRADED_DIVERGENCE_THRESHOLD = 0.3

# Per-run judge calls; the median is the score, the spread the confidence.
DEFAULT_JUDGE_ROUNDS = 3

# A single judge draw occasionally returns a wrong-schema reply -- most often a
# code-review {"findings": [...], "level": ...} object instead of the rubric
# {"criteria": [...]} -- when the host `claude -p` session picks up review-shaped
# framing from a reviewable candidate diff. That is an unparseable draw, not a
# score of record: re-take it up to this many times before failing loud. Bounded
# so a persistently-broken judge still surfaces (RubricParseError) rather than
# looping. Only RubricParseError is retried; a [0,1] contract breach (plain
# ValueError) is a judge bug and fails on the first draw.
GRADED_JUDGE_MAX_ATTEMPTS = 4

# Bumping this invalidates any cached verdict and is recorded on the judgment.
GRADED_PROMPT_VERSION = "v1"

# The coarse 3-point per-criterion scale (EB anti-gaming): the only scores a reply
# may carry. A reply using any other value is a protocol violation, surfaced loudly.
ALLOWED_CRITERION_SCORES = (0.0, 0.5, 1.0)

# Locked judge backend (mem-r5y decision 1): Claude Sonnet 4.6 over the OAuth CLI.
# Overridable for experiments via the env var (e.g. a different pinned Sonnet build).
DEFAULT_GRADED_JUDGE_MODEL = "claude-sonnet-4-6"
ENV_GRADED_JUDGE_MODEL = "MEMBENCH_GRADED_JUDGE_MODEL"
# A graded-judge prompt resolves in seconds; a minute-plus bound means a wedged
# subprocess, not slow inference (the comparative-judge convention).
DEFAULT_TIMEOUT_S = 120.0


def graded_rubric() -> Rubric:
    """The diff-quality rubric (mem-g6a S3): does the candidate diff resolve the
    issue, judged against the gold diff. Distinct from
    `grading.judge.completion_rubric` (which scores a held-out *task* transcript) --
    here the judge sees the gold diff and grades solution quality against it. Weights
    sum to 1.0 so the weighted score is already in [0, 1]."""
    return Rubric(
        criteria=(
            RubricCriterion(
                name="resolves_issue",
                description=(
                    "The candidate diff addresses the issue and is consistent with "
                    "the reference (gold) diff's solution -- same behavior change, "
                    "not an unrelated or superficial edit."
                ),
                weight=0.5,
            ),
            RubricCriterion(
                name="completeness",
                description=(
                    "The candidate carries the change through -- it covers the parts "
                    "the gold diff changes, rather than stopping partway or stubbing."
                ),
                weight=0.3,
            ),
            RubricCriterion(
                name="focus",
                description=(
                    "The candidate's edits are coherent and scoped to the fix, with "
                    "no spurious or unrelated changes that the gold diff does not make."
                ),
                weight=0.2,
            ),
        )
    )


def _render_diff(diff_by_file: Mapping[str, str]) -> str:
    """A stable, path-ordered rendering of a per-file diff for the judge view. Empty
    (the agent edited nothing) renders explicitly so the judge sees a no-op as a
    no-op, never a missing section."""
    if not diff_by_file:
        return "(no changes)"
    return "\n".join(f"## {path}\n{diff_by_file[path]}" for path in sorted(diff_by_file))


def build_graded_view(
    *,
    issue_title: str,
    issue_body: str,
    candidate_diff: Mapping[str, str],
    gold_diff: Mapping[str, str],
) -> tuple[str, str]:
    """The BLINDED (task, run_output) the judge scores: ``task`` is the issue text
    plus the reference (gold) diff; ``run_output`` is the candidate diff. Exactly the
    three inputs the design admits -- no condition/arm label, no memory payload, no
    token counts, no harness preamble can enter through this envelope."""
    issue = issue_title if not issue_body else f"{issue_title}\n\n{issue_body}"
    task = f"# Issue\n{issue}\n\n# Reference (gold) diff\n{_render_diff(gold_diff)}"
    return task, _render_diff(candidate_diff)


@dataclass(frozen=True)
class CriterionVerdict:
    """One criterion's coarse-scale verdict with its grounding evidence."""

    name: str
    score: float
    evidence: str


class RubricParseError(ValueError):
    """A judge reply that is not a usable per-criterion verdict -- missing JSON, a
    criterion score OUT OF RANGE (outside [0, 1]), an unknown/duplicate criterion, or
    evidence-free scoring. A malformed verdict is a real error surfaced loudly, never
    coerced to a default score (the `grading.judge` fail-loud contract)."""


def _snap_to_coarse(score: float) -> float:
    """Snap an in-range score to the nearest coarse value (mem-r5y robustness). The
    judge is prompted for the 3-point {0, 0.5, 1.0} scale, but the ``claude -p`` seam
    occasionally returns a finer value (e.g. 0.8) -- benign imprecision, not a
    malformed verdict. Snapping is deterministic arithmetic that preserves the coarse
    intent (0.8 -> 1.0, 0.3 -> 0.5), so one off-grid value never aborts a multi-hour
    grid; an OUT-OF-RANGE score is a different failure and is rejected before this is
    called. Ties (e.g. 0.25) resolve to the lower value -- `min` keeps the first."""
    return min(ALLOWED_CRITERION_SCORES, key=lambda allowed: abs(allowed - score))


def parse_criteria(reply: str, rubric: Rubric) -> tuple[CriterionVerdict, ...]:
    """Parse a judge reply into one validated `CriterionVerdict` per rubric criterion.

    Enforces the anti-gaming contract structurally: every rubric criterion present
    exactly once, each score IN RANGE [0, 1] (an out-of-range score raises), each with
    non-empty code-specific evidence. Any breach raises `RubricParseError`. An in-range
    but off-grid score is snapped to the nearest coarse {0, 0.5, 1.0} value
    (`_snap_to_coarse`) -- benign judge imprecision, not a malformed verdict."""
    block = first_json_object(reply)
    if block is None:
        raise RubricParseError(f"judge reply has no JSON object: {reply[:200]!r}")
    try:
        parsed = json.loads(block)
    except json.JSONDecodeError as exc:
        raise RubricParseError(f"judge reply is not valid JSON: {exc}") from exc
    if not isinstance(parsed, Mapping) or not isinstance(parsed.get("criteria"), list):
        raise RubricParseError(f"judge reply has no 'criteria' list: {parsed!r}")

    by_name: dict[str, CriterionVerdict] = {}
    expected = {c.name for c in rubric.criteria}
    for entry in parsed["criteria"]:
        if not isinstance(entry, Mapping):
            raise RubricParseError(f"criterion entry is not an object: {entry!r}")
        name = entry.get("name")
        if name not in expected:
            raise RubricParseError(f"unknown or missing criterion name: {name!r}")
        if name in by_name:
            raise RubricParseError(f"duplicate criterion: {name!r}")
        score = entry.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise RubricParseError(f"criterion {name!r} score is not a number: {score!r}")
        if not 0.0 <= float(score) <= 1.0:
            raise RubricParseError(
                f"criterion {name!r} score {score} is out of range (expected [0, 1])"
            )
        evidence = entry.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            raise RubricParseError(f"criterion {name!r} has no evidence: {evidence!r}")
        by_name[name] = CriterionVerdict(
            name=name, score=_snap_to_coarse(float(score)), evidence=evidence
        )

    missing = expected - by_name.keys()
    if missing:
        raise RubricParseError(f"judge reply omitted criteria: {sorted(missing)}")
    return tuple(by_name[c.name] for c in rubric.criteria)


def weighted_score(verdicts: tuple[CriterionVerdict, ...], rubric: Rubric) -> float:
    """The rubric-weighted mean of the per-criterion scores -- the single [0, 1]
    number the judge contributes. Weighting is arithmetic over the model's coarse
    scores (ZFC: the judgment was the model's, the composition is ours)."""
    weights = {c.name: c.weight for c in rubric.criteria}
    total = sum(weights.values())
    return sum(v.score * weights[v.name] for v in verdicts) / total


class RubricJudge(Protocol):
    """Scores semantic diff quality against a rubric, in [0, 1]. The view is the
    blinded (task, run_output) `build_graded_view` produces. ``model`` is the pinned
    identity recorded on the judgment."""

    @property
    def model(self) -> str: ...

    def score(self, task: str, run_output: str, rubric: Rubric) -> float: ...


@dataclass(frozen=True)
class StubRubricJudge:
    """A deterministic, injectable judge -- NO model, NO network. The whole pipeline
    and every test run on this. Supply exactly one of ``fixed`` (a constant [0, 1]
    score) or ``fn`` (a pure function over the same view a real judge sees)."""

    fixed: float | None = None
    fn: Callable[[str, str, Rubric], float] | None = None
    model: str = "stub"

    def __post_init__(self) -> None:
        if (self.fixed is None) == (self.fn is None):
            raise ValueError("StubRubricJudge needs exactly one of fixed or fn")

    def score(self, task: str, run_output: str, rubric: Rubric) -> float:
        if self.fn is not None:
            return self.fn(task, run_output, rubric)
        if self.fixed is None:  # unreachable — __post_init__ guarantees one is set
            raise AssertionError("StubRubricJudge has neither fixed nor fn")
        return self.fixed


_GRADED_PROMPT_TEMPLATE = """\
You are grading a candidate code diff that attempts to resolve a software issue. You
are shown the issue, a reference (gold) diff already known to resolve it, and the
candidate diff. Judge ONLY the candidate diff, ONLY against the rubric below.

For EACH rubric criterion assign exactly one of these three scores:
  1.0 = fully satisfied, with specific evidence in the candidate diff
  0.5 = partially satisfied
  0.0 = not satisfied, OR you cannot cite specific evidence for it
Cite code-specific evidence (a file path, symbol name, or changed line) from the
CANDIDATE diff for every score; a criterion you cannot ground in the candidate must
score 0.0.

ISSUE AND REFERENCE:
{task}

CANDIDATE DIFF (the work being graded):
{run_output}

RUBRIC (score the candidate against these criteria):
{rubric_block}

Output STRICT JSON only, no prose:
{{"criteria": [
  {{"name": "<exact criterion name>", "score": 0.0, "evidence": "<path or symbol>"}}
]}}"""


@dataclass(frozen=True)
class ClaudeRubricJudge(IsolatedClaudeCallsite):
    """A judge backed by headless ``claude -p ... --output-format json``.

    Defaults to the locked Sonnet 4.6 build, overridable via
    ``MEMBENCH_GRADED_JUDGE_MODEL``. The model emits per-criterion coarse scores +
    evidence; ``score`` parses and weights them in code. The ``claude -p`` seam has
    no temperature flag, so determinism rests on the N-round median vote in
    `judge_graded`, not on temp 0 (see the module docstring). ``runner`` is injected
    so tests drive the parse path without spawning a real claude; every failure
    raises `RubricParseError` or
    `RuntimeError`, never a default score.

    ``isolation`` (mem-9ld4) is the clean-config surface the subprocess runs under,
    so no host/project agent (notably a ``code-reviewer``) can hijack the judge into
    answering as a reviewer; lazy semantics and the marker contract live on
    `IsolatedClaudeCallsite`. The MODEL and round count are unchanged -- only the
    config surface the judge loads is."""

    _isolation_label = "graded"

    model: str = ""
    timeout_s: float = DEFAULT_TIMEOUT_S
    runner: Runner = subprocess.run
    isolation: IsolatedJudgeConfig | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model",
            self.model or os.environ.get(ENV_GRADED_JUDGE_MODEL, DEFAULT_GRADED_JUDGE_MODEL),
        )

    def build_prompt(self, task: str, run_output: str, rubric: Rubric) -> str:
        """The rubric-grounded judge prompt. Pure -- assembles the model input from
        the blinded view and the rubric criteria."""
        return _GRADED_PROMPT_TEMPLATE.format(
            task=task, run_output=run_output, rubric_block=rubric.as_prompt_block()
        )

    def score(self, task: str, run_output: str, rubric: Rubric) -> float:
        reply = self._complete(self.build_prompt(task, run_output, rubric))
        return weighted_score(parse_criteria(reply, rubric), rubric)

    def _complete(self, prompt: str) -> str:
        reply = run_isolated_claude(
            prompt,
            isolation=self._resolved_isolation(),
            runner=self.runner,
            timeout_s=self.timeout_s,
            model=self.model,
            callsite="judge",
        )
        return unwrap_cli_json(reply)


@dataclass(frozen=True)
class GradedJudgment:
    """The S3 judge readout for one run. ``judge_score`` is the median over
    ``rounds`` calls; ``judge_confidence`` is the round agreement (1 - spread);
    ``divergence`` is |judge_score - mechanical_reference| (None when no mechanical
    reference was available), flagged when it exceeds the threshold. ``model`` and
    ``prompt_version`` make the score attributable and cache-invalidatable."""

    judge_score: float
    rounds: tuple[float, ...]
    judge_confidence: float
    mechanical_reference: float | None
    divergence: float | None
    divergence_flagged: bool
    model: str
    prompt_version: str = GRADED_PROMPT_VERSION


def _score_round_retrying_parse(
    judge: RubricJudge, task: str, run_output: str, rubric: Rubric
) -> float:
    """One judge round, re-taking a wrong-schema (unparseable) draw up to
    ``GRADED_JUDGE_MAX_ATTEMPTS`` times. Only ``RubricParseError`` is transient
    here -- every other failure (a [0,1] contract breach, a ``claude -p`` process
    error) propagates on the first draw. If all attempts are unparseable the last
    error is re-raised, so a persistently-broken judge fails loud rather than
    looping. Re-draws are noted on stderr so the batch log carries the
    wrong-schema rate."""
    last_exc: RubricParseError | None = None
    for attempt in range(1, GRADED_JUDGE_MAX_ATTEMPTS + 1):
        try:
            return score_completion(judge, task, run_output, rubric)
        except RubricParseError as exc:
            last_exc = exc
            if attempt < GRADED_JUDGE_MAX_ATTEMPTS:
                print(
                    f"graded judge: unparseable reply on attempt "
                    f"{attempt}/{GRADED_JUDGE_MAX_ATTEMPTS}, re-drawing ({exc})",
                    file=sys.stderr,
                )
    assert last_exc is not None  # MAX_ATTEMPTS >= 1, so the loop raised at least once
    raise last_exc


def judge_graded(
    judge: RubricJudge,
    *,
    issue_title: str,
    issue_body: str,
    candidate_diff: Mapping[str, str],
    gold_diff: Mapping[str, str],
    mechanical_reference: float | None,
    rubric: Rubric | None = None,
    rounds: int = DEFAULT_JUDGE_ROUNDS,
) -> GradedJudgment:
    """Score one run's candidate diff: build the blinded view, call ``judge``
    ``rounds`` times, take the median, derive the confidence and the
    mechanical-vs-judge divergence flag. Orchestration only -- the semantic judgment
    is the model's (inside `judge.score`); the median / spread / divergence are
    arithmetic over its outputs.

    ``judge_confidence`` is 1 - the round spread, so with ``rounds=1`` it is
    trivially 1.0 (a single sample has no spread to disagree with) -- the confidence
    is only meaningful at the default ``rounds=3``."""
    if rounds < 1:
        raise ValueError(f"rounds must be >= 1, got {rounds}")
    rubric = rubric or graded_rubric()
    task, run_output = build_graded_view(
        issue_title=issue_title,
        issue_body=issue_body,
        candidate_diff=candidate_diff,
        gold_diff=gold_diff,
    )
    scores = tuple(
        _score_round_retrying_parse(judge, task, run_output, rubric) for _ in range(rounds)
    )
    judge_score = median(scores)
    confidence = 1.0 - (max(scores) - min(scores))  # tight round agreement -> high
    divergence = None if mechanical_reference is None else abs(judge_score - mechanical_reference)
    return GradedJudgment(
        judge_score=judge_score,
        rounds=scores,
        judge_confidence=confidence,
        mechanical_reference=mechanical_reference,
        divergence=divergence,
        divergence_flagged=divergence is not None and divergence > GRADED_DIVERGENCE_THRESHOLD,
        model=getattr(judge, "model", "unknown"),
    )
