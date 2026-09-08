"""Author-written information-gap demonstration, not an agent adoption experiment.

No CLI agent, memory store, model, or user data is accessed. Both policy worlds
are hypothetical approved requirements, not memories fabricated for a trial.
"""

import hashlib
import itertools
import json
from pathlib import Path


CAP = 2400
SOURCE = "def credit(cents):\n    return min(cents // 10, 2400)\n"


def legacy_single(cents):
    return min(cents // 10, CAP)


def subscription_policy(rows):
    return [min(cents // 10, CAP) for account, subscription, cents in rows]


def account_policy(rows):
    remaining = {}
    output = []
    for account, subscription, cents in rows:
        available = remaining.setdefault(account, CAP)
        amount = min(cents // 10, available)
        output.append(amount)
        remaining[account] -= amount
    return output


def verify():
    prices = [0, 1, 99, 100, 23999, 24000, 24001, 30000]
    initial = [[("account-a", "sub-a", p)] for p in prices]
    initial += [
        [("account-a", "sub-a", a), ("account-b", "sub-b", b)]
        for a, b in itertools.product(prices, repeat=2)
    ]
    for rows in initial:
        assert account_policy(rows) == subscription_policy(rows)
        assert account_policy(rows) == [legacy_single(p) for _, _, p in rows]

    expanded = [
        [("account-a", "sub-a", a), ("account-a", "sub-b", b)]
        for a, b in itertools.product(prices, repeat=2)
    ]
    divergent = [
        rows for rows in expanded
        if account_policy(rows) != subscription_policy(rows)
    ]
    witness = [("account-a", "sub-a", 30000), ("account-a", "sub-b", 30000)]
    assert account_policy(witness) == [2400, 0]
    assert subscription_policy(witness) == [2400, 2400]
    assert divergent

    # A note claiming the wrong scope agrees perfectly with the same wrong code.
    wrong_claim_scope = "subscription"
    wrong_artifact = subscription_policy(witness)
    self_consistency_accepts = (
        wrong_claim_scope == "subscription"
        and wrong_artifact == subscription_policy(witness)
    )
    independent_approved_policy_accepts = wrong_artifact == [2400, 0]
    assert self_consistency_accepts and not independent_approved_policy_accepts
    return {
        "kind": "offline author-written counterexample; no model/adoption result",
        "same_initial_source_sha256_in_both_worlds": hashlib.sha256(SOURCE.encode()).hexdigest(),
        "indistinguishable_initial_cases": len(initial),
        "expanded_cases": len(expanded),
        "expanded_cases_requiring_scope_information": len(divergent),
        "ordinary_followup": "Support accounts with multiple subscriptions in the monthly notice batch.",
        "witness_input": witness,
        "account_cap_output_cents": account_policy(witness),
        "subscription_cap_output_cents": subscription_policy(witness),
        "wrong_note_and_wrong_artifact_agree": self_consistency_accepts,
        "wrong_artifact_passes_approved_account_policy": independent_approved_policy_accepts,
        "source_access_in_future_trial": "Retain original issue approval and all actual code/docs/records; do not delete sources or seed agent memories.",
    }


if __name__ == "__main__":
    result = verify()
    path = Path(__file__).with_name("result.json")
    with path.open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps(result, indent=2))
