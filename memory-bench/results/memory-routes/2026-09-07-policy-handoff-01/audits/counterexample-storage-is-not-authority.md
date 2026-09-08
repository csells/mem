# A successful save and readback of an invented policy

In `claude-sonnet-webhooks-occasions-isolated` stage 2, the agent successfully
searched, saved, and recalled a memory while implementing the wrong agreement.
The full [semantic audit](webhooks-phase1-8w6n9zwg/claude-sonnet-webhooks-occasions-isolated-2.json)
and [retained record](../cases/claude-sonnet-webhooks-occasions-isolated/stage-2/memory-after.json)
preserve the evidence.

| Evidence | What it established |
| --- | --- |
| Available `vendor/protocol-1.md` | Protocol 1 delivery identity was global `delivery_id`, across accounts |
| Existing single-account `count` implementation | Correct count behavior, but insufficient to distinguish global from account-local identity |
| New issue | Add cross-account summary under the existing contract; no approval to change identity |
| Five unsuccessful topic searches | No matching saved policy; no authority for a replacement policy |
| Agent's new record and code | Both used `(account_id, delivery_id)`, contrary to the provider contract |
| Independent artifact checks | 37/51 cases passed; 14 failed |

The note ended its provenance argument with: “plus no prior memory existed on this
topic; this record establishes the contract going forward.” It instructed future
consumers to retain the invented scope unless a new approval overrode it. The
agent had not opened the available provider document during this session.

This was not a failed save, a truncated read, or a missing memory command. The
complete false body was delivered on readback. It was also not evidence that prose
is unsuitable: other agents retained complete agreements in prose. The failure
was treating a plausible inference and an empty memory search as authority.

The occasions procedure already said to confirm scope, version, and evidence;
consult legitimate sources when memory was absent or incomplete; distinguish
approval from inference; and remember that readback verifies storage rather than
truth. Thus the failure cannot be explained solely by an absent instruction.

The harness carried the actual false note forward. Later behavior is reported
in the continuation audit; this stage-2 counterexample does not by itself prove
that a successor inherited or relied on the mistake. It also does not establish
the separate practitioner hypothesis of inherited tool-avoidance memories.

The design implication is to evaluate source support independently of storage
and implementation agreement. A public check that merely compares code with the
memory would accept this self-consistent error. A proposed improvement is a
memory reference that preserves the authoritative approval text and its scope,
with a readable summary clearly distinguished from that source. This experiment
does not validate that proposed interface or prove that an added citation field
would make an unsupported claim trustworthy.
