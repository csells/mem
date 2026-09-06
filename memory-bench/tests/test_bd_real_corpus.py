from __future__ import annotations

import hashlib
import json
import subprocess

import pytest

from membench.runner.bd_real_corpus import corpus_identity, load_corpus


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args]).decode().strip()


@pytest.fixture
def corpus(tmp_path):
    repo = tmp_path / "history"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    (repo / "a.py").write_text("one\ntwo\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "a.py").write_text("three\n")
    git(repo, "commit", "-qam", "landing")
    landing = git(repo, "rev-parse", "HEAD")
    root = tmp_path / "memory-bench" / "data" / "corpus"
    root.mkdir(parents=True)

    def artifact(path, content, parent=root):
        target = parent / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return {"path": path, "sha256": hashlib.sha256(content.encode()).hexdigest()}

    task = {
        "task_id": "task",
        "work_id": "work",
        "repo": "history",
        "repo_absolute": str(repo),
        "base_commit": base,
        "landing_commit": landing,
        "source": {
            "git_path": "a.py",
            "start_line": 1,
            "end_line": 2,
            "blob_sha256": hashlib.sha256(b"one\ntwo\n").hexdigest(),
            "git_blob_oid": git(repo, "rev-parse", f"{base}:a.py"),
        },
        "artifacts": {
            key: artifact(f"task/{key}.md", "one\ntwo\n")
            for key in ["source_packet", "establish_prompt", "goal_unbriefed", "goal_briefed"]
        },
        "grader": {
            "withheld_from_agents": True,
            "test_ids": ["tests.test_x::test_x"],
            "modules": [
                {
                    **artifact("grader-assets/task/tests/test_x.py.txt", "assert True"),
                    "target_path": "tests/test_x.py",
                }
            ],
            "check_command": [
                "/usr/bin/python3",
                "-m",
                "pytest",
                "-q",
                "-o",
                "addopts=",
                "-p",
                "no:cacheprovider",
                "tests/test_x.py::test_x",
            ],
        },
        "bundle": artifact(".mem/bundles/task.json", "{}", tmp_path),
    }
    manifest = {
        "schema": "bd-real-memory.v1",
        "tasks": [task],
        "preflight": artifact("preflight/results.json", "{}"),
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root


def edit(root, fn):
    path = root / "manifest.json"
    body = json.loads(path.read_text())
    fn(body)
    path.write_text(json.dumps(body))


def test_load_and_identity(corpus):
    tasks = load_corpus(corpus)
    assert tasks == json.loads((corpus / "manifest.json").read_text())["tasks"]
    identity = corpus_identity(corpus)
    assert len(identity["manifest_sha256"]) == 64
    assert len(identity["artifact_sha256"]) == 7
    assert identity["repo_pins"][0]["base_commit"] == tasks[0]["base_commit"]


@pytest.mark.parametrize("path", ["../escape", "/tmp/escape", "task/../source.md", "bad\x00"])
def test_unsafe_path(corpus, path):
    edit(corpus, lambda body: body["tasks"][0]["artifacts"]["source_packet"].update(path=path))
    with pytest.raises(ValueError):
        load_corpus(corpus)


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b.update(schema="bad"),
        lambda b: b["tasks"].append(b["tasks"][0]),
        lambda b: b["tasks"][0].update(base_commit="bad"),
        lambda b: b["tasks"][0].update(repo_absolute="relative"),
        lambda b: b["tasks"][0]["grader"].update(withheld_from_agents=False),
        lambda b: b["tasks"][0]["grader"].update(check_command="pytest"),
        lambda b: b["tasks"][0]["grader"].update(check_command=["python", "-m", "pytest"]),
        lambda b: b["tasks"][0]["grader"].update(check_command=["/usr/bin/python", "-c", "evil"]),
        lambda b: b["tasks"][0]["source"].update(start_line=0),
        lambda b: b["tasks"][0]["source"].update(blob_sha256="0" * 64),
        lambda b: b["tasks"][0]["artifacts"].pop("goal_briefed"),
        lambda b: b["tasks"][0].update(base_commit=b["tasks"][0]["landing_commit"]),
    ],
)
def test_bad_contract(corpus, change):
    edit(corpus, change)
    with pytest.raises(ValueError):
        load_corpus(corpus)


