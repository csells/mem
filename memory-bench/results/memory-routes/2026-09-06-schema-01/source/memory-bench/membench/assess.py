"""SELECT/assess — rank a rig's beads by benchmarking potential (mem-75t.7.4, P3).

A port of codeprobe's ``assess/heuristics.py`` rubric onto the bead-shaped corpus.
codeprobe scores a *repository* and leans on merge history (``list_merged_prs``,
merge-commit counts); this corpus has no PR linkage (mem-apg.5), so every
merge-history signal is replaced with what the WorkRecords actually carry:

  - ``spec_quality``        — title/body length and *structural* specificity
                              (a dedicated acceptance-criteria field, a sectioned
                              markdown body). Structure only — no keyword matching.
  - ``trace_signal``        — a resolvable transcript (``trace.jsonl_path``) and its
                              parsed volume (``trace.n_turns``): the trace is the
                              gold-diff source (plan §1 Option A), so no trace means
                              nothing to mine.
  - ``mutation_signal``     — the transcript's Edit/Write/MultiEdit call count, the
                              replayable volume the gold diff is mined from
                              (mem-75t.7.1 validation: 39/111 eligible beads are
                              shell-only with ZERO mutation calls, and replay needs
                              >=3 calls to matter). The count arrives via an
                              injectable provider so scoring stays file-free in
                              tests; the default provider reads the transcript and
                              counts via ``bundle.replay.parse_mutation_calls`` —
                              the exact parse the replay reconstructor uses, so the
                              signal and the gold-diff source can never disagree.
                              Zero calls is a hard ranking gate like
                              ``env_reconstructable``: nothing to replay means no
                              gold diff, dead weight regardless of other scores.
  - ``closed``              — lifecycle agreement (``status == "closed"`` AND a
                              ``closed`` timestamp); P1's admission filter requires
                              closed, so open work is pre-discounted here.
  - ``repo_activity``       — pool-level bead count and commit-anchor count per rig
                              (the merge-commit replacement): a rig with many beads
                              and many env anchors yields a richer task batch.
  - ``env_reconstructable`` — plan §9.4: the rig maps to a local repo (env_recon's
                              rig map, injectable), the mapped path passes a cheap
                              injectable checkout probe (NO git is run here), and the
                              record carries a repo+base_commit anchor (exact) or at
                              least a ``started``/``created`` timestamp that
                              ``env_recon.resolve_base_commit`` could anchor
                              (approximate). A bundle you cannot run an agent
                              against is dead weight regardless of other scores, so
                              this criterion also acts as the ranking gate.

Input is an iterable of Mapping-shaped WorkRecords — the same JSON shape
``validity.query_from_record`` reads (``work_id``/``rig``/``lifecycle``/``trace``/
``outcome``/``provenance``). The module never opens the SQLite store and never
shells out: it is pure arithmetic over fields the caller already loaded.

ZFC boundary: this is the *mechanism* half of SELECT — deterministic arithmetic
sub-scores with transparent, documented tiebreakers (an allowed exception:
deterministic ranking with explicit tiebreaker rules). The fixed tier thresholds
grade signal *presence/volume*, not meaning; any semantic "is this task
well-scoped?" judgment stays with the model that consumes this ranking, and no
LLM is in the loop in this wave.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from membench.bundle.replay import parse_mutation_calls
from membench.harbor.env_recon import DEFAULT_RIG_REPOS

# ---------------------------------------------------------------------------
# Fixed rubric — deterministic sub-scores, transparent weights
# ---------------------------------------------------------------------------

RUBRIC_V1: tuple[str, ...] = (
    "spec_quality",
    "trace_signal",
    "mutation_signal",
    "closed",
    "repo_activity",
    "env_reconstructable",
)

# mutation_signal and env_reconstructable carry the most weight: the mutation
# calls are the replayable gold-diff source, and an unrunnable bundle is dead
# weight (plan §9.4) — both also act as hard ranking gates at zero.
WEIGHTS: Mapping[str, float] = {
    "spec_quality": 0.15,
    "trace_signal": 0.15,
    "mutation_signal": 0.25,
    "closed": 0.10,
    "repo_activity": 0.10,
    "env_reconstructable": 0.25,
}

# Tier thresholds. These grade structural volume (lengths, counts), mirroring the
# codeprobe tier style (1.0 / 0.7 / 0.4 / floor) so ported scores stay comparable.
_TITLE_MIN_CHARS = 10  # below this a title is a label, not a task statement
_BODY_SECTIONED_MIN_CHARS = 120  # a sectioned body must also have real content
_TRACE_RICH_TURNS = 20  # enough activity to mine a non-trivial diff
_TRACE_MIN_TURNS = 5  # below this the transcript is a stub
# Mutation-call tiers grade STRUCTURAL VOLUME (how many replayable calls the
# transcript carries), not the meaning of the edits. 3 is the replay-validation
# floor (mem-75t.7.1: replay needs >=3 calls to matter); 10+ saturates the tier.
_MUTATION_HIGH_CALLS = 10
_MUTATION_MIN_CALLS = 3
_BEADS_RICH, _BEADS_MODERATE, _BEADS_FEW = 50, 20, 5
_COMMITS_RICH, _COMMITS_MODERATE = 20, 5

# Injectable "could we check this repo out?" probe. The default is deliberately a
# cheap existence test (the bead spec: do NOT run git in the rubric) — callers that
# need a stronger guarantee inject one.
CheckoutProbe = Callable[[Path], bool]


def _default_checkout_probe(repo: Path) -> bool:
    return repo.is_dir()


# Injectable mutation-call counter: (work_id, trace_path) -> count. Unit tests
# inject a file-free stub; the default reads the resolved transcript. This is the
# module's second sanctioned IO probe (alongside the checkout probe) — everything
# else stays pure arithmetic over already-loaded fields.
MutationCountProvider = Callable[[str, str], int]


def default_mutation_count_provider(work_id: str, trace_path: str) -> int:
    """Count the transcript's Edit/Write/MultiEdit calls by reading the resolved
    transcript file with ``bundle.replay.parse_mutation_calls`` — the identical
    parse the gold-diff replay uses. Fails loud on an unreadable transcript: a
    record pointing at a missing trace file is a provenance bug, not a zero."""
    stream = Path(trace_path).read_text(encoding="utf-8")
    return len(parse_mutation_calls(stream))


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CriterionScore:
    """One rubric criterion's sub-score in [0, 1] with its stated reasoning —
    the per-candidate transparency the ZFC ranking exception requires."""

    name: str
    score: float
    reasoning: str


@dataclass(frozen=True)
class RepoSignals:
    """Pool-level per-rig aggregates — the merge-history replacement. A commit
    anchor is any of ``outcome.commit_sha`` / ``outcome.base_commit`` /
    ``provenance.base_commit``."""

    rig: str
    bead_count: int
    commit_count: int


@dataclass(frozen=True)
class CandidateAssessment:
    """A candidate's full scorecard: per-criterion sub-scores, the weighted
    overall, and the fields the tiebreakers read (so the ranking is auditable
    from the assessment alone)."""

    work_id: str
    rig: str
    overall: float
    env_reconstructable: bool
    replayable: bool
    trace_turns: int
    mutation_calls: int
    scores: tuple[CriterionScore, ...]

    def criterion(self, name: str) -> CriterionScore:
        for score in self.scores:
            if score.name == name:
                return score
        raise KeyError(f"unknown rubric criterion: {name!r} (rubric: {RUBRIC_V1})")


# ---------------------------------------------------------------------------
# Structural field extraction (validity.query_from_record's record shape)
# ---------------------------------------------------------------------------


def _mapping(record: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = record.get(key)
    return value if isinstance(value, Mapping) else {}


def _text(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    return value.strip() if isinstance(value, str) else ""


def _body_text(record: Mapping[str, Any]) -> str:
    """The long-form spec text. Current ingest carries only ``title``; this reads
    the forward-shaped ``description``/``body`` fields when present so the rubric
    upgrades for free once the bead body lands in the export."""
    return _text(record, "description") or _text(record, "body")


def _is_sectioned(body: str) -> bool:
    """Markdown-structural: the body has at least one heading line. This is syntax
    shape (the bead author organized the spec into sections), not a judgment on
    what the sections say."""
    return any(line.lstrip().startswith("#") for line in body.splitlines())


def _trace_turns(record: Mapping[str, Any]) -> int:
    n_turns = _mapping(record, "trace").get("n_turns")
    return n_turns if isinstance(n_turns, int) else 0


def _has_commit_anchor(record: Mapping[str, Any]) -> bool:
    outcome = _mapping(record, "outcome")
    provenance = _mapping(record, "provenance")
    return bool(
        outcome.get("commit_sha") or outcome.get("base_commit") or provenance.get("base_commit")
    )


def _exact_env_anchor(record: Mapping[str, Any]) -> bool:
    """repo + base_commit on either env-anchor path (outcome = PR-authoritative,
    provenance = locally derived) — enough to check out the exact baseline."""
    for key in ("outcome", "provenance"):
        anchor = _mapping(record, key)
        if anchor.get("repo") and anchor.get("base_commit"):
            return True
    return False


def _timestamp_anchor(record: Mapping[str, Any]) -> str | None:
    """The timestamp ``env_recon.resolve_base_commit`` would anchor against —
    the same started-falling-back-to-created boundary as ``query_from_record``."""
    lifecycle = _mapping(record, "lifecycle")
    return lifecycle.get("started") or lifecycle.get("created")


# ---------------------------------------------------------------------------
# Per-criterion scoring
# ---------------------------------------------------------------------------


def _score_spec_quality(record: Mapping[str, Any]) -> CriterionScore:
    title = _text(record, "title")
    body = _body_text(record)
    has_acceptance = bool(_text(record, "acceptance_criteria"))
    sectioned = _is_sectioned(body) and len(body) >= _BODY_SECTIONED_MIN_CHARS

    if len(title) >= _TITLE_MIN_CHARS and body and (has_acceptance or sectioned):
        score, reason = 1.0, "title + body with acceptance criteria / sectioned spec"
    elif len(title) >= _TITLE_MIN_CHARS and body:
        score, reason = 0.7, f"title + {len(body)}-char body, unstructured"
    elif len(title) >= _TITLE_MIN_CHARS:
        score, reason = 0.4, f"{len(title)}-char title only — no body text"
    else:
        score, reason = 0.1, f"{len(title)}-char title — a label, not a task statement"
    return CriterionScore(name="spec_quality", score=score, reasoning=reason)


def _score_trace_signal(record: Mapping[str, Any]) -> CriterionScore:
    trace = _mapping(record, "trace")
    turns = _trace_turns(record)
    if not trace.get("jsonl_path"):
        score, reason = 0.0, "no trace — nothing to mine a gold diff from"
    elif turns == 0:
        score, reason = 0.4, "trace present but unparsed (no turn count)"
    elif turns >= _TRACE_RICH_TURNS:
        score, reason = 1.0, f"{turns} turns — rich transcript"
    elif turns >= _TRACE_MIN_TURNS:
        score, reason = 0.7, f"{turns} turns — moderate transcript"
    else:
        score, reason = 0.3, f"{turns} turns — stub transcript, little to mine"
    return CriterionScore(name="trace_signal", score=score, reasoning=reason)


def _score_mutation_signal(
    record: Mapping[str, Any], provider: MutationCountProvider
) -> tuple[CriterionScore, int]:
    """Score the replayable mutation volume; returns ``(score, count)`` so the
    assessment can carry the raw count for the tiebreaker and the artifact."""
    name = "mutation_signal"
    trace_path = _mapping(record, "trace").get("jsonl_path")
    if not trace_path:
        return CriterionScore(name, 0.0, "no trace — nothing to replay"), 0
    count = provider(str(record["work_id"]), str(trace_path))
    if count < 0:
        raise ValueError(
            f"mutation-count provider returned {count} for {record.get('work_id')!r} "
            "— counts must be non-negative"
        )
    if count == 0:
        score, reason = 0.0, "0 mutation calls — shell-only session, no gold diff to replay"
    elif count >= _MUTATION_HIGH_CALLS:
        score, reason = 1.0, f"{count} mutation calls — high replay volume"
    elif count >= _MUTATION_MIN_CALLS:
        score, reason = 0.7, f"{count} mutation calls — moderate replay volume"
    else:
        score, reason = (
            0.4,
            f"{count} mutation calls — below the >={_MUTATION_MIN_CALLS}-call replay floor",
        )
    return CriterionScore(name=name, score=score, reasoning=reason), count


def _score_closed(record: Mapping[str, Any]) -> CriterionScore:
    lifecycle = _mapping(record, "lifecycle")
    status_closed = lifecycle.get("status") == "closed"
    has_timestamp = bool(lifecycle.get("closed"))
    if status_closed and has_timestamp:
        score, reason = 1.0, "closed status with closed timestamp"
    elif status_closed or has_timestamp:
        score, reason = 0.5, "lifecycle disagrees: closed status XOR closed timestamp"
    else:
        score, reason = 0.0, f"not closed (status={lifecycle.get('status')!r})"
    return CriterionScore(name="closed", score=score, reasoning=reason)


def _tier(value: int, rich: int, moderate: int, few: int) -> float:
    if value >= rich:
        return 1.0
    if value >= moderate:
        return 0.7
    if value >= few:
        return 0.4
    return 0.1


def _score_repo_activity(signals: RepoSignals) -> CriterionScore:
    bead_tier = _tier(signals.bead_count, _BEADS_RICH, _BEADS_MODERATE, _BEADS_FEW)
    commit_tier = _tier(signals.commit_count, _COMMITS_RICH, _COMMITS_MODERATE, 1)
    score = (bead_tier + commit_tier) / 2
    reason = (
        f"rig {signals.rig!r}: {signals.bead_count} beads, "
        f"{signals.commit_count} commit anchors in pool"
    )
    return CriterionScore(name="repo_activity", score=score, reasoning=reason)


def _score_env_reconstructable(
    record: Mapping[str, Any],
    rig_repos: Mapping[str, Path],
    checkout_probe: CheckoutProbe,
) -> CriterionScore:
    name = "env_reconstructable"
    rig = str(record["rig"])
    repo = rig_repos.get(rig)
    if repo is None:
        return CriterionScore(name, 0.0, f"no local repo mapped for rig {rig!r}")
    if not checkout_probe(repo):
        return CriterionScore(name, 0.0, f"mapped repo {repo} failed the checkout probe")
    if _exact_env_anchor(record):
        return CriterionScore(name, 1.0, f"repo {repo} checkoutable with repo+base_commit anchor")
    timestamp = _timestamp_anchor(record)
    if timestamp:
        return CriterionScore(
            name, 0.7, f"repo {repo} checkoutable; base commit resolvable from {timestamp}"
        )
    return CriterionScore(name, 0.0, "checkoutable repo but no commit or timestamp anchor")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def gather_pool_signals(records: Iterable[Mapping[str, Any]]) -> dict[str, RepoSignals]:
    """Per-rig bead count + commit-anchor count over the candidate pool — the
    bead-derived replacement for codeprobe's merge-commit history."""
    beads: dict[str, int] = {}
    commits: dict[str, int] = {}
    for record in records:
        rig = str(record["rig"])
        beads[rig] = beads.get(rig, 0) + 1
        if _has_commit_anchor(record):
            commits[rig] = commits.get(rig, 0) + 1
    return {
        rig: RepoSignals(rig=rig, bead_count=count, commit_count=commits.get(rig, 0))
        for rig, count in beads.items()
    }


