import hashlib
import json

import pytest

from membench.runner import bd_real_experiment as experiment
from membench.runner.bd_real_experiment import build_manifest, execute, freeze
from membench.runner.resume_cache import digest


def manifest():
    return build_manifest(
        [{"task_id": "tokens"}, {"task_id": "quota"}],
        corpus_sha256="a" * 64,
        model="pinned-model",
        cli_version="2.1.261",
        bd_identity={"path": "/bd", "sha256": "b" * 64, "version": "v1"},
        source="frozen-source",
        timeout_s=300,
        seed=7,
    )


def test_schedule_is_matched_and_reproducible():
    plan = manifest()
    assert plan == manifest()
    assert plan["planned_pairs"] == 8
    assert plan["planned_sessions"] == 16
    assert {(p["task_id"], p["condition"], p["variant"]) for p in plan["schedule"]} == {
        (t, c, v)
        for t in ["tokens", "quota"]
        for c in ["current", "focused"]
        for v in ["unbriefed", "briefed"]
    }


def test_manifest_pins_instruction_delivery_to_enabled_source():
    plan = manifest()
    assert plan["protocol_revision"] == 3
    assert (
        plan["execution_boundary"]
        == "bubblewrap filesystem allowlist and private process namespace"
    )
    assert plan["agent_python"] == "task grader interpreter with candidate src on PYTHONPATH"
    assert plan["setting_sources"] == "user"
    assert (
        plan["instruction_delivery"]
        == "assembled workspace CLAUDE.md copied to isolated user CLAUDE.md"
    )


def test_freeze_refuses_changed_identity(tmp_path):
    plan = manifest()
    freeze(tmp_path, plan)
    freeze(tmp_path, plan)
    with pytest.raises(ValueError, match="identity"):
        freeze(tmp_path, {**plan, "model": "other"})


def test_completed_pairs_are_not_repurchased(tmp_path):
    plan = manifest()
    freeze(tmp_path, plan)
    calls = []

    def runner(task, **kwargs):
        calls.append(task["task_id"])
        assert (kwargs["out"].parent / "started.json").exists()
        return persist_fake_pair(kwargs["out"])

    args = {
        "tasks": [{"task_id": "tokens"}, {"task_id": "quota"}],
        "corpus_dir": tmp_path,
        "max_pairs": 2,
        "pair_runner": runner,
        "identity_check": lambda: None,
    }
    assert execute(tmp_path, plan, **args)["new_pairs"] == 2
    assert execute(tmp_path, plan, **{**args, "max_pairs": 6})["new_pairs"] == 6
    assert execute(tmp_path, plan, **args)["new_pairs"] == 0
    assert len(calls) == 8


def test_started_failure_preserves_evidence_and_refuses_retry(tmp_path):
    plan = manifest()
    freeze(tmp_path, plan)

    def runner(task, **kwargs):
        kwargs["out"].mkdir()
        (kwargs["out"] / "partial.json").write_text("{}")
        raise RuntimeError("interrupted")

    args = {
        "tasks": [{"task_id": "tokens"}, {"task_id": "quota"}],
        "corpus_dir": tmp_path,
        "max_pairs": 1,
        "pair_runner": runner,
        "identity_check": lambda: None,
    }
    with pytest.raises(RuntimeError, match="interrupted"):
        execute(tmp_path, plan, **args)
    assert len(list(tmp_path.rglob("partial.json"))) == 1
    assert len(list(tmp_path.rglob("halt.json"))) == 1
    with pytest.raises(ValueError, match="reconciliation"):
        execute(tmp_path, plan, **args)


def test_identity_revalidated_before_new_pair(tmp_path):
    plan = manifest()
    freeze(tmp_path, plan)

    def check():
        raise ValueError("source changed")

    with pytest.raises(ValueError, match="source changed"):
        execute(
            tmp_path,
            plan,
            tasks=[{"task_id": "tokens"}, {"task_id": "quota"}],
            corpus_dir=tmp_path,
            max_pairs=1,
            pair_runner=lambda **kw: {},
            identity_check=check,
        )
    assert not list(tmp_path.rglob("started.json"))