def test_hash_tamper(corpus):
    (corpus / "task/goal_briefed.md").write_text("changed")
    with pytest.raises(ValueError, match="hash"):
        load_corpus(corpus)


def test_packet_missing_excerpt(corpus):
    packet = corpus / "task/source_packet.md"
    packet.write_text("wrong")
    edit(
        corpus,
        lambda b: b["tasks"][0]["artifacts"]["source_packet"].update(
            sha256=hashlib.sha256(b"wrong").hexdigest()
        ),
    )
    with pytest.raises(ValueError, match="excerpt"):
        load_corpus(corpus)


def test_symlink_escape(corpus, tmp_path):
    outside = tmp_path / "outside"
    outside.write_text("one\ntwo\n")
    packet = corpus / "task/source_packet.md"
    packet.unlink()
    packet.symlink_to(outside)
    with pytest.raises(ValueError):
        load_corpus(corpus)


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b["tasks"][0].update(landing_commit="0" * 40),
        lambda b: b["tasks"][0]["grader"]["check_command"].append("bad\x00"),
        lambda b: b["tasks"][0]["grader"]["modules"][0].update(target_path="../x.py"),
        lambda b: b["tasks"][0]["grader"]["modules"][0].update(target_path="runtime/x.py"),
        lambda b: b["tasks"][0]["grader"]["modules"][0].update(path="task/source_packet.md"),
        lambda b: b["tasks"][0]["source"].update(git_blob_oid="0" * 40),
        lambda b: b["preflight"].update(sha256="0" * 64),
        lambda b: b["tasks"][0]["bundle"].update(sha256="0" * 64),
    ],
)
def test_extra_invalid_boundaries(corpus, change):
    edit(corpus, change)
    with pytest.raises(ValueError):
        load_corpus(corpus)


def test_reverse_ancestry(corpus):
    def reverse(body):
        task = body["tasks"][0]
        task["base_commit"], task["landing_commit"] = task["landing_commit"], task["base_commit"]

    edit(corpus, reverse)
    with pytest.raises(ValueError, match="git validation failed"):
        load_corpus(corpus)


def test_runtime_symlink_cannot_expose_grader(corpus):
    packet = corpus / "task/source_packet.md"
    packet.unlink()
    packet.symlink_to(corpus / "grader-assets/task/tests/test_x.py.txt")
    edit(
        corpus,
        lambda body: body["tasks"][0]["artifacts"]["source_packet"].update(
            sha256=hashlib.sha256(b"assert True").hexdigest()
        ),
    )
    with pytest.raises(ValueError, match="designated"):
        load_corpus(corpus)


@pytest.mark.parametrize(
    "node",
    [
        "/external/test.py::test_x",
        "tests/other.py::test_x",
        "tests/test_x.py",
        "-p",
        "--rootdir=/external",
    ],
)
def test_grader_command_must_match_selected_tests(corpus, node):
    edit(corpus, lambda body: body["tasks"][0]["grader"]["check_command"].__setitem__(-1, node))
    with pytest.raises(ValueError, match="selection"):
        load_corpus(corpus)


def test_grader_rejects_arbitrary_flags(corpus):
    edit(corpus, lambda body: body["tasks"][0]["grader"]["check_command"].insert(3, "-x"))
    with pytest.raises(ValueError, match="selection"):
        load_corpus(corpus)


def test_duplicate_grader_destinations(corpus):
    source = corpus / "grader-assets/task/tests/test_x.py.txt"
    copy = source.with_name("test_y.py.txt")
    copy.write_bytes(source.read_bytes())

    def duplicate(body):
        module = body["tasks"][0]["grader"]["modules"][0]
        body["tasks"][0]["grader"]["modules"].append(
            {**module, "path": "grader-assets/task/tests/test_y.py.txt"}
        )

    edit(corpus, duplicate)
    with pytest.raises(ValueError, match="duplicate"):
        load_corpus(corpus)


def test_dotted_class_selection(corpus):
    def nested(body):
        grader = body["tasks"][0]["grader"]
        grader["test_ids"] = ["tests.test_x.TestClass::test_x"]
        grader["check_command"][-1] = "tests/test_x.py::TestClass::test_x"

    edit(corpus, nested)
    assert load_corpus(corpus)
