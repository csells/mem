import json,sys
from receipt_impl import hook_response
print(json.dumps(hook_response(json.load(sys.stdin), leg_id='wrong-consistent-contract')))
