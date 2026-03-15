# SuiSec Gap Fixes Design

**Date:** 2026-03-15
**Scope:** Fix 4 identified gaps in `main.py` and `SKILL.md`
**Approach:** Minimal targeted fixes (Approach A) — surgical changes, no restructuring
**Status:** Forward-looking implementation plan. No code or SKILL.md changes have been applied yet.

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
After `run_simulation()` returns JSON, scan `balanceChanges` for the entry whose `coinType` is `0x2::sui::SUI` and whose `amount` is most negative. The owner address of that entry is the sender.

The `owner` field in Sui JSON can appear in two forms — both must be handled:
- Plain string: `"owner": "0xABC..."`
- Nested dict: `"owner": {"AddressOwner": "0xABC..."}`

This is consistent with the dual-format handling already present in `audit_balance_changes()`.

If no negative SUI entry exists, abort with an error — the simulation is inconclusive.

**Out of scope:** Sponsored-gas transactions (where a third-party pays gas) may result in the true sender having zero or positive SUI balance change, making auto-detection unreliable. Sponsored transactions are explicitly out of scope for this iteration.

---

## Section 2 — HIJACK Detection (Gap 1)

### New function: `audit_object_changes(json_data, sender_addr)`

Iterates `objectChanges`. For each entry:
- If `type` is `"mutated"` (ownership changing on a mutated object is always unexpected)
- Extract the new owner address (handling both plain string and `{"AddressOwner": ...}` forms)
- If that address is not the sender and not a known Sui system address, flag as HIJACK

**Scope note:** Only `"mutated"` type is checked in this iteration. `"transferred"` type is intentionally excluded — a transfer call legitimately moves objects to a new owner, and without a declared-recipient input from the user there is no way to distinguish a valid transfer from a hijack. This can be added in a future iteration when declared-recipient intent is captured.

**Known Sui system addresses (filtered out):** `0x1`, `0x2`, `0x3`, `0x5`, `0x6`, `0x7`, `0x8`

(`0x1` = Move stdlib, `0x2` = Sui framework, `0x3` = Sui system, `0x5`–`0x8` = system state objects. All may appear as object owners in framework-touching transactions.)

### Output format

Both audit functions contribute to a single report block. The combined output is:

```
=============================================
        🛡️  SUISEC AUDIT REPORT 🛡️
=============================================
Intended Spend :     0.0100 SUI
Actual Loss    :     0.0100 SUI
---------------------------------------------
✅ [RESULT] SAFE TO SIGN.                   ← from audit_balance_changes()
🚨 [HIJACK] Object 0x7ebf... diverted to 0x...deadbeef   ← from audit_object_changes()
=============================================
```

- `audit_object_changes()` appends its lines inside the same report block, after the balance result line
- If zero HIJACKs: no HIJACK lines are added (silent pass within the block)
- If HIJACK detected: line(s) are appended before the closing `=` separator, then exit code `1`
- Both checks always run — a PRICE_MISMATCH does not short-circuit the HIJACK check

### Behavior
- Runs after `audit_balance_changes()` — both checks always complete before any exit
- Any HIJACK → exit code `1`
- Zero HIJACKs → no HIJACK lines in output

---

## Section 3 — `sui client call` Support (Gap 4)

### Why it already works
`run_simulation()` validates only that `args[0] == 'sui'` (correct security boundary). It injects `--dry-run` and `--json` generically. The JSON output of `sui client call --dry-run --json` includes the same `balanceChanges` and `objectChanges` fields consumed by the audit functions.

### Changes required
1. **`main.py`** — Update `Usage:` string: replace `'<ptb_command>'` with `'<sui_command>'`
2. **`SKILL.md`** — Four locations require updating:
   - **Line ~17**: "Automated Audit" intro — add `sui client call` alongside `sui client ptb` as a supported command type
   - **Line ~62**: Step 2 header — change "For `sui client ptb` commands (primary path):" to cover both command types
   - **Lines ~68-77**: The manual path block for `sui client call` — replace with automated path documentation
   - **Line ~127**: "Manual Detection Patterns" section header — remove `sui client call` from the manual grouping

No logic changes to `run_simulation()` or audit functions.

---

## Files Changed

| File | Changes |
|------|---------|
| `main.py` | Fix arg order in `main()`, remove `owner_addr` CLI param, add sender auto-detection, update `audit_balance_changes()` call site to pass auto-detected sender, implement `audit_object_changes()`, update Usage string |
| `SKILL.md` | Update 4 locations: automated audit intro (~line 17), Step 2 header (~line 62), manual path block (~lines 68–77), Manual Detection Patterns header (~line 127) |

---

## Validation

`test_suisec.sh` is the acceptance test suite and requires no changes to the test script itself:
- **Test 1** (safe_buy): must exit 0 — validates price check passes
- **Test 2** (hidden_steal): must exit 1 — validates PRICE_MISMATCH detection
- **Test 3** (profile_theft): must exit 1 — validates HIJACK detection (currently broken due to the stub; this test becoming a true pass is the acceptance criterion for Gap 1)

---

## What Is Not Changing

- `run_simulation()` security model (shell=False, `sui`-only whitelist) — unchanged
- `audit_balance_changes()` logic — only the function signature changes (receives auto-detected `owner_addr` instead of CLI arg)
- `test_suisec.sh` — already uses the correct `<cost> '<command>'` order, no changes needed
- `setup.sh`, `package.json` — unchanged
