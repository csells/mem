# Stage graders

Run `python3 grade.py --stage N --candidate /absolute/path/to/candidate`.
The candidate directory must contain `cli.py` and its normal runtime files.
The grader invokes the real CLI in subprocesses with JSON stdin, with no imports
from the candidate or reference implementation. It outputs a JSON case report
and exits 0 only if every check passes. Each subprocess has a five-second limit;
normal requests take well under one second.

Stage checks are cumulative, with active-report expectations changed at stage
4. Stage 3's corrected-statement endpoint stays frozen. Stage 6 checks current
reports and both fixed calendar-month endpoints against identical boundary input.

Expected memberships are explicit ID lists. Date arithmetic only constructs
the fixture instants; it does not decide expected membership. Arithmetic sums
and directly specified CSV escaping turn the selected rows into responses.
The independent reference instead shifts timestamps and classifies calendar
date labels. Neither imports the other.

Keep this directory, reference/, and tasks.json outside the coding agent's
starter working directory. Deliver each task prompt when that stage begins;
retain the existing working tree and prior conversation/files across stages.
