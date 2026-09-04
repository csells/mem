"""mem-9q8dg — the E1 twin corpus and its outcome-side necessity preflight."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from membench.generators.enterprise_workflow import (
    _SUBJECTS,
    fact_subject,
    fact_value,
    materialize_world,
)
from membench.grading.paired_ci import paired_delta_ci
from membench.metrics.scorers import states_value
from membench.runner import e1_necessity_preflight, toolreq_corpus
from membench.runner.e1_necessity_preflight import (
    EXIT_ACCEPTED,
    EXIT_NO_CORPUS,
    EXIT_REFUSED,
    EXIT_REJECTED,
    EXIT_UNVERIFIED,
    NECESSARY_PASS_CEILING,
    UNNECESSARY_PASS_FLOOR,
    VERDICT_UNVERIFIED,
    necessity_preflight,
)
from membench.runner.toolreq_corpus import (
    CONTEXT_SEPARATOR,
    load_twin_corpus,
    twin_tasks,
    unnecessary_twin,
    variant_split,
)
from membench.runner.toolreq_realagent import (
    VARIANT_NECESSARY,
    VARIANT_UNNECESSARY,
    ToolReqRealAgentTask,
    adapt_sequence,
    task_fingerprint,
)
from membench.schemas.sequence import BenchmarkSequence
from membench.schemas.world import Channel, EnterpriseWorld, Persona, Project, Team
from tests.toolreq_helpers import corpus, multi_value_corpus


def _twin_corpus(tmp_path: Path, *work_ids: str):
    corpus_dir = tmp_path / "corpus"
    corpus(tmp_path, *work_ids)  # seeds tmp_path/corpus/0/sequences.json
    return load_twin_corpus(corpus_dir)


def test_twins_share_a_pair_key_and_split_evenly(tmp_path: Path) -> None:
    _, tasks = _twin_corpus(tmp_path, "w-0", "w-1")
    split = variant_split(tasks)
    assert len(split[VARIANT_NECESSARY]) == len(split[VARIANT_UNNECESSARY]) == 2
    assert {t.pair_key for t in split[VARIANT_NECESSARY]} == {
        t.pair_key for t in split[VARIANT_UNNECESSARY]
    }
    # ...but never a shared RESULT id: twins that collide on disk would overwrite each other.
    assert len({t.result_id for t in tasks}) == len(tasks)


def test_the_unnecessary_twin_states_the_current_value_and_never_a_stale_one(
    tmp_path: Path,
) -> None:
    _, tasks = _twin_corpus(tmp_path, "w-0")
    necessary, unnecessary = tasks
    forbidden = necessary.goal_step.outcome_checks[0].requires_action[0].forbidden_values
    assert forbidden  # the fixture really does carry a superseded value to guard against
    for value in necessary.current_opaque_values:
        # The whole contrast: the necessary half withholds it, the twin states it.
        assert not states_value(necessary.goal_step.user_request, value)
        assert states_value(unnecessary.goal_step.user_request, value)
    for value in forbidden:
        assert not states_value(unnecessary.goal_step.user_request, value)
    # Scoring is identical, so the halves differ only in what is in context.
    assert (
        unnecessary.goal_step.outcome_checks[0].requires_action
        == necessary.goal_step.outcome_checks[0].requires_action
    )
    assert unnecessary.oracle_memory == {}
    assert unnecessary.goal_step.expected_memory_reads == []
    assert necessary.goal_step.memory_necessary is True
    assert unnecessary.goal_step.memory_necessary is False


def _subject_value_pairs(necessary: ToolReqRealAgentTask) -> list[tuple[str, str]]:
    """The (subject, value) pairs the twin's context block should carry, rebuilt HERE from the
    necessary half's oracle facts rather than imported from the builder -- so a builder that
    started pairing values with the wrong subjects reds this suite instead of agreeing with it.

    Sorted on the rendered line, which is how the block orders itself."""
    pairs = [
        (fact_subject(content), fact_value(content))
        for content in necessary.oracle_memory.values()
    ]
    return sorted(pairs, key=lambda pair: f"- {pair[0]} is {pair[1]}")


def _requested_subjects(necessary: ToolReqRealAgentTask) -> list[str]:
    """The subjects the goal request names, in the order it names them -- the order a positional
    pairing would use, and the reason this fixture authors ``arg_values`` against it."""
    head = necessary.goal_step.user_request.split("apply the current value of:", 1)[1]
    return [subject.strip() for subject in head.split(".", 1)[0].split(",")]


def test_the_non_value_text_of_a_twin_pair_is_identical(tmp_path: Path) -> None:
    # The confound this corpus must not carry (arXiv 2605.09252). E1's endpoint is P(agent
    # chooses to consult memory), so ANY wording present in one half only and absent from the
    # other is a prompt-only treatment on the measured behaviour. Off the values themselves the
    # twin's request must be the necessary request plus a fixed, behaviour-silent scaffold.
    _, tasks = _twin_corpus(tmp_path, "w-0")
    necessary, unnecessary = tasks

    # The heading is re-typed here, NOT imported: this test's job is to red when the wording
    # changes, and importing the constant would let "no recall required" walk back in silently.
    prefix, separator, block = unnecessary.goal_step.user_request.partition(
        CONTEXT_SEPARATOR + "Current state:\n"
    )
    assert separator, unnecessary.goal_step.user_request
    assert prefix == necessary.goal_step.user_request
    # ...and the block is the values, each under the subject it belongs to, and nothing else —
    # no provenance prose, no framing. The subject is not new wording: the necessary request
    # already names it, so the twin repeats a phrase rather than introducing one, which is what
    # keeps the pair's non-value text a fixed scaffold.
    #
    # This assertion used to demand BARE values, and that was the defect, not the guarantee: a
    # line reading `- toolreq-efc91a631a8d` does not read as a value, and the arm built to be the
    # easy half refused every leg of the staged fire. The property worth holding is that the twin
    # adds no behaviour-directing text, not that it adds no text.
    assert block.splitlines() == [
        f"- {subject} is {value}"
        for subject, value in _subject_value_pairs(necessary)
    ]
    for subject, _value in _subject_value_pairs(necessary):
        assert subject in necessary.goal_step.user_request


def test_twins_are_distinct_worlds_to_the_cache(tmp_path: Path) -> None:
    # Same work_id, different measurement: a shared fingerprint would let a cached necessary
    # cell be served as the unnecessary half's result.
    #
    # Asserted on two tasks differing ONLY in ``variant``. Comparing the real twins instead is
    # vacuous — their goal_step and oracle_memory differ too, so the assertion holds even with
    # ``"variant": task.variant`` deleted from ``task_fingerprint``, i.e. it passes whether the
    # thing it names works or not.
    _, tasks = _twin_corpus(tmp_path, "w-0")
    necessary = tasks[0]
    relabelled = dataclasses.replace(necessary, variant=VARIANT_UNNECESSARY)
    assert relabelled.goal_step is necessary.goal_step  # nothing else moved
    assert task_fingerprint(relabelled) != task_fingerprint(necessary)
    assert task_fingerprint(tasks[0]) != task_fingerprint(tasks[1])


def test_a_twin_of_a_twin_is_refused(tmp_path: Path) -> None:
    _, tasks = _twin_corpus(tmp_path, "w-0")
    with pytest.raises(ValueError, match="can only twin"):
        unnecessary_twin(tasks[1])


def test_paired_estimator_imputes_nothing_over_the_twin_corpus(tmp_path: Path) -> None:
    # The reason twins share a key at all (bead correction 1). Pairing by ``pair_key`` matches
    # every task; ``n_imputed_zero == 0`` is the assertion that the estimator is reading real
    # deltas rather than fabricating them.
    _, tasks = _twin_corpus(tmp_path, "w-0", "w-1", "w-2")
    split = variant_split(tasks)
    unnecessary_rate = {t.pair_key: 1.0 for t in split[VARIANT_UNNECESSARY]}
    necessary_rate = {t.pair_key: 0.25 for t in split[VARIANT_NECESSARY]}
    ci = paired_delta_ci(unnecessary_rate, necessary_rate, population="itt", n_resamples=200)
    assert ci.n_imputed_zero == 0
    assert ci.n_pairs == 3
    assert ci.delta == pytest.approx(-0.75)


def test_keying_the_halves_apart_fabricates_a_confident_zero(tmp_path: Path) -> None:
    # The defect the shared key exists to prevent, pinned so a future "disambiguate the ids"
    # refactor cannot reintroduce it silently: key by ``result_id`` and the two halves are
    # disjoint, so every delta is imputed 0.0 and the estimator reports 0.0 regardless of the
    # truth — here, of a real -0.75.
    _, tasks = _twin_corpus(tmp_path, "w-0", "w-1", "w-2")
    split = variant_split(tasks)
    unnecessary_rate = {t.result_id: 1.0 for t in split[VARIANT_UNNECESSARY]}
    necessary_rate = {t.result_id: 0.25 for t in split[VARIANT_NECESSARY]}
    ci = paired_delta_ci(unnecessary_rate, necessary_rate, population="itt", n_resamples=200)
    assert ci.n_imputed_zero == 6
    assert ci.delta == 0.0 and ci.ci_low == 0.0 and ci.ci_high == 0.0


def test_cli_json_labels_both_classes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    corpus(tmp_path, "w-0", "w-1")
    assert toolreq_corpus.main(["--corpus-dir", str(tmp_path / "corpus"), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    labels = [task["goal_step"]["memory_necessary"] for task in payload["tasks"]]
    assert labels.count(True) == labels.count(False) == 2
    assert payload["n_pairs"] == 2


def test_cli_refuses_an_empty_corpus(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    assert toolreq_corpus.main(["--corpus-dir", str(tmp_path / "empty"), "--json"]) == 1


def test_dry_run_preflight_separates_the_halves(tmp_path: Path) -> None:
    # Wiring only — the simulated runner copies values that are in the prompt, so this shows the
    # corpus GEOMETRY is right (unnecessary solvable with no memory, necessary not) and nothing
    # about a real agent. ``verified`` must stay false for exactly that reason.
    _, tasks = _twin_corpus(tmp_path, "w-0", "w-1")
    result = necessity_preflight(tasks, corpus_dir=tmp_path / "corpus", repeats=2)
    assert result.unnecessary_pass_rate == 1.0 > UNNECESSARY_PASS_FLOOR
    assert result.necessary_pass_rate == 0.0 < NECESSARY_PASS_CEILING
    assert result.thresholds_cleared is True
    assert result.verdict == VERDICT_UNVERIFIED
    assert result.verified is False and result.mode == "dry_run"
    assert "NOT VERIFICATION" in result.note


def test_preflight_refuses_an_empty_half(tmp_path: Path) -> None:
    _, tasks = _twin_corpus(tmp_path, "w-0")
    necessary_only = [t for t in tasks if t.variant == VARIANT_NECESSARY]
    with pytest.raises(ValueError, match="no tasks in this half"):
        necessity_preflight(necessary_only, corpus_dir=tmp_path / "corpus")


def test_twin_tasks_is_order_stable(tmp_path: Path) -> None:
    _, tasks = _twin_corpus(tmp_path, "w-0", "w-1")
    assert [(t.work_id, t.variant) for t in tasks] == [
        ("w-0", VARIANT_NECESSARY),
        ("w-0", VARIANT_UNNECESSARY),
        ("w-1", VARIANT_NECESSARY),
        ("w-1", VARIANT_UNNECESSARY),
    ]
    _, again = load_twin_corpus(tmp_path / "corpus")
    assert [task_fingerprint(t) for t in tasks] == [task_fingerprint(t) for t in again]


def test_twin_tasks_of_an_already_twinned_corpus_is_refused(tmp_path: Path) -> None:
    _, tasks = _twin_corpus(tmp_path, "w-0")
    with pytest.raises(ValueError, match="can only twin"):
        twin_tasks(tasks)


def test_a_dry_run_cannot_exit_as_acceptance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The gate-facing half of "a label is not evidence". The dry run's rates are entailed by the
    # simulated runner and DO clear the thresholds, so ``accepted`` is true — and the process must
    # still not exit 0, because a CI gate reads the exit code, not the ``verified`` field.
    corpus(tmp_path, "w-0", "w-1")
    code = e1_necessity_preflight.main(["--corpus-dir", str(tmp_path / "corpus"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["thresholds_cleared"] is True and payload["verified"] is False
    assert code == EXIT_UNVERIFIED
    assert "UNRUN" in payload["note"]


def test_paid_without_a_model_refuses_before_it_loads_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # ``--model`` defaults to "", and the paid path was never exercised, so an authorized run
    # would have discovered this AT SPEND TIME. The refusal also has to land before the corpus is
    # read: --corpus-dir names a directory that does not exist, and the run must still refuse for
    # the model rather than die on the corpus.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MEMBENCH_AGENT_MODEL", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "stub-token-not-used")
    code = e1_necessity_preflight.main(
        ["--corpus-dir", str(tmp_path / "nonexistent"), "--paid", "--json"]
    )
    assert code == EXIT_REFUSED
    assert "REFUSING to spend" in capsys.readouterr().out


def test_paid_refuses_a_metered_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    code = e1_necessity_preflight.main(
        ["--corpus-dir", str(tmp_path / "nonexistent"), "--paid", "--model", "stub-model"]
    )
    assert code == EXIT_REFUSED
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_a_dry_run_is_never_refused_for_paid_preconditions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The refusals gate SPEND, not the free wiring check: a dry run spawns nothing, so an ambient
    # metered key or a missing token must not turn the default path into an exit 2 (mem-9bh93 —
    # a gate that reads an ambient env var reds the suite in the shell it targets).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    corpus(tmp_path, "w-0")
    assert (
        e1_necessity_preflight.main(["--corpus-dir", str(tmp_path / "corpus")]) == EXIT_UNVERIFIED
    )


def _multi_twin(tmp_path: Path):
    """The two-value task and its twin — the shape every other twin test cannot express."""
    _, tasks = multi_value_corpus(tmp_path)
    (necessary,) = tasks
    return necessary, unnecessary_twin(necessary)


def test_the_multi_value_twin_states_every_current_value_and_no_stale_one(tmp_path: Path) -> None:
    necessary, unnecessary = _multi_twin(tmp_path)
    # The fixture really is the multi-value case, and its authored order really does differ from
    # the canonical one — without both, the assertions below would hold whether the construction
    # orders the block or not.
    assert len(necessary.current_opaque_values) == 2
    assert list(necessary.current_opaque_values) != sorted(necessary.current_opaque_values)

    for value in necessary.current_opaque_values:
        assert not states_value(necessary.goal_step.user_request, value)
        assert states_value(unnecessary.goal_step.user_request, value)
    forbidden = necessary.goal_step.outcome_checks[0].requires_action[0].forbidden_values
    assert len(forbidden) == 2
    for value in forbidden:
        assert not states_value(unnecessary.goal_step.user_request, value)


def test_the_multi_value_context_block_states_no_positional_mapping(tmp_path: Path) -> None:
    # The follow-up this test exists for. The necessary request names its subjects in an order
    # authored independently of ``arg_values`` (the fixture reverses them on purpose), so a block
    # emitted in the action's authored order sits next to that subject list IMPLYING a pairing
    # that is wrong. The block is canonical (sorted) instead, which asserts no mapping at all —
    # and none is needed, since the scorer tests membership of every value, not their order.
    necessary, unnecessary = _multi_twin(tmp_path)
    _, separator, block = unnecessary.goal_step.user_request.partition(
        CONTEXT_SEPARATOR + "Current state:\n"
    )
    assert separator, unnecessary.goal_step.user_request
    assert block.splitlines() == [
        f"- {subject} is {value}"
        for subject, value in _subject_value_pairs(necessary)
    ]

    # The pairing is read off the FACT that carries each value, so it is the authored one. On
    # this fixture that is demonstrably not what zipping the request's subject order against
    # ``arg_values`` would produce -- which is the whole reason the block cannot be built that
    # way, and why an unlabelled list was the first cut.
    subjects = _requested_subjects(necessary)
    positional = [
        f"- {subject} is {value}"
        for subject, value in zip(subjects, necessary.current_opaque_values, strict=True)
    ]
    assert block.splitlines() != positional


def test_the_non_value_text_of_a_multi_value_twin_pair_is_identical(tmp_path: Path) -> None:
    # test_the_non_value_text_of_a_twin_pair_is_identical, at >1 value: the byte-identity
    # property is this bead's whole point and it had only ever been exercised on a corpus where
    # the block has a single line.
    necessary, unnecessary = _multi_twin(tmp_path)
    prefix, separator, block = unnecessary.goal_step.user_request.partition(
        CONTEXT_SEPARATOR + "Current state:\n"
    )
    assert separator, unnecessary.goal_step.user_request
    assert prefix == necessary.goal_step.user_request
    assert all(" is toolreq-" in line for line in block.splitlines())
    for subject, _value in _subject_value_pairs(necessary):
        assert subject in necessary.goal_step.user_request


def test_the_multi_value_twin_is_solvable_with_an_empty_store(tmp_path: Path) -> None:
    # Necessity, measured rather than labelled, on the multi-value shape: the twin must pass at
    # the empty-store floor (both values are in its prompt) and the necessary half must not.
    necessary, unnecessary = _multi_twin(tmp_path)
    result = necessity_preflight(
        [necessary, unnecessary], corpus_dir=tmp_path / "corpus", repeats=2
    )
    assert result.unnecessary_pass_rate == 1.0
    assert result.necessary_pass_rate == 0.0


def test_the_json_payload_cannot_report_an_unrun_preflight_as_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The exit code was guarded; the PAYLOAD was not, and ``--json`` exists to be read. A
    # consumer reading the emitted object must find the dry run's own verdict there, not a
    # bare ``accepted: true`` computed from rates the simulated runner entails.
    corpus(tmp_path, "w-0", "w-1")
    code = e1_necessity_preflight.main(["--corpus-dir", str(tmp_path / "corpus"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_UNVERIFIED
    assert "accepted" not in payload  # the ambiguous field is gone, not merely qualified
    assert payload["verdict"] == VERDICT_UNVERIFIED
    assert payload["exit_code"] == EXIT_UNVERIFIED
    assert payload["verified"] is False
    # ...while the arithmetic it used to be conflated with is still reported, under its own name.
    assert payload["thresholds_cleared"] is True


def test_the_margin_is_named_a_pass_rate_margin(tmp_path: Path) -> None:
    # E1's primary endpoint (the user's standing ruling) is a CALL-rate margin. This field is a
    # PASS-rate margin over an empty store, and sharing the endpoint's name is how a preflight
    # number gets reported as the endpoint.
    _, tasks = _twin_corpus(tmp_path, "w-0")
    result = necessity_preflight(tasks, corpus_dir=tmp_path / "corpus")
    assert not hasattr(result, "discrimination_margin")
    assert result.empty_store_pass_rate_margin == pytest.approx(
        result.unnecessary_pass_rate - result.necessary_pass_rate
    )


def test_an_absent_corpus_is_not_a_rejection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # An infrastructure absence must not arrive on the channel that means "measured and
    # REJECTED". Exit 1 is a scientific verdict about a corpus that was actually run.
    code = e1_necessity_preflight.main(["--corpus-dir", str(tmp_path / "nonexistent"), "--json"])
    assert code == EXIT_NO_CORPUS
    assert EXIT_NO_CORPUS not in (EXIT_ACCEPTED, EXIT_REJECTED, EXIT_REFUSED, EXIT_UNVERIFIED)
    err = capsys.readouterr().err
    assert "NOT a rejection" in err


def test_an_empty_corpus_directory_is_not_a_rejection(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    assert (
        e1_necessity_preflight.main(["--corpus-dir", str(tmp_path / "empty"), "--json"])
        == EXIT_NO_CORPUS
    )


# --------------------------------------------------------------------------- #
# mem-zfm0m item 1: the twin inlines EVERY named subject's value, not just the scored one
# --------------------------------------------------------------------------- #


def _generated_necessary_tasks(seed: int) -> list[tuple[BenchmarkSequence, ToolReqRealAgentTask]]:
    """The real generator's tool-requiring shape (three subjects named per request, ONE scored),
    adapted the way the frozen corpus is."""
    world = EnterpriseWorld(
        world_id=f"world-seed{seed}",
        domain="cuda-engineering",
        org_name="Acme",
        teams=[Team(team_id="t1", name="Kernels")],
        personas=[
            Persona(persona_id="p1", name="Ada Lovelace", role="staff-engineer", team_id="t1"),
            Persona(persona_id="p2", name="Grace Hopper", role="sre", team_id="t1"),
        ],
        channels=[Channel(channel_id="c1", name="kernels", kind="chat")],
        seed=seed,
    )
    project = Project(
        project_id=f"world-seed{seed}-project",
        world_id=f"world-seed{seed}",
        name="Acme initiative",
        goal="Reconcile the launch config.",
    )
    seqs = materialize_world(world, project, n_tasks=3, facts_per_task=3, tool_requiring=True)
    return [(seq, adapt_sequence(seq)) for seq in seqs]


def _authored_required_contents(seq: BenchmarkSequence, task: ToolReqRealAgentTask) -> list[str]:
    """The AUTHORED (pre-opaque) content of every memory the goal requires: ``oracle_memory`` is
    keyed by exactly the required ids, and the sequence's own writes carry the realistic text."""
    writes = {k: v for step in seq.steps for k, v in step.expected_memory_writes.items()}
    return [writes[memory_id] for memory_id in task.oracle_memory]


