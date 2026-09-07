All 60 selected Claude/Codex sessions have offline cost and native-state evidence. Keep main isolated and normal robustness observations separate. Dollar figures are host-reported list-price accounting, including observed auxiliary model usage; Codex does not report dollars. These are not subscription invoices.

| Host | Phase | Arm | Sessions | Reported USD | Primary USD | Auxiliary USD | Native setting | Useful native capture/read |
|---|---|---|---:|---:|---:|---:|---|---|
| claude | checkpoint | baseline | 6 | 1.0336683 | 1.0279173 | 0.0057510 | disabled_for_isolation | 0 / 0 |
| claude | continuation | baseline | 6 | 1.6569413 | 1.6511673 | 0.0057740 | disabled_for_isolation | 0 / 0 |
| claude | checkpoint | memory | 6 | 1.0415406 | 1.0357716 | 0.0057690 | disabled_for_isolation | 0 / 0 |
| claude | continuation | memory | 6 | 1.6828160 | 1.6770600 | 0.0057560 | disabled_for_isolation | 0 / 0 |
| codex | checkpoint | baseline | 6 | unavailable | unavailable | unavailable | disabled_for_isolation | 0 / 0 |
| codex | continuation | baseline | 6 | unavailable | unavailable | unavailable | disabled_for_isolation | 0 / 0 |
| codex | checkpoint | memory | 6 | unavailable | unavailable | unavailable | disabled_for_isolation | 0 / 0 |
| codex | continuation | memory | 6 | unavailable | unavailable | unavailable | disabled_for_isolation | 0 / 0 |
| claude | normal | memory | 6 | 1.2164945 | 1.2107205 | 0.0057740 | enabled | 0 / 0 |
| codex | normal | memory | 6 | unavailable | unavailable | unavailable | feature_off_default | 0 / 0 |

Claude primary usage is Sonnet 4.6; every selected Claude session also reports auxiliary Haiku 4.5 usage. Its 30-session total is $6.6314607: $6.6026367 Sonnet and $0.0288240 Haiku. Normal alone is $1.2164945. Codex normal reports 820,330 input tokens including 731,008 cached input tokens, 14,149 output tokens and 628 reasoning output tokens; do not add cached tokens to input or reasoning to output without host-specific semantics.

Every Claude native archive is empty. Every Codex archive contains one runtime SQLite file with no generated-memory records or jobs. Native snapshots are kept apart from successful Beads captures and ordinary README/issue retention. The normal native settings differ by host, and absence of useful native output does not establish universal native-memory inability.

Source hashes and per-group values: [complete-cross-phase-cost-native.json](complete-cross-phase-cost-native.json). Earlier isolated reports remain untouched.