def test_completed_pair_identity_must_match(tmp_path):
    plan = manifest()
    freeze(tmp_path, plan)
    pair = plan["schedule"][0]
    key = hashlib.sha256(json.dumps(pair, sort_keys=True).encode()).hexdigest()[:16]
    directory = tmp_path / "pairs" / key
    directory.mkdir(parents=True)
    (directory / "cell.json").write_text(json.dumps({"pair": {**pair, "task_id": "wrong"}}))
    with pytest.raises(ValueError, match="identity"):
        execute(
            tmp_path,
            plan,
            tasks=[{"task_id": "tokens"}, {"task_id": "quota"}],
            corpus_dir=tmp_path,
            max_pairs=1,
            pair_runner=lambda **kw: {},
            identity_check=lambda: None,
        )


def test_identity_only_cell_cannot_satisfy_completion(tmp_path):
    plan = manifest()
    freeze(tmp_path, plan)
    pair = plan["schedule"][0]
    key = hashlib.sha256(json.dumps(pair, sort_keys=True).encode()).hexdigest()[:16]
    directory = tmp_path / "pairs" / key
    directory.mkdir(parents=True)
    (directory / "cell.json").write_text(
        json.dumps({"pair": pair, "manifest_digest": digest(plan)})
    )
    with pytest.raises(ValueError, match="evidence"):
        execute(
            tmp_path,
            plan,
            tasks=[{"task_id": "tokens"}, {"task_id": "quota"}],
            corpus_dir=tmp_path,
            max_pairs=1,
            pair_runner=lambda *a, **kw: {},
            identity_check=lambda: None,
        )


def test_unfinished_later_pair_blocks_all_new_spend(tmp_path):
    plan = manifest()
    freeze(tmp_path, plan)
    pair = plan["schedule"][-1]
    key = hashlib.sha256(json.dumps(pair, sort_keys=True).encode()).hexdigest()[:16]
    (tmp_path / "pairs" / key).mkdir(parents=True)
    calls = []
    with pytest.raises(ValueError, match="reconciliation"):
        execute(
            tmp_path,
            plan,
            tasks=[{"task_id": "tokens"}, {"task_id": "quota"}],
            corpus_dir=tmp_path,
            max_pairs=1,
            pair_runner=lambda *a, **kw: calls.append(True),
            identity_check=lambda: None,
        )
    assert calls == []


def persist_fake_pair(out):
    out.mkdir()
    legs = [{"leg": leg, "status": "ok"} for leg in range(2)]
    pair = json.loads((out.parent / "started.json").read_text())["pair"]
    result = {**pair, "legs": legs, "task_check": {"passed": False}}
    (out / "result.json").write_text(json.dumps(result))
    (out / "task_check.json").write_text(json.dumps(result["task_check"]))
    (out / "goal-candidate.tar").write_bytes(b"fixture archive")
    for leg in range(2):
        path = out / f"leg-{leg}"
        path.mkdir()
        (path / "result.json").write_text(json.dumps(legs[leg]))
        for name in ["raw.stream.jsonl", "receipts.json", "argv.json", "process.json"]:
            (path / name).write_text("[]")
    return result


