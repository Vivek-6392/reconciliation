"""
generate_data.py
Generates synthetic payments platform data with 4 planted reconciliation gaps.

Assumptions:
- Currency: USD
- Period: March 2025 (month-end reconciliation)
- Settlement window: T+1 or T+2 business days (bank batch cycle)
- Amounts: $10 – $5,000 range (typical e-commerce)
- Refunds are negative-amount transactions prefixed REF-
- Rounding: Platform stores full precision; bank rounds to 2dp per settlement
"""

import csv
import random
from datetime import datetime, timedelta

random.seed(42)

MARCH_START = datetime(2025, 3, 1)
MARCH_END   = datetime(2025, 3, 31, 23, 59, 59)

def rand_dt(start, end):
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))

def rand_amount(lo=10.0, hi=5000.0):
    return round(random.uniform(lo, hi), 2)

# ── Build clean transactions ────────────────────────────────────────────────
transactions = []
for i in range(1, 46):          # 45 clean transactions
    txn_id  = f"TXN-{i:04d}"
    ts      = rand_dt(MARCH_START, datetime(2025, 3, 30))   # keep away from 31st for clean ones
    amount  = rand_amount()
    transactions.append({
        "transaction_id": txn_id,
        "customer_id":    f"CUST-{random.randint(1000,9999)}",
        "amount":         amount,
        "currency":       "USD",
        "timestamp":      ts.strftime("%Y-%m-%d %H:%M:%S"),
        "status":         "completed",
    })

# ── GAP 1: Transaction on Mar 31 that settles Apr 1 ─────────────────────────
gap1_txn = {
    "transaction_id": "TXN-0046",
    "customer_id":    "CUST-5501",
    "amount":         847.50,
    "currency":       "USD",
    "timestamp":      "2025-03-31 23:14:07",   # last day of month, late at night
    "status":         "completed",
}
transactions.append(gap1_txn)

# ── GAP 4: Refund with NO matching original transaction ──────────────────────
gap4_txn = {
    "transaction_id": "REF-9001",
    "customer_id":    "CUST-7734",
    "amount":         -214.00,
    "currency":       "USD",
    "timestamp":      "2025-03-15 10:22:33",
    "status":         "refunded",
}
transactions.append(gap4_txn)

# ── GAP 2 seed: 6 transactions whose sub-cent fractions accumulate ───────────
# Platform stores 3dp; bank rounds per transaction → sum diverges
rounding_txns = []
rounding_amounts_platform = [199.995, 299.995, 149.995, 399.995, 99.995, 249.995]
for j, amt in enumerate(rounding_amounts_platform, start=47):
    txn = {
        "transaction_id": f"TXN-{j:04d}",
        "customer_id":    f"CUST-{random.randint(1000,9999)}",
        "amount":         amt,
        "currency":       "USD",
        "timestamp":      rand_dt(MARCH_START, datetime(2025, 3, 28)).strftime("%Y-%m-%d %H:%M:%S"),
        "status":         "completed",
    }
    rounding_txns.append(txn)
transactions.extend(rounding_txns)

# Write transactions CSV
txn_fields = ["transaction_id","customer_id","amount","currency","timestamp","status"]
with open("/home/claude/reconciliation/data/transactions.csv","w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=txn_fields)
    w.writeheader()
    w.writerows(transactions)

print(f"Wrote {len(transactions)} transactions")

# ── Build settlements ────────────────────────────────────────────────────────
settlements = []
sett_id = 1

def make_settlement(txn_id, amount, txn_ts_str, offset_days=None, custom_date=None):
    global sett_id
    if custom_date:
        sett_date = custom_date
    else:
        base = datetime.strptime(txn_ts_str, "%Y-%m-%d %H:%M:%S")
        days = offset_days if offset_days else random.choice([1,2])
        sett_date = (base + timedelta(days=days)).strftime("%Y-%m-%d")
    row = {
        "settlement_id":   f"SETT-{sett_id:04d}",
        "transaction_id":  txn_id,
        "settled_amount":  amount,
        "currency":        "USD",
        "settlement_date": sett_date,
        "batch_id":        f"BATCH-{random.randint(100,999)}",
    }
    sett_id += 1
    return row

# Clean settlements for clean transactions
for t in transactions[:45]:
    settlements.append(make_settlement(t["transaction_id"], t["amount"], t["timestamp"]))

# GAP 1 settlement: settles April 1 (NEXT month)
settlements.append(make_settlement("TXN-0046", 847.50, "2025-03-31 23:14:07", custom_date="2025-04-01"))

# GAP 4 refund: NO settlement row at all (that's the gap — omit it)

# GAP 2 rounding: bank rounds each X.995 to X.99 (rounds down at 0.5 boundary edge)
bank_rounded = [199.99, 299.99, 149.99, 399.99, 99.99, 249.99]
for t, br in zip(rounding_txns, bank_rounded):
    settlements.append(make_settlement(t["transaction_id"], br, t["timestamp"]))

# GAP 3 duplicate: TXN-0012 appears TWICE in settlements
dup_target = transactions[11]   # TXN-0012
settlements.append(make_settlement(dup_target["transaction_id"], dup_target["amount"], dup_target["timestamp"]))

# Write settlements CSV
sett_fields = ["settlement_id","transaction_id","settled_amount","currency","settlement_date","batch_id"]
with open("/home/claude/reconciliation/data/settlements.csv","w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=sett_fields)
    w.writeheader()
    w.writerows(settlements)

print(f"Wrote {len(settlements)} settlements")
print("\n=== PLANTED GAPS ===")
print("GAP 1 (Next-month settlement) : TXN-0046 → settled 2025-04-01")
print("GAP 2 (Rounding delta)        : TXN-0047..0052 → sum diff =", 
      round(sum(rounding_amounts_platform) - sum(bank_rounded), 4))
print("GAP 3 (Duplicate settlement)  : TXN-0012 has 2 settlement rows")
print("GAP 4 (Orphan refund)         : REF-9001 has no settlement")