def assess_candidate(
    record: Mapping[str, Any],
    *,
    pool_signals: Mapping[str, RepoSignals],
    rig_repos: Mapping[str, Path] = DEFAULT_RIG_REPOS,
    checkout_probe: CheckoutProbe = _default_checkout_probe,
    mutation_count_provider: MutationCountProvider = default_mutation_count_provider,
) -> CandidateAssessment:
    """Score one candidate against ``RUBRIC_V1``; pure arithmetic, no IO beyond
    the injected checkout probe and mutation-count provider."""
    rig = str(record["rig"])
    signals = pool_signals.get(rig, RepoSignals(rig=rig, bead_count=0, commit_count=0))
    env = _score_env_reconstructable(record, rig_repos, checkout_probe)
    mutation, mutation_calls = _score_mutation_signal(record, mutation_count_provider)
    scores = (
        _score_spec_quality(record),
        _score_trace_signal(record),
        mutation,
        _score_closed(record),
        _score_repo_activity(signals),
        env,
    )
    overall = sum(s.score * WEIGHTS[s.name] for s in scores)
    return CandidateAssessment(
        work_id=str(record["work_id"]),
        rig=rig,
        overall=overall,
        env_reconstructable=env.score > 0.0,
        replayable=mutation.score > 0.0,
        trace_turns=_trace_turns(record),
        mutation_calls=mutation_calls,
        scores=scores,
    )


