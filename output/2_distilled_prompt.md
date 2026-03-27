# Submission 2 — Distilled Prompt

The single prompt fed into the AI coding tool:

---

```
You are a senior payments engineer. Build a Python reconciliation engine for a payments company 
whose books don't balance at month-end.

CONTEXT:
- The platform records transactions instantly when a customer pays.
- The bank batches and settles funds 1–2 days later.
- At month-end, every March transaction should have exactly one matching March settlement.

TASK:
1. Write generate_data.py — generates two CSVs (transactions.csv, settlements.csv) for March 2025 
   with ~50 rows each. Plant EXACTLY these 4 gap types:
     GAP 1: One transaction on March 31 that settles April 1 (next-month timing gap)
     GAP 2: Six transactions with amounts like $X.995 where the bank rounds to $X.99 — 
             the individual difference ($0.005) is invisible but the sum ($0.03) is not
     GAP 3: One transaction (TXN-0012) that appears TWICE in the settlements file (duplicate)
     GAP 4: One refund (REF- prefix, negative amount) that has no settlement row at all

2. Write reconcile.py — loads the CSVs, runs these 4 checks, outputs a JSON report with:
     - totals (transaction count/amount, settlement count/amount, net difference)
     - gaps object with four keys, each an array of affected rows
     - summary object with financial impact of each gap type
   
   State all assumptions explicitly as inline comments (A1, A2, ... A7).

3. Do NOT hardcode the gap IDs — detect them algorithmically.

4. The engine must handle edge cases: empty datasets, perfectly matched pairs, a transaction 
   that triggers multiple gap types simultaneously.

CONSTRAINTS:
- No external libraries beyond csv, json, datetime, collections (stdlib only)
- All amounts in USD
- Period = "2025-03" (calendar month)
- A transaction belongs to March by its platform timestamp; a settlement by its settlement_date
```
