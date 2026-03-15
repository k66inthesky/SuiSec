# SuiSec Gap Fixes Design

**Date:** 2026-03-15
**Scope:** Fix 4 identified gaps in `main.py` and `SKILL.md`
**Approach:** Minimal targeted fixes (Approach A) — surgical changes, no restructuring

---

## Gaps Being Fixed

| # | Gap | Location |
|---|-----|----------|
| 1 | HIJACK detection is a stub (`pass`) | `main.py:69-73` |
| 2 | CLI argument signature mismatch vs SKILL.md and test script | `main.py:93-99` |
| 3 | Sender address requires explicit CLI arg instead of auto-detection | `main.py:93-99` |
| 4 | `sui client call` documented as unsupported despite generic pipeline | `main.py`, `SKILL.md` |

---

## Section 1 — CLI Interface (Gaps 2 & 3)

### Current (broken)
```
python3 main.py '<ptb_command>' <intended_cost> <owner_address>
```
- Command is argv[1], cost is argv[2], owner is argv[3]
- Requires the caller to know and pass the sender address
- Contradicts SKILL.md (`<cost> '<command>'`) and test_suisec.sh (same order)

### New
```
python3 main.py <intended_cost> '<full_sui_command>'
```
- Cost is argv[1], command is argv[2]
- No `owner_address` argument — auto-detected from dry-run output

### Sender Auto-Detection
After `run_simulation()` returns JSON, scan `balanceChanges` for the entry whose `coinType` is `0x2::sui::SUI` and whose `amount` is most negative. The `owner.AddressOwner` of that entry is the sender.

If no negative SUI entry exists, abort with an error — the simulation is inconclusive.

---

## Section 2 — HIJACK Detection (Gap 1)

### New function: `audit_object_changes(json_data, sender_addr)`

Iterates `objectChanges`. For each entry:
- If `type` is `"mutated"` or `"transferred"`
- Extract `owner.AddressOwner` (the new owner)
- If that address is not the sender and not a known Sui system address, flag as HIJACK

**Known Sui system addresses (filtered out):** `0x5`, `0x6`, `0x7`, `0x8`

### Output
```
🚨 [HIJACK] Object 0x7ebf... diverted to 0x...deadbeef
```

### Behavior
- Runs after `audit_balance_changes()` — both checks always run so all threats appear in one report
- Any HIJACK → exit code `1`
- Zero HIJACKs → no output from this check (silent pass)

---

## Section 3 — `sui client call` Support (Gap 4)

### Why it already works
`run_simulation()` validates only that `args[0] == 'sui'` (correct security boundary). It injects `--dry-run` and `--json` generically. The JSON output of `sui client call --dry-run --json` includes the same `balanceChanges` and `objectChanges` fields consumed by the audit functions.

### Changes required
1. **`main.py`** — Update `Usage:` string: replace `'<ptb_command>'` with `'<sui_command>'`
2. **`SKILL.md`** — Remove the "manual path" caveat for `sui client call`; document it as a fully supported automated path alongside `sui client ptb`

No logic changes to `run_simulation()` or audit functions.

---

## Files Changed

| File | Changes |
|------|---------|
| `main.py` | Fix arg order, remove `owner_addr` param, add sender auto-detection, implement `audit_object_changes()`, update Usage string |
| `SKILL.md` | Remove `sui client call` limitation note, update example to show both command types supported |

---

## What Is Not Changing

- `run_simulation()` security model (shell=False, `sui`-only whitelist) — unchanged
- `audit_balance_changes()` logic — only the function signature changes (receives auto-detected `owner_addr` instead of CLI arg)
- `test_suisec.sh` — already uses the correct `<cost> '<command>'` order, no changes needed
- `setup.sh`, `package.json` — unchanged