@pytest.fixture
def cli_environment(tmp_path, monkeypatch):
    from membench.runner import bd_experiment, bd_real_corpus, bd_real_pair, headless_agent

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "manifest.json").write_text("{}")
    monkeypatch.setattr(bd_real_corpus, "load_corpus", lambda path: [{"task_id": "tokens"}])
    monkeypatch.setattr(headless_agent, "resolve_cli_version", lambda: "2.1.261")
    monkeypatch.setattr(
        bd_experiment,
        "resolve_bd_identity",
        lambda: {"path": "/bd", "sha256": "b" * 64, "version": "v1"},
    )
    monkeypatch.setattr(bd_experiment, "source_fingerprint", lambda: "source")
    monkeypatch.setattr(
        bd_real_pair, "run_real_pair", lambda task, **kw: persist_fake_pair(kw["out"])
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-subscription-token")
    return [
        "--corpus",
        str(corpus),
        "--out",
        str(tmp_path / "run"),
        "--model",
        "pinned-model",
        "--expect-cli-version",
        "2.1.261",
    ]


def test_cli_plan_has_no_agent_execution(cli_environment, tmp_path):
    assert experiment.main(cli_environment) == 0
    assert not list((tmp_path / "run").rglob("started.json"))
    assert (tmp_path / "run/harness-source.zip").is_file()


def test_cli_fire_is_bounded_and_resumes(cli_environment, tmp_path):
    assert experiment.main([*cli_environment, "--fire", "--max-pairs", "1"]) == 0
    assert len(list((tmp_path / "run").rglob("cell.json"))) == 1
    assert experiment.main([*cli_environment, "--fire", "--max-pairs", "3"]) == 0
    assert len(list((tmp_path / "run").rglob("cell.json"))) == 4


def test_cli_rejects_metered_key_before_execution(cli_environment, monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with pytest.raises(ValueError, match="subscription"):
        experiment.main([*cli_environment, "--fire"])
    assert not (tmp_path / "run").exists()


def test_cli_rejects_damaged_archive_before_execution(cli_environment, tmp_path):
    experiment.main(cli_environment)
    (tmp_path / "run/harness-source.zip").write_bytes(b"damaged")
    with pytest.raises(ValueError, match="archive evidence"):
        experiment.main([*cli_environment, "--fire"])
    assert not list((tmp_path / "run").rglob("started.json"))


def test_resume_rejects_mutated_raw_leg(cli_environment, tmp_path):
    experiment.main([*cli_environment, "--fire"])
    raw = next((tmp_path / "run").rglob("raw.stream.jsonl"))
    raw.write_text("modified")
    with pytest.raises(ValueError, match="evidence changed"):
        experiment.main([*cli_environment, "--fire"])


def test_completed_run_requires_two_persisted_legs(tmp_path):
    plan = manifest()
    freeze(tmp_path, plan)
    with pytest.raises(ValueError, match="evidence"):
        execute(
            tmp_path,
            plan,
            tasks=[{"task_id": "tokens"}, {"task_id": "quota"}],
            corpus_dir=tmp_path,
            max_pairs=1,
            pair_runner=lambda *a, **kw: {},
            identity_check=lambda: None,
        )
    assert not list(tmp_path.rglob("cell.json"))
    assert len(list(tmp_path.rglob("halt.json"))) == 1


def test_returned_task_identity_cannot_be_misattributed(tmp_path):
    plan = manifest()
    freeze(tmp_path, plan)

    def runner(task, **kw):
        result = persist_fake_pair(kw["out"])
        wrong = {**result, "task_id": "wrong"}
        (kw["out"] / "result.json").write_text(json.dumps(wrong))
        return wrong

    with pytest.raises(ValueError, match="identity"):
        execute(
            tmp_path,
            plan,
            tasks=[{"task_id": "tokens"}, {"task_id": "quota"}],
            corpus_dir=tmp_path,
            max_pairs=1,
            pair_runner=runner,
            identity_check=lambda: None,
        )


def test_source_archive_must_contain_the_current_sources(cli_environment, tmp_path):
    import zipfile

    experiment.main(cli_environment)
    archive = tmp_path / "run/harness-source.zip"
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr("membench/fake.py", "wrong source")
    (tmp_path / "run/harness-source-sha256.json").write_text(
        json.dumps({"archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()})
    )
    with pytest.raises(ValueError, match="source contents"):
        experiment.main([*cli_environment, "--fire"])
