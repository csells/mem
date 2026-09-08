"""Offline evidence packaging and independent receipt-output oracle; never runs candidates."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

AUDIT = Path(__file__).resolve().parent
COHORT = AUDIT.parents[1]
CORPUS = COHORT / "frozen-source/memory-bench/fixtures/memory-policy-fork-corpus"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text())

def exact(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(exact(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(exact(a, b) for a, b in zip(left, right))
    return left == right

def expected_response(request, world, stage):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command not in {"count", "summary", "accepted"}:
        return {"error": "unknown_command"}
    protocol = request.get("protocol", "1" if stage < 3 else "2")
    pair_identity = (world == "webhooks/account-first") == (protocol == "1")
    receipts = request["receipts"]
    groups = {}
    for i, item in enumerate(receipts):
        identity = (item["account_id"], item["delivery_id"]) if pair_identity else item["delivery_id"]
        groups.setdefault(identity, []).append(i)
    selected = []
    for indexes in groups.values():
        times = {i: datetime.fromisoformat(receipts[i]["occurred_at"].replace("Z", "+00:00")).astimezone(timezone.utc) for i in indexes}
        target = (min if protocol == "1" else max)(times.values())
        winner = min((i for i in indexes if times[i] == target), key=lambda i: receipts[i]["record_id"])
        selected.append(winner)
    result = {"protocol": protocol, "accepted_count": len(selected), "duplicate_count": len(receipts)-len(selected)}
    if command == "accepted":
        result["receipts"] = [receipts[i] for i in sorted(selected)]
    return result

def oracle_cases(world, stage):
    file = CORPUS / world / "graders" / f"stage-{stage}.json"
    cases = read(file)
    for case in cases:
        if "artifact_json_path" in case:
            request = case["expected"]["request"]
            independent = {"request": request, "response": expected_response(request, world, stage)}
        else:
            independent = expected_response(case["stdin"], world, stage)
        if not exact(independent, case["expected"]):
            raise AssertionError((str(file), case["name"], independent, case["expected"]))
    return file, cases

def grade_saved(folder, result):
    file, cases = oracle_cases(result["corpus_family"], result["stage"])
    saved = read(folder / "artifact-grade.json")
    assert len(cases) == len(saved["cases"])
    observations = []
    for case, got in zip(cases, saved["cases"]):
        assert case["name"] == got["name"]
        try:
            body = json.loads(got["stdout"])
            passes = got.get("exit") == 0 and exact(body, case["expected"])
        except (KeyError, TypeError, ValueError):
            passes = False
        observations.append({"name": case["name"], "independently_passed": passes, "recorded_passed": got["passed"], "classification_agrees": passes == got["passed"]})
    return {"method": "Reparse saved per-case stdout only; independently derive fixture responses from supplied protocol rules. No candidate execution.", "oracle_path":str(file.relative_to(COHORT)), "oracle_sha256":sha(file), "frozen_expected_cases_independently_match":True, "observations":observations, "classification_disagreements":[x for x in observations if not x["classification_agrees"]], "independently_correct":sum(x["independently_passed"] for x in observations), "total":len(cases)}

def write_slot(slot, findings):
    lifecycle, stage = slot.rsplit("-", 1)
    folder = COHORT / "cases" / lifecycle / ("stage-" + stage)
    result = read(folder / "result.json")
    assert result["slot"] == slot and result["family"] == "webhooks" and 3 <= int(stage) <= 6
    reviewed = ["result.json", "task.json", "tasks-before.json", "tasks-after.json", "memory-before.json", "memory-after.json", "tool-calls.json", "stream.jsonl", "raw-receipts.json", "artifact-grade.json", "prompt.txt", "launch.json", "process.json"]
    evidence = [folder/name for name in reviewed if (folder/name).is_file()]
    for rel in ["workspace-before", "workspace-after"]:
        evidence.extend(p for p in (folder/rel).rglob('*') if p.is_file() and not p.is_symlink() and (p.suffix in {'.py','.md','.json'}))
    evidence.extend((folder/'host-evidence').rglob('rollout-*.jsonl'))
    before = {x['id']:x for x in read(folder/'tasks-before.json')}
    after = {x['id']:x for x in read(folder/'tasks-after.json')}
    history_changes = [k for k in before if k != result['task_id'] and before[k] != after.get(k)]
    report = {"slot":slot, "review":"Manual semantic judgments plus independent offline recheck of saved output JSON", "metadata":{k:result.get(k) for k in ['profile_id','host','arm','stage','corpus_family','catalog_mode','model_requested','models_observed','session_id','host_success','infrastructure_fault','errors','artifact_passed','artifact_correct','artifact_total','task_closed']}, "record_bodies_before":read(folder/'memory-before.json'), "record_bodies_after":read(folder/'memory-after.json'), "older_issue_objects_changed":history_changes, "findings":findings, "saved_output_oracle_recheck":grade_saved(folder,result), "evidence_sha256":{str(p.relative_to(COHORT)):sha(p) for p in evidence}}
    with (AUDIT/(slot+'.json')).open('x') as out:
        json.dump(report,out,indent=2,ensure_ascii=False)
    return report

if __name__ == '__main__':
    evidence = []
    for world in ['webhooks/global-first','webhooks/account-first']:
        for stage in range(3,7):
            file,cases=oracle_cases(world,stage)
            evidence.append({'world':world,'stage':stage,'cases':len(cases),'oracle_sha256':sha(file),'all_expected_match_independent_rules':True})
    with (AUDIT/'independent-frozen-oracle-validation.json').open('x') as out:
        json.dump({'method':'Independent direct implementation of approved grouping/time/tie/order contract; no candidate executions','cases':evidence,'total':sum(x['cases'] for x in evidence)},out,indent=2)
    print('Independent frozen oracle cases checked:',sum(x['cases'] for x in evidence))
