The zcode reconciliation treatment stage-2 record includes a claim that Python's
CSV writer cannot quote carriage returns when configured with LF line endings.
The independent pinned-runtime counterexample disproves that claim on Python
3.14.7. The record and later sessions remain untouched.

Python's [3.14 CSV documentation](https://docs.python.org/3.14/library/csv.html#csv.QUOTE_MINIMAL)
also specifies CR and LF among the characters handled by minimal quoting,
independently of the selected line terminator. Its dialect configuration permits
overriding the default line terminator. Retrieved 2026-09-07.

There was a related historical defect: the primary
[CPython issue](https://github.com/python/cpython/issues/67044) links a fix and
backports to 3.12 and 3.11. That history makes version-dependent advice relevant;
it does not establish what caused this agent's assertion. Do not describe the
defect as universal to Python 3.13, or claim that this run read an old external
memory. We observed creation of a misleading library-avoidance record. Whether
a later agent inherits or acts on it requires the subsequent trace evidence.

This is supplemental source research after the cohort freeze, not information
supplied to any evaluated agent. The practitioner's broader warning about
remembered tool avoidance remains an anecdote; its transcript-volume and adoption
claims remain unverified here.
