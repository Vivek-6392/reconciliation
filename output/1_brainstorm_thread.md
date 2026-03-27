# Submission 1 — Brainstorming Thread (unedited)

---

**Me:** Okay, a payments company. Books don't balance. They have transaction records and bank settlement records. Need to find why they differ.

First instinct — what even causes reconciliation gaps?

- Timing: platform records instantly, bank settles T+1/T+2. So anything on the last day of the month might settle next month. Classic.
- Rounding: if platform stores $X.995 but bank rounds to $X.99 per transaction, each one is off by $0.005. Tiny per line but if you have thousands... you'd see it only in the sum.
- Duplicate entries: same transaction logged twice somewhere. Could be on the platform side (idempotency failure on retry) or on the bank side (resent settlement file).
- Refunds: a refund on the platform with no bank acknowledgment. Or a bank reversal with no platform record.

That's four gap types. That's actually exactly what the brief says to plant. So let me make the data match that requirement explicitly.

---

**Me:** What should the data look like?

Two CSVs:
- transactions.csv: what the platform recorded (transaction_id, customer_id, amount, currency, timestamp, status)
- settlements.csv: what the bank reported (settlement_id, transaction_id, settled_amount, currency, settlement_date, batch_id)

Normal scenario: for every transaction, there's exactly one settlement row with a matching amount, and settlement_date is within T+2 of the transaction timestamp.

Gap 1 — timing: take a transaction timestamped March 31 late at night. Make its settlement_date = April 1. When we reconcile "March", this transaction exists in our records but its settlement is absent.

Gap 2 — rounding: create transactions with amounts like $199.995. Platform stores this. Bank rounds to $199.99. Each row is off by $0.005. Six of these = $0.03 total difference. The killer: looking at any one row you'd barely notice it. Only when you sum the column does it appear.

Gap 3 — duplicate: take one transaction (say TXN-0012 for $4,239). Give it two settlement rows with the same amount. Bank has sent the settlement twice. The platform books the full amount once. But when you total settlements, it appears twice.

Gap 4 — orphan refund: create a refund transaction (REF-9001, -$214). Never create a settlement row for it. The bank has no record of issuing the reversal. Could be the refund was approved before the bank confirmed, or the original charge doesn't exist.

---

**Me:** How should reconciliation logic work?

Three main passes:

Pass 1: Date filter. Split everything by period (March 2025). Transactions belong to March by timestamp. Settlements belong to March by settlement_date. Build indexes.

Pass 2: For each transaction, find its settlement.
- If settlement exists but is in a different month → Gap 1
- If settlement exists but amount differs by >0 and <$1 → Gap 2 (rounding)
- If transaction looks like a refund and has no settlement → Gap 4

Pass 3: Check for duplicates.
- Group settlements by transaction_id. Any group with count > 1 → Gap 3.

Output: JSON report with each gap type as a key, list of affected rows, and summary stats.

---

**Me:** What would I get wrong in production?

Timezone issues are the big one. If my timestamps are naive (no tz info), a 23:55 PST transaction is actually next-day UTC. My reconciliation would classify it to the wrong month. Everything needs explicit tz normalization.

Partial captures: some payment processors allow partial settlement. A $500 charge might settle as two $250 entries. My 1:1 match logic would flag both as duplicates.

FX: any cross-currency transaction is a nightmare. Bank settles in USD but the original was in EUR. The conversion rate at settlement time may differ from the rate at transaction time. My engine has no FX logic at all — would generate constant false positives.

---

**Me:** How do I want to present the output?

A dashboard HTML file. Static, no server needed. Shows:
- Summary metrics at top (total transactions, settlements, net difference, at-risk amount)
- Two charts: gap breakdown by financial impact (donut), transactions vs settlements by category (bar)
- Four gap tables — one per gap type — with row-level detail
- Stated assumptions section
- Production limitations section at the bottom

No backend needed. Everything is computed in Python, hardcoded into the HTML, charts rendered by Chart.js.

---

**Me:** What tests do I need?

For each gap type:
- Does the engine detect it? (presence check)
- Are the details correct? (amount, date, IDs match what we planted)
- Does it NOT false-positive on clean data?

Edge cases:
- Empty datasets (should produce zero gaps, not crash)
- Perfectly matched single pair (zero gaps)
- A transaction that is both next-month AND duplicated (both gap types should fire simultaneously)

That's 21 test cases. Enough to be credible.
