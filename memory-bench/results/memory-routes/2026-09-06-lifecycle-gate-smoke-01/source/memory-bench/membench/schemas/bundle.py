"""Task-bundle schema (mem-75t.7.2, plan §2 + §9.3) -- the grid's eval object.

Mirrors codeprobe ``models/task.py`` (``Task``/``TaskMetadata``/``TaskVerification``)
re-shaped for a bead-sourced, PR-less corpus:

- the **issue** leg is the bead's title/body (leak-guarded at assembly, never here --
  a schema cannot know which strings are outcome labels); for workflow-formula
  records it is sourced from the bead named by ``metadata["gc.var.issue"]``, with
  ``issue_work_id`` as the provenance pointer;
- the **output** leg embeds the P0 `ReplayResult` verbatim (per-file gold diffs +
  classified replay outcomes + ``replay_success_rate``) rather than re-projecting it:
  the replay types ARE the output contract, and re-stating them would let the two
  drift;
- ``oracle_context`` is None until oracle curation (mem-75t.7.3) fills it -- absence
  is "not yet curated", distinguishable from a curated-but-empty oracle;
- ``env`` makes the bundle a self-contained RUNNABLE eval object (plan §9.3): repo +
  base_commit are the checkout anchors, base_image the toolchain -- no out-of-band
  rig map needed downstream;
- ``loo_excluded_work_ids`` is the bundle-level LOO INVARIANT: the record ids any
  grid run must withhold from memory arms (own work + siblings), stored IN the
  bundle so the exclusion is mechanical, not a convention;
- ``verification`` carries the dual sub-score slots (mem-75t.7.5 fills them); both
  legs stay None until scored, so "unscored" never reads as 0.0.

All models are frozen value objects (membench schema idiom). This module depends on
`membench.bundle.replay` for the embedded output types; neither package ``__init__``
imports this module, keeping the import graph acyclic.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from membench.bundle.replay import ReplayResult

# Plan §9.5's scoring-policy vocabulary; "direct" is the current probe-grade leg.
ScoringPolicy = Literal["direct", "min", "mean", "weighted"]

# The fail-to-pass headline (mirrors harbor.ftp_curate.FtpType). A structural fact --
# behavioral (a red->green nodeid that ran at the parent), feature-presence (only
# new-test collection errors at the parent), or none -- not a quality judgment.
FtpType = Literal["behavioral", "feature-presence", "none"]


class FtpOracle(BaseModel):
    """A landing commit's curated fail-to-pass test set (mem-bxhh.3.2), the
    test-reproduction leg's ground truth for a real landing-commit anchor bundle.

    Carries the same split `harbor.ftp_curate.CommitFtp` produces -- ``ftp_tests``
    (passes at landing, not at parent) partitioned into ``behavioral`` (the test
    ran red at the parent -- the strong discriminator) and ``feature_presence`` (a
    new test that only collection-errored at the parent). ``behavioral`` may be
    empty for a feature-presence commit; absence of behavioral tests is a real
    property, not missing data. Defined HERE rather than imported from harbor so
    the schema package stays an import leaf (no schema -> harbor edge); the
    materializer maps the harbor dataclass onto this model."""

    model_config = ConfigDict(frozen=True)

    commit: str = Field(min_length=1)
    parent: str = Field(min_length=1)
    ftp_tests: tuple[str, ...] = ()
    behavioral: tuple[str, ...] = ()
    feature_presence: tuple[str, ...] = ()
    type: FtpType = "none"

    @model_validator(mode="after")
    def _coherent_split(self) -> "FtpOracle":
        """Enforce `ftp_curate.classify_ftp`'s contract at the schema boundary, so a
        drifted or hand-edited oracle cannot materialize an incoherent bundle that
        scores the wrong discriminator: ``behavioral``/``feature_presence`` are a
        DISJOINT partition of ``ftp_tests``, and ``type`` is the structural headline
        (behavioral if any behavioral, else feature-presence if any of those, else
        none)."""
        behavioral, feature = set(self.behavioral), set(self.feature_presence)
        if behavioral & feature:
            raise ValueError(
                f"behavioral and feature_presence overlap: {sorted(behavioral & feature)}"
            )
        if behavioral | feature != set(self.ftp_tests):
            raise ValueError(
                "behavioral | feature_presence must equal ftp_tests "
                f"(got {len(behavioral | feature)} vs {len(set(self.ftp_tests))})"
            )
        expected = "behavioral" if behavioral else "feature-presence" if feature else "none"
        if self.type != expected:
            raise ValueError(f"type {self.type!r} disagrees with the split (expected {expected!r})")
        return self


class CuratedOracle(BaseModel):
    """The P2 oracle-context leg (codeprobe ``oracle_answer``/``oracle_tiers``).

    A placeholder TYPE today: mem-75t.7.3 populates it via grep/AST/SG consensus +
    curator. ``oracle_backends_consensus`` is the anti-tautology provenance --
    which backends contributed a kept oracle file."""

    model_config = ConfigDict(frozen=True)

    oracle_answer: tuple[str, ...] = ()
    # file -> tier ("required" | "supplementary" | "context"), codeprobe-shaped.
    oracle_tiers: tuple[tuple[str, str], ...] = ()
    oracle_backends_consensus: tuple[str, ...] = ()
    # The mem-9ld4 curator-isolation marker (see `judge_config.IsolatedJudgeConfig
    # .marker`). None when no Tier-2 LLM vote fired this build (consensus-only, or
    # use_llm=False -- today's only batch caller) or the curator has no isolation
    # surface to attest (mem-x5d3).
    curator_isolation: dict[str, object] | None = None


class BundleVerification(BaseModel):
    """Dual-verifier slots (codeprobe ``TaskVerification``, ported weights).

    Both sub-scores are None until mem-75t.7.5 scores a run against the bundle --
    the direct leg (gold-diff / test reproduction) and the comprehension leg
    (artifact F1 vs the oracle file list). None means "not scored", never 0.0."""

    model_config = ConfigDict(frozen=True)

    scoring_policy: ScoringPolicy = "direct"
    weight_direct: float = 0.5
    weight_artifact: float = 0.5
    score_direct: float | None = Field(default=None, ge=0.0, le=1.0)
    score_artifact: float | None = Field(default=None, ge=0.0, le=1.0)
    # The direct leg's fail-to-pass ground truth for a real landing-commit anchor
    # bundle (mem-bxhh.3.2): the curated red->green test set the graded arm runs.
    # None for trace-replayed bundles, which have no per-commit ftp oracle.
    ftp_oracle: FtpOracle | None = None


class BundleEnv(BaseModel):
    """The env-recon anchors that make the bundle runnable (plan §9.3): check out
    ``repo`` at ``base_commit``, run the agent in ``base_image``. All required --
    a bundle with a missing anchor is not admissible, so the schema refuses it."""

    model_config = ConfigDict(frozen=True)

    repo: str = Field(min_length=1)
    base_commit: str = Field(min_length=1)
    base_image: str = Field(min_length=1)


class TaskBundle(BaseModel):
    """One evaluable task bundle: ``issue -> trace -> output (+ oracle_context)``."""

    model_config = ConfigDict(frozen=True)

    # work_id flows into filesystem paths (probe/grid result files, job dirs --
    # including rmtree targets in the 3-arm driver's scrub), so the charset is
    # locked down at the schema boundary: bead-id shaped (dots allowed for
    # hierarchy, e.g. mem-75t.9), never a path separator or a leading dot.
    work_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    rig: str = Field(min_length=1)
    # The bead-sourced issue leg. Body may legitimately be empty: current ingest
    # carries only the title (see assess._body_text's forward-shaped read).
    issue_title: str
    issue_body: str = ""
    # Issue-leg provenance: the work_id of the REFERENCED bead whose title/body
    # supplied the issue leg, when it is not the record itself. Workflow-formula
    # records (gc.kind=workflow) store the formula name in their own title and
    # name the real task statement via metadata["gc.var.issue"] -- the assembler
    # resolves that bead and records it here. None means the record's own text IS
    # the issue leg. When set, the id is always in ``loo_excluded_work_ids`` (the
    # issue bead is the same work).
    issue_work_id: str | None = None
    # The resolved transcript path (record.trace.jsonl_path) -- the mined source.
    trace_ref: str = Field(min_length=1)
    # The P0 replay product, embedded whole: gold diffs + outcomes + fidelity rate.
    output: ReplayResult
    oracle_context: CuratedOracle | None = None
    env: BundleEnv
    # Sorted, deduplicated: own work_id + supersedes closure + convoy/pr/branch
    # siblings (validity semantics). Never empty -- self-exclusion is unconditional.
    loo_excluded_work_ids: tuple[str, ...] = Field(min_length=1)
    verification: BundleVerification = BundleVerification()
