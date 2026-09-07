plan_cents = 19999
completed_years = 3

# New policy calculation
credit_cents = min(plan_cents * 15 // 100, 3600)
print(f"Plan cents: {plan_cents}")
print(f"Credit cents: {credit_cents}")