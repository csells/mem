"""Offline checkpoint aggregation. Reads frozen/retained evidence; creates new audit files only."""
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
CORPUS = ROOT / "frozen-source/memory-bench/fixtures/memory-unprompted-corpus"

def read(p):
    return json.loads(p.read_text())

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def put(name, value):
    with (OUT / name).open("x") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")

def no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate JSON key")
        out[k] = v
    return out

def strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(strict_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(strict_equal(a,b) for a,b in zip(left,right))
    return left == right

planned = [s for s in read(OUT / "scope.json")["scheduled_slots"] if s["phase"] == "checkpoint"]
assert len(planned) == 24
rows = []
source_hashes = {}
integrity_rows = []
issues = []
for slot in planned:
    path = ROOT / "cases" / slot["lifecycle"] / f"stage-{slot['stage']}"
    result = read(path / "result.json")
    review = read(OUT / f"{slot['slot']}.audit.json")
    assert result["slot"] == slot["slot"] == review["slot"]
    audit_hash_changes = [rel for rel,h in review["source_sha256"].items() if digest(ROOT/rel) != h]
    source_hashes[str((OUT / f"{slot['slot']}.audit.json").relative_to(ROOT))] = digest(OUT / f"{slot['slot']}.audit.json")
    for p in path.rglob("*"):
        if p.is_file():
            source_hashes[str(p.relative_to(ROOT))] = digest(p)
    specfile = CORPUS / slot["family"] / "tasks.json"
    spec = read(specfile)
    task = next(t for t in spec["tasks"] if t["stage"] == slot["stage"])
    delivered = read(path / "task.json")
    expected_body = (spec.get("common_contract", "") + "\n\n" + task["prompt"]).strip()
    before = {t["id"]: t for t in read(path/"tasks-before.json")}
    after = {t["id"]: t for t in read(path/"tasks-after.json")}
    mutations = [tid for tid,t in before.items() if tid not in after or any(t.get(k) != after[tid].get(k) for k in ("description", "title"))]
    new = sorted(set(after) - set(before))
    continuity = []
    if slot["stage"] > 1:
        prev = path.parent / f"stage-{slot['stage']-1}" / "workspace-after"
        curr = path / "workspace-before"
        for p in prev.rglob("*"):
            if p.is_file():
                rel=p.relative_to(prev)
                if not (curr/rel).is_file() or digest(p) != digest(curr/rel):
                    continuity.append(str(rel))
    fixture = CORPUS / slot["family"] / "graders" / f"stage-{slot['stage']}.json"
    expected = read(fixture)
    grade = read(path / "artifact-grade.json")
    mismatches = []
    if len(grade["cases"]) != len(expected):
        mismatches.append("case count")
    for actual, exp in zip(grade["cases"], expected):
        try:
            parsed = json.loads(actual["stdout"], object_pairs_hook=no_duplicates)
            exact = strict_equal(parsed, exp["expected"])
        except (ValueError,TypeError):
            exact = False
        if actual["name"] != exp["name"] or actual["exit"] != 0 or not actual["passed"] or not exact:
            mismatches.append(actual["name"])
    if not (grade["passed"] and grade["correct"] == grade["total"] == len(expected) == result["artifact_total"] == result["artifact_correct"] and result["artifact_passed"]):
        mismatches.append("aggregate disagreement")
    public = CORPUS / slot["family"] / task["public_tests"]
    public_delivery = digest(public) == digest(path / "workspace-before" / task["public_tests"])
    for p in [specfile, fixture, public]:
        source_hashes[str(p.relative_to(ROOT))]=digest(p)
    integrity = {
        "slot":slot["slot"], "frozen_task_title_exact":delivered["title"]==task["title"],
        "frozen_task_body_exact":delivered["description"]==expected_body,
        "current_stage_public_example_exact":public_delivery,
        "existing_issue_body_or_title_changes":mutations,"new_agent_issues":new,
        "issue_comments_after":sum(t.get("comment_count",0) for t in after.values()),
        "previous_artifact_files_changed_before_next_session":continuity,
        "package_changed_paths":result["package_changed_paths"],
        "independent_exact_grade_output_mismatches":mismatches,
        "independently_compared_grade_cases":len(expected),
        "prior_audit_source_hash_changes":audit_hash_changes,
        "infrastructure_fault":result["infrastructure_fault"]}
    integrity_rows.append(integrity)
    good = all(integrity[k] for k in ["frozen_task_title_exact","frozen_task_body_exact","current_stage_public_example_exact"])
    bad = any(integrity[k] for k in ["existing_issue_body_or_title_changes","new_agent_issues","issue_comments_after","previous_artifact_files_changed_before_next_session","package_changed_paths","independent_exact_grade_output_mismatches","prior_audit_source_hash_changes","infrastructure_fault"])
    if not good or bad:
        issues.append(slot["slot"])
    rows.append((result,review))
assert len({r["session_id"] for r,a in rows}) == 24
assert all(read(ROOT/"cases"/r["lifecycle"]/f"stage-{r['stage']}"/f"memory-{when}.json") == {} for r,a in rows for when in ["before","after"])

def aggregate(selected):
    rs=[r for r,a in selected]
    cs=[r["cost_usd"] for r in rs if r["cost_usd"] is not None]
    usage={}
    for r in rs:
        if r["host"]=="claude":
            for model,fields in r["usage"].items():
                totals=usage.setdefault(model, Counter())
                for k in ["inputTokens","outputTokens","cacheReadInputTokens","cacheCreationInputTokens","thinkingTokens","webSearchRequests","costUSD"]:
                    totals[k]+=fields.get(k,0)
        else:
            totals=usage.setdefault("gpt-6-astra",Counter())
            for k in ["input_tokens","cached_input_tokens","cache_write_input_tokens","output_tokens","reasoning_output_tokens"]:
                totals[k]+=r["usage"].get(k,0)
    return {
        "sessions":len(rs),"stage_counts":dict(Counter(r["stage"] for r in rs)),
        "initial_capture_opportunities":sum(r["stage"]==1 for r in rs),
        "initial_keyed_captures":sum(r["stage"]==1 and r["memory_after_count"]>r["memory_before_count"] for r in rs),
        "related_reuse_opportunities":sum(r["stage"]==2 for r in rs),
        "repeated_agreement_controls":sum(r["stage"]==3 for r in rs),
        "control_agent_writes":sum(r["receipt_assessment"]["agent_writes"] for r in rs if r["stage"]==3),
        "sessions_with_native_skill_call":sum(r["native_skill_calls"]>0 for r in rs),
        "sessions_with_skill_file_read":sum(r["skill_file_read_calls"]>0 for r in rs),
        "sessions_with_detailed_memory_procedure_read":sum(a["delivery"]["memory_procedure_opened"] for r,a in selected),
        "agent_memory_reads":sum(r["receipt_assessment"]["agent_reads"] for r in rs),
        "agent_memory_writes":sum(r["receipt_assessment"]["agent_writes"] for r in rs),
        "agent_memory_searches":sum(r["receipt_assessment"]["agent_searches"] for r in rs),
        "agent_memory_recalls":sum(r["receipt_assessment"]["agent_recalls"] for r in rs),
        "administrative_memory_reads_excluded":sum(r["administrative_memory_reads"] for r in rs),
        "agent_prime_calls_excluded_from_memory_retrieval":sum(r["receipt_assessment"]["prime_calls"] for r in rs),
        "artifact_sessions_passed":sum(r["artifact_passed"] for r in rs),
        "artifact_cases_correct":sum(r["artifact_correct"] for r in rs),
        "artifact_cases_total":sum(r["artifact_total"] for r in rs),
        "host_success":sum(r["host_success"] for r in rs),
        "agent_authored_memory_lookup_reminders":sum(a["issue_authored_reminders"]["present"] for r,a in selected),
        "reported_cost_usd":sum(cs) if cs else None,"sessions_with_reported_cost":len(cs),
        "sum_recorded_session_duration_s":sum(r["duration_s"] for r in rs),
        "usage_by_reported_model":usage,
        "slots":[r["slot"] for r in rs]}

summary={
    "schema":"claude-codex-checkpoint-audit.v1", "created_ns":time.time_ns(),
    "cohort":str(ROOT),"scope":"24 Claude/Codex isolated stages1-3 checkpoint sessions only",
    "assessment":"No concrete adapter, task delivery, retained-state, package integrity, or recorded grade validity blocker found in this scope; continue unchanged subject to the other hosts' admission review.",
    "totals":aggregate(rows),
    "host_arm":{f"{host}/{arm}":aggregate([(r,a) for r,a in rows if r["host"]==host and r["arm"]==arm]) for host in ["claude","codex"] for arm in ["baseline","memory"]},
    "host_totals":{host:aggregate([(r,a) for r,a in rows if r["host"]==host]) for host in ["claude","codex"]},
    "interpretation":{
        "keyed_fidelity_provenance_unsupported_prose":"Not assessable: no records were created. Do not label absent records as inaccurate records.",
        "zero_control_writes":"No observed redundant control writes; selectivity is unproven when initial captures are also absent.",
        "alternate_preservation":"Faithful README policy and issue close reasons are retained and sometimes read; distinct from requested keyed capture, not total information loss.",
        "cost":"Claude reported cost includes primary Sonnet and auxiliary Haiku; Codex cost is unavailable, not zero. Usage fields retain host-native units and are not directly pooled.",
        "duration":"Sum of recorded session durations is not elapsed cohort time; hosts ran in parallel.",
        "unobserved":"Stage4 revisions, stage5 current reuse, stage6 compatibility, and normal-mode native memory remain outside this checkpoint audit."}}
put("checkpoint-summary.json",summary)
put("checkpoint-integrity.json",{
    "schema":"claude-codex-checkpoint-integrity.v1","created_ns":time.time_ns(),
    "method":"Offline read and hash verification; independent strict JSON re-comparison of retained grader stdout against frozen expectations; no model, application, or Beads invocations.",
    "selected_sessions":len(rows),"unique_sessions":24,"failures":issues,
    "independently_compared_grade_cases":sum(r["independently_compared_grade_cases"] for r in integrity_rows),
    "rows":integrity_rows,"evidence_sha256":source_hashes})
print(json.dumps({"totals":{k:v for k,v in summary["totals"].items() if k not in ["slots","usage_by_reported_model"]},"groups":{k:{f:v for f,v in g.items() if f in ["reported_cost_usd","sum_recorded_session_duration_s","usage_by_reported_model"]} for k,g in summary["host_arm"].items()},"integrity_failures":issues},indent=2))