def _authored_scored_values(seq: BenchmarkSequence) -> set[str]:
    return {
        value
        for step in seq.steps
        for check in step.outcome_checks
        for action in check.requires_action
        if action.tool == "apply_config"
        for value in action.arg_values
    }


@pytest.mark.parametrize("seed", [1, 2, 3, 5, 8])
def test_the_generated_twin_states_the_current_value_of_every_named_subject(seed: int) -> None:
    """mem-zfm0m item 1. The generator names THREE subjects in the goal request ("apply the current
    value of: <p1>, <p2>, <p3>") and scores ONE; the adapter opaquifies only the scored value, so
    the other two subjects' current values live only in ``oracle_memory``. A twin that inlined
    ``current_opaque_values`` alone handed the agent one value and a request naming three: the
    "memory-unnecessary" half still needed memory for two of its subjects, and the contrast was
    not the one it claimed. Every required fact's value is inlined now: the opaque token for the
    scored subject, the realistic value for the rest, and never a stale or distractor value."""
    for seq, necessary in _generated_necessary_tasks(seed):
        scored = _authored_scored_values(seq)
        twin = unnecessary_twin(necessary)
        request = twin.goal_step.user_request
        named = [s for s in _SUBJECTS if s.prompt in necessary.goal_step.user_request]
        assert len(named) == 3, "the generator names every fact's subject in the request"
        contents = _authored_required_contents(seq, necessary)
        for subject in named:
            (content,) = [c for c in contents if c.startswith(f"{subject.prompt} is ")]
            (current,) = [v for v in subject.values if states_value(content, v)]
            if current in scored:
                # The scored subject is stated as its OPAQUE token (the adapter's substitution),
                # never as the guessable authored value.
                assert not states_value(request, current)
            else:
                assert states_value(request, current), (
                    f"{seq.sequence_id}: twin names {subject.prompt!r} but does not state its "
                    f"current value {current!r}"
                )
                assert not states_value(necessary.goal_step.user_request, current)
            for other in subject.values:
                if other != current:
                    assert not states_value(request, other), (
                        f"{seq.sequence_id}: twin states non-current {other!r} for "
                        f"{subject.prompt!r}"
                    )
        for value in necessary.current_opaque_values:
            assert states_value(request, value)
