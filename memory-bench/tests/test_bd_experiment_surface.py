"""Treatment choices reach both sessions without changing native-memory settings."""

import pytest

from membench.runner import e1_grid
from membench.runner.tool_surface import MemoryToolSurface
from tests.toolreq_helpers import corpus_one


@pytest.mark.parametrize(
    "context,mode", [(False, "observe"), (True, "observe"), (True, "redirect")]
)
def test_comparison_treatment_reaches_both_legs(tmp_path, monkeypatch, context, mode):
    _, tasks = corpus_one(tmp_path)
    seen = []
    hooks = []
    install = e1_grid.install_native_memory_hook

    def provision(root, **kwargs):
        return MemoryToolSurface(
            store_dir=root / "store",
            bin_dir=root / "bin",
            bd_binary="/usr/bin/bd",
            config_dir=root / "config",
            bd_context={"CLAUDE.md": "Use bd memory."},
        )

    def hook(config, *, mode):
        hooks.append(mode)
        return install(config, mode=mode)

    def run(task, step, *, store, **kwargs):
        seen.append((store.bd_context, (store.sandbox / "CLAUDE.md").exists(), store.pinned_off))
        return e1_grid._LegOutcome(status="ok")

    monkeypatch.setattr(e1_grid, "provision_memory_tool", provision)
    monkeypatch.setattr(e1_grid, "install_native_memory_hook", hook)
    monkeypatch.setattr(e1_grid, "_run_leg", run)
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model="test-model",
        dry_run=True,
        bd_context=context,
        native_memory_hook_mode=mode,
    )
    assert seen == [(context, context, False)] * 2
    assert hooks == [mode]
    assert cell.runs == 2


def test_receipts_are_prepared_and_preserved_per_leg(tmp_path, monkeypatch):
    import json

    from membench.runner.bd_receipt_surface import receipt_path

    _, tasks = corpus_one(tmp_path)
    records = []

    def provision(root, **kwargs):
        (root / "bin").mkdir()
        return MemoryToolSurface(
            store_dir=root / "store",
            bin_dir=root / "bin",
            bd_binary="/usr/bin/bd",
            config_dir=root / "config",
        )

    def run(task, step, *, store, leg, **kwargs):
        path = receipt_path(store.surface, leg)
        assert (store.surface.bin_dir / "bd").exists()
        path.write_text(json.dumps({"instrumentation_error": "test", "leg_id": path.stem}) + "\n")
        return e1_grid._LegOutcome(status="ok")

    monkeypatch.setattr(e1_grid, "provision_memory_tool", provision)
    monkeypatch.setattr(e1_grid, "_run_leg", run)
    e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model="test",
        dry_run=True,
        bd_context=False,
        instrument_bd=True,
        on_leg=records.append,
    )
    assert len(records) == 2
    assert records[0].row()["bd_receipts"][0]["instrumentation_error"] == "test"
    assert records[0].row()["bd_receipt_leg_id"] != records[1].row()["bd_receipt_leg_id"]