def _rank_key(assessment: CandidateAssessment) -> tuple[int, int, float, float, int, int, str]:
    """Explicit, total tiebreaker order (documented contract):

    1. env-reconstructable gate — runnable candidates rank above every
       unrunnable one regardless of other scores (plan §9.4: dead weight);
    2. replayable gate — zero mutation calls means no gold diff to mine
       (mem-75t.7.1: shell-only sessions are not bundle-able from trace replay);
    3. weighted overall, descending;
    4. env_reconstructable sub-score, descending (exact anchor beats approximate);
    5. mutation-call count, descending (more replayable volume to mine);
    6. trace turn count, descending (more transcript to mine);
    7. work_id, ascending — the deterministic total-order anchor.
    """
    return (
        0 if assessment.env_reconstructable else 1,
        0 if assessment.replayable else 1,
        -assessment.overall,
        -assessment.criterion("env_reconstructable").score,
        -assessment.mutation_calls,
        -assessment.trace_turns,
        assessment.work_id,
    )


def rank_candidates(
    records: Iterable[Mapping[str, Any]],
    *,
    rig_repos: Mapping[str, Path] = DEFAULT_RIG_REPOS,
    checkout_probe: CheckoutProbe = _default_checkout_probe,
    mutation_count_provider: MutationCountProvider = default_mutation_count_provider,
    top_n: int | None = None,
) -> list[CandidateAssessment]:
    """Rank a pool of WorkRecords by benchmarking potential.

    Materializes the pool once (the repo_activity criterion is a pool-level
    aggregate), assesses every candidate, and sorts by ``_rank_key`` — so the
    same pool yields the same ranking regardless of input order. ``top_n``
    truncates after ranking; ``None`` returns the full ordered list.
    """
    pool = list(records)
    signals = gather_pool_signals(pool)
    ranked = sorted(
        (
            assess_candidate(
                record,
                pool_signals=signals,
                rig_repos=rig_repos,
                checkout_probe=checkout_probe,
                mutation_count_provider=mutation_count_provider,
            )
            for record in pool
        ),
        key=_rank_key,
    )
    return ranked if top_n is None else ranked[:top_n]


__all__ = [
    "RUBRIC_V1",
    "WEIGHTS",
    "CandidateAssessment",
    "CheckoutProbe",
    "CriterionScore",
    "MutationCountProvider",
    "RepoSignals",
    "assess_candidate",
    "default_mutation_count_provider",
    "gather_pool_signals",
    "rank_candidates",
]
