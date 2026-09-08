"""Read retained Codex model-facing outputs, including nested serialized exec results."""
import json
from pathlib import Path

def fragments(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from fragments(item)
    elif isinstance(value, list):
        for item in value:
            yield from fragments(item)
    elif isinstance(value, str):
        yield value
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            return
        if decoded != value:
            yield from fragments(decoded)

def delivered(folder, target):
    matches = []
    for file in (folder/'host-evidence').rglob('rollout-*.jsonl'):
        for lineno,line in enumerate(file.read_text().splitlines(),1):
            row=json.loads(line)
            payload=row.get('payload',{})
            if payload.get('type') in {'custom_tool_call_output','function_call_output'}:
                if any(target.strip() in text for text in fragments(payload.get('output'))):
                    matches.append({'path':str(file),'line':lineno,'call_id':payload.get('call_id')})
    return matches
