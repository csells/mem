from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from membench.runner.memory_contract_check import PUBLIC_TEST_PATH, PUBLIC_TEST_SOURCE


def policy() -> dict[str, Any]:
    # Deliberately unrelated to either approved experiment configuration.
    return {
        "project": "unapproved-project",
        "cache": {
            "ttl_seconds": 987,
            "max_entries": 42,
            "eviction_policy": "unapproved-policy",
            "namespace": "unapproved-namespace",
            "cache_misses": False,
        },
    }


def component(value: Any, source: Any = "Unapproved source", rationale: Any = "No approval") -> str:
    return (
        f"POLICY = {value!r}\nSOURCE = {source!r}\nRATIONALE = {rationale!r}\n"
        "def create_cache(clock):\n    return None\n"
    )


def run_checker(workspace: Path, modules: dict[str, str]) -> subprocess.CompletedProcess[str]:
    test_file = workspace / PUBLIC_TEST_PATH
    test_file.parent.mkdir(parents=True)
    test_file.write_text(PUBLIC_TEST_SOURCE)
    for name, content in modules.items():
        (workspace / name).write_text(content)
    return subprocess.run(
        [str(Path(sys.executable).resolve()), "-B", "-m", "unittest", "discover", "-s", "tests"],
        cwd=workspace,
        env={"PATH": ""},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_valid_shape_with_wrong_facts_passes_without_certifying_behavior(tmp_path: Path) -> None:
    result = run_checker(tmp_path, {"catalog_cache.py": component(policy())})
    assert result.returncode == 0, result.stderr
    assert "Ran 1 test" in result.stderr
    assert PUBLIC_TEST_PATH == "tests/test_component_contract.py"


def test_flattened_policy_is_rejected(tmp_path: Path) -> None:
    result = run_checker(tmp_path, {"catalog_cache.py": component(policy()["cache"])})
    assert result.returncode != 0
    assert "POLICY keys" in result.stderr


@pytest.mark.parametrize("damage", ["outer_missing", "outer_extra", "inner_missing", "inner_extra"])
def test_missing_and_extra_fields_are_rejected(tmp_path: Path, damage: str) -> None:
    value = policy()
    if damage == "outer_missing":
        del value["project"]
    elif damage == "outer_extra":
        value["version"] = "invented"
    elif damage == "inner_missing":
        del value["cache"]["namespace"]
    else:
        value["cache"]["another_field"] = "invented"
    result = run_checker(tmp_path, {"catalog_cache.py": component(value)})
    assert result.returncode != 0
    assert "keys" in result.stderr


@pytest.mark.parametrize(
    "field,value",
    [
        ("project", 1),
        ("cache", []),
        ("ttl_seconds", True),
        ("ttl_seconds", 9.0),
        ("max_entries", False),
        ("max_entries", "42"),
        ("eviction_policy", None),
        ("namespace", 5),
        ("cache_misses", 1),
    ],
)
def test_exact_types_reject_boolean_integer_and_scalar_coercion(
    tmp_path: Path, field: str, value: Any
) -> None:
    config = policy()
    target = config if field in {"project", "cache"} else config["cache"]
    target[field] = value
    result = run_checker(tmp_path, {"catalog_cache.py": component(config)})
    assert result.returncode != 0
    assert field in result.stderr


@pytest.mark.parametrize("attribute", ["SOURCE", "RATIONALE", "create_cache"])
def test_required_exports_are_checked(tmp_path: Path, attribute: str) -> None:
    source = component(policy()) + f"\n{attribute} = None\n"
    result = run_checker(tmp_path, {"catalog_cache.py": source})
    assert result.returncode != 0
    assert attribute in result.stderr


def test_every_matching_component_is_checked(tmp_path: Path) -> None:
    result = run_checker(
        tmp_path,
        {
            "catalog_cache.py": component(policy()),
            "catalog_detail_cache.py": component(policy()["cache"]),
            "unrelated.py": "raise RuntimeError('must not import unrelated files')\n",
        },
    )
    assert result.returncode != 0
    assert "catalog_detail_cache.py" in result.stderr
    assert "must not import" not in result.stderr


def test_missing_component_fails_instead_of_vacuously_passing(tmp_path: Path) -> None:
    result = run_checker(tmp_path, {})
    assert result.returncode != 0
    assert "No catalog" in result.stderr


def test_standard_discovery_still_runs_existing_tests(tmp_path: Path) -> None:
    source = (
        "import unittest\nclass Existing(unittest.TestCase):\n"
        "    def test_existing(self): self.fail('existing check ran')\n"
    )
    result = run_checker(
        tmp_path,
        {"catalog_cache.py": component(copy.deepcopy(policy())), "tests/test_existing.py": source},
    )
    assert result.returncode != 0
    assert "existing check ran" in result.stderr


def test_component_can_import_project_support_module(tmp_path: Path) -> None:
    source = "from support import VALUE\n" + component(policy()) + "assert VALUE == 7\n"
    result = run_checker(tmp_path, {"catalog_cache.py": source, "support.py": "VALUE = 7\n"})
    assert result.returncode == 0, result.stderr


def test_same_assertion_can_check_target_without_removing_earlier_bad_component(
    tmp_path: Path,
) -> None:
    result = run_checker(
        tmp_path,
        {
            "catalog_cache.py": component(policy()["cache"]),
            "catalog_detail_cache.py": component(policy()),
        },
    )
    assert result.returncode != 0  # Normal discovery checks both retained components.
    namespace: dict[str, Any] = {
        "__name__": "canonical_contract",
        "__file__": str(tmp_path / PUBLIC_TEST_PATH),
    }
    exec(compile(PUBLIC_TEST_SOURCE, namespace["__file__"], "exec"), namespace)
    namespace["ComponentContractTest"]().check_component(tmp_path / "catalog_detail_cache.py")
    with pytest.raises(AssertionError, match="POLICY keys"):
        namespace["ComponentContractTest"]().check_component(tmp_path / "catalog_cache.py")


@pytest.mark.parametrize("attribute", ["POLICY", "SOURCE", "RATIONALE", "create_cache"])
def test_missing_exports_are_rejected(tmp_path: Path, attribute: str) -> None:
    result = run_checker(
        tmp_path, {"catalog_cache.py": component(policy()) + f"\ndel {attribute}\n"}
    )
    assert result.returncode != 0
    assert attribute in result.stderr
