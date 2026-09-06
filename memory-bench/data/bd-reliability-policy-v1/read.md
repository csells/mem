BD MEMORY COMMAND CONTRACT
For any bd memory lookup in this task, your first memory command must be exactly:

bd memories --json

Inspect the returned JSON values before deciding whether relevant memory exists. This command lists stored keys and full values; a long multiword query is not a substitute. If the JSON is empty, report that observation. If the command fails, inspect the error. If a discovery command returns only a preview, use bd recall with an exact returned key to obtain the full value. Never infer absence from a no-match phrase search. Apply a retrieved claim only after checking its evidence, scope, and relevance to the current task. This contract specifies how to consult memory; it does not itself require an otherwise optional lookup.

