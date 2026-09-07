# Offline OpenCode and zcode audit checklist

This audit reads completed scored sessions only. It never invokes a model,
changes a record, repairs a capture, retries a slot, or alters earlier evidence.
The two hosts account for 60 frozen slots, including 24 checkpoint slots.
At audit initialization no complete result.json existed for either host.

For each completed session:

- Hash every inspected evidence file and identify host/model, lifecycle, arm,
  stage, completion status, artifact grade, and instruction-delivery evidence.
- Compare actual memory-before and memory-after bodies and inspect captured
  tool receipts. Distinguish no capture, failed capture, faithfully scoped
  capture, information loss, false claims, and unsupported source attribution.
- Inspect the actual task body, issue/comment history, project notes, and calls
  for task-specific lookup reminders authored earlier by an agent. Separate
  instructed reuse from uncued work; do not count harness reads as agent use.
- For each recall, establish where its key became known. A recall after search
  belongs to the search route; a genuinely known reference supports direct use.
  Identify whether search returned a complete body or only a preview.
- Separate relevant retrieval and application from mere calls or command help.
  Track legitimate code/docs/tests/issue sources and do not claim causation.
- At stage 3, compare new records with already-saved agreements. Repeated
  unchanged capture can be duplicate work; new useful scope or findings may be
  justified. Do not impose a zero-write score by assumption.
- At stages 4–6, verify permanent revision, unaffected facts, actual earlier
  content, and current/historical applicability. Preserve failed or missing
  coverage in the planned denominators.

HarborPass decision fields: calendar lead, tenure threshold, autopay condition,
percentage, floor rounding, cap, cents, and release applicability. Northbank
fields: absolute UTC instants, inclusive lower/exclusive upper boundary, full
calendar month versus fixed 05:00 ledger month, and frozen replay/compatibility.
A narrowly scoped useful note need not restate the entire application API.
