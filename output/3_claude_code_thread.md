# Submission 3 — Claude Code Execution Thread (including wrong turns)

---

## Attempt 1 — Initial run

**Prompt given:** [see Submission 2]

**Output:** generate_data.py and reconcile.py created.

**Wrong turn #1:** First version of reconcile.py used a simple dict comprehension to index settlements:
```python
march_setts = {s["transaction_id"]: s for s in settlements if ...}
```
This silently drops duplicates — the second settlement for TXN-0012 was overwritten by the first.
Gap 3 (duplicate detection) produced 0 results.

**Fix:** Switched to defaultdict(list) to collect all rows per transaction_id, then check `len(rows) > 1`.

---

## Attempt 2 — Data generation bug

**Wrong turn #2:** In generate_data.py, the clean transaction loop ran `for i in range(1, 46)` but
also added GAP 2 transactions (TXN-0047 to TXN-0052) inside the same loop range. This caused
TXN-0046 (the next-month gap transaction) to be overwritten in the settlement building loop.

**Error:** `run_reconciliation()` returned 0 next-month gaps despite TXN-0046 existing in the CSV.

**Debug:** Added `print(all_setts.get("TXN-0046"))` — returned `None`. Traced it to the settlement
loop using `transactions[:45]` which skipped TXN-0046. 

**Fix:** Separated the clean settlement loop from gap-specific settlement rows. Added explicit
`make_settlement("TXN-0046", ...)` call with `custom_date="2025-04-01"` after the loop.

---

## Attempt 3 — Test failures

**Run:** `python -m pytest tests/ -v`

**Wrong turn #3:** test_gap2_cumulative_delta failed:
```
AssertionError: assert abs(0.030000000000000027 - 0.03) < 1e-09
```
Python float addition of six 0.005 values does not exactly equal 0.03 in IEEE 754.

**Fix:** Changed the assertion tolerance from `1e-9` to `1e-6`, or used `round(..., 6)` before comparison.
Settled on: `assert abs(report["summary"]["rounding_total_delta"] - 0.03) < 1e-9` and stored the
sum as `round(..., 4)` in the engine to avoid the float drift.

**Run after fix:** All 21 tests pass.

---

## Attempt 4 — Dashboard layout

**Wrong turn #4:** First HTML version used `grid-template-columns: repeat(4, 1fr)` for the metric
cards but didn't set `min-width: 0` on children. On narrow viewports the cards overflowed the
container because grid items default to `min-width: auto`.

**Fix:** Changed to `grid-template-columns: repeat(4, minmax(0, 1fr))`.

**Wrong turn #5:** Chart.js tooltip showed raw floats: `$0.030000000000000027` for the rounding 
delta in the donut chart.

**Fix:** Added `.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})` in
the tooltip callback.

---

## Final state

All scripts execute cleanly:
```
$ python src/generate_data.py
Wrote 53 transactions
Wrote 53 settlements

$ python src/reconcile.py
{... clean JSON with all 4 gaps detected ...}

$ python -m pytest tests/ -v
21 passed in 0.09s
```
