"""
reconcile_v2.py  —  Enhanced Reconciliation Engine
Detects 8 gap types vs the original 4.

NEW in v2:
  GAP 5: Ghost settlements    — bank has a settlement for a txn that doesn't exist on platform
  GAP 6: Late settlements     — settled > 3 business days after transaction (SLA breach)
  GAP 7: Partial settlements  — bank paid less than platform amount by > $1.00
  GAP 8: Velocity anomalies   — same customer makes a transaction >3× their own average

Original 4 (improved detection):
  GAP 1: Next-month settlement
  GAP 2: Rounding differences  (now flags both truncation AND rounding-up)
  GAP 3: Duplicate settlements (now flags triplicate+ too, with full overcharge math)
  GAP 4: Orphan refunds

Assumptions:
  A1. Reconciliation period = calendar month (March 2025).
  A2. Transaction belongs to March by platform timestamp (UTC naive).
  A3. Settlement belongs to March by settlement_date field.
  A4. Business days = Mon–Fri; no holiday calendar (assumption stated).
  A5. Settlement SLA = 3 business days after transaction date.
  A6. Rounding gap: 0 < |diff| < $1.00.
  A7. Partial settlement: bank amount < platform amount by > $1.00 (not a rounding issue).
  A8. Duplicate: same transaction_id appears >1 in settlements regardless of batch or date.
  A9. Velocity anomaly: transaction > 3× customer's own historical average AND > $500.
       (Threshold chosen to avoid flagging low-value customers with natural variance.)
  A10. Ghost settlement: settlement_id exists with no matching transaction_id in platform data.
"""

import csv, json
from datetime import datetime, timedelta
from collections import defaultdict

RECON_MONTH  = "2025-03"
SLA_DAYS     = 3          # A5
ROUNDING_MAX = 1.00       # A6
PARTIAL_MIN  = 1.00       # A7
VELOCITY_MUL = 3.0        # A9 multiplier
VELOCITY_FLOOR = 500.0    # A9 minimum amount to flag


# ── helpers ──────────────────────────────────────────────────────────────────

def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def in_month(date_str, month=RECON_MONTH):
    return str(date_str)[:7] == month

def business_days_between(start_str, end_str):
    """Count Mon–Fri days between two date strings (A4)."""
    start = datetime.strptime(start_str[:10], "%Y-%m-%d")
    end   = datetime.strptime(end_str[:10],   "%Y-%m-%d")
    if end <= start:
        return 0
    days = 0
    cur  = start + timedelta(days=1)
    while cur <= end:
        if cur.weekday() < 5:   # 0=Mon … 4=Fri
            days += 1
        cur += timedelta(days=1)
    return days


# ── main engine ──────────────────────────────────────────────────────────────

def run_reconciliation(txn_path, sett_path):
    transactions = load_csv(txn_path)
    settlements  = load_csv(sett_path)

    # ── indexes ──────────────────────────────────────────────────────────────
    all_txns    = {t["transaction_id"]: t for t in transactions}
    march_txns  = {tid: t for tid, t in all_txns.items()
                   if in_month(t["timestamp"][:7])}

    sett_by_txn = defaultdict(list)          # all settlements keyed by txn_id
    for s in settlements:
        sett_by_txn[s["transaction_id"]].append(s)

    march_sett_primary = {}                  # first settlement per txn, if in March
    all_sett_primary   = {}                  # first settlement per txn, any month
    for tid, rows in sett_by_txn.items():
        all_sett_primary[tid] = rows[0]
        march_rows = [r for r in rows if in_month(r["settlement_date"][:7])]
        if march_rows:
            march_sett_primary[tid] = march_rows[0]

    # customer history for velocity check (A9)
    cust_txns = defaultdict(list)
    for t in transactions:
        amt = float(t["amount"])
        if amt > 0:
            cust_txns[t["customer_id"]].append(amt)

    # ── totals ────────────────────────────────────────────────────────────────
    total_txn_amount  = sum(float(t["amount"]) for t in march_txns.values())
    total_sett_amount = sum(float(s["settled_amount"]) for s in march_sett_primary.values()
                            if s["transaction_id"] in march_txns)

    results = {
        "period":  RECON_MONTH,
        "version": "2.0",
        "totals": {
            "transaction_count":  len(march_txns),
            "transaction_amount": round(total_txn_amount, 2),
            "settlement_count":   len([s for s in march_sett_primary
                                        if s in march_txns]),
            "settlement_amount":  round(total_sett_amount, 2),
            "net_difference":     round(total_txn_amount - total_sett_amount, 2),
        },
        "gaps": {
            "next_month_settlements": [],
            "rounding_differences":   [],
            "duplicate_settlements":  [],
            "orphan_refunds":         [],
            "ghost_settlements":      [],
            "late_settlements":       [],
            "partial_settlements":    [],
            "velocity_anomalies":     [],
        },
        "summary": {}
    }

    g = results["gaps"]

    # ── GAP 1: March txn settled in a different month ─────────────────────────
    for tid, txn in march_txns.items():
        sett = all_sett_primary.get(tid)
        if sett and not in_month(sett["settlement_date"][:7]):
            g["next_month_settlements"].append({
                "transaction_id":  tid,
                "txn_date":        txn["timestamp"][:10],
                "txn_amount":      float(txn["amount"]),
                "settlement_id":   sett["settlement_id"],
                "settlement_date": sett["settlement_date"],
                "settlement_month": sett["settlement_date"][:7],
                "impact":          "Excluded from March settlement total",
            })

    # ── GAP 2: Rounding differences (< $1 but > $0) ───────────────────────────
    for tid, txn in march_txns.items():
        sett = march_sett_primary.get(tid)
        if not sett:
            continue
        diff = round(float(txn["amount"]) - float(sett["settled_amount"]), 6)
        if 0 < abs(diff) < ROUNDING_MAX:
            direction = "truncated" if diff > 0 else "rounded-up"
            g["rounding_differences"].append({
                "transaction_id":  tid,
                "platform_amount": float(txn["amount"]),
                "bank_amount":     float(sett["settled_amount"]),
                "difference":      round(diff, 6),
                "direction":       direction,
                "settlement_id":   sett["settlement_id"],
            })

    # ── GAP 3: Duplicate settlements ──────────────────────────────────────────
    for tid, rows in sett_by_txn.items():
        if len(rows) > 1:
            amounts = [float(r["settled_amount"]) for r in rows]
            expected = amounts[0]
            total    = round(sum(amounts), 2)
            g["duplicate_settlements"].append({
                "transaction_id":   tid,
                "occurrence_count": len(rows),
                "settlement_ids":   [r["settlement_id"] for r in rows],
                "batch_ids":        [r["batch_id"] for r in rows],
                "amounts":          amounts,
                "expected_amount":  expected,
                "total_settled":    total,
                "overcharge":       round(total - expected, 2),
                "severity":         "HIGH" if total - expected > 1000 else "MEDIUM",
            })

    # ── GAP 4: Orphan refunds ─────────────────────────────────────────────────
    for txn in transactions:
        tid = txn["transaction_id"]
        is_refund = tid.startswith("REF-") or float(txn["amount"]) < 0
        if is_refund:
            has_sett  = tid in all_sett_primary
            g["orphan_refunds"].append({
                "transaction_id":  tid,
                "amount":          float(txn["amount"]),
                "txn_date":        txn["timestamp"][:10],
                "customer_id":     txn["customer_id"],
                "has_settlement":  has_sett,
                "issue": "No bank acknowledgment of reversal" if not has_sett
                         else "Refund settled but no original charge found",
            })

    # ── GAP 5: Ghost settlements (bank record, no platform txn) ──────────────
    for tid, sett in all_sett_primary.items():
        if tid not in all_txns:
            g["ghost_settlements"].append({
                "settlement_id":   sett["settlement_id"],
                "transaction_id":  tid,
                "settled_amount":  float(sett["settled_amount"]),
                "settlement_date": sett["settlement_date"],
                "batch_id":        sett["batch_id"],
                "issue":           "Settlement exists in bank file but transaction not found on platform",
                "risk":            "Possible phantom payout or data ingestion failure",
            })

    # ── GAP 6: Late settlements (> SLA_DAYS business days) ───────────────────
    for tid, txn in march_txns.items():
        sett = all_sett_primary.get(tid)
        if not sett:
            continue
        bdays = business_days_between(txn["timestamp"][:10], sett["settlement_date"])
        if bdays > SLA_DAYS:
            g["late_settlements"].append({
                "transaction_id":    tid,
                "txn_date":          txn["timestamp"][:10],
                "settlement_date":   sett["settlement_date"],
                "settlement_id":     sett["settlement_id"],
                "business_days":     bdays,
                "sla_days":          SLA_DAYS,
                "days_over_sla":     bdays - SLA_DAYS,
                "amount":            float(txn["amount"]),
            })

    # ── GAP 7: Partial settlements (bank paid < platform by > $1) ─────────────
    for tid, txn in march_txns.items():
        sett = march_sett_primary.get(tid)
        if not sett:
            continue
        diff = float(txn["amount"]) - float(sett["settled_amount"])
        # Must be > $1 (else it's a rounding gap already caught by GAP 2)
        if diff > PARTIAL_MIN:
            g["partial_settlements"].append({
                "transaction_id":   tid,
                "platform_amount":  float(txn["amount"]),
                "bank_amount":      float(sett["settled_amount"]),
                "shortfall":        round(diff, 2),
                "settlement_id":    sett["settlement_id"],
                "possible_cause":   "Partial capture, fee deduction, or chargeback",
            })

    # ── GAP 8: Velocity anomalies ─────────────────────────────────────────────
    for tid, txn in march_txns.items():
        amt  = float(txn["amount"])
        cid  = txn["customer_id"]
        hist = cust_txns[cid]
        if len(hist) < 2:
            continue        # need history to compute average
        avg_excl = (sum(hist) - amt) / (len(hist) - 1)
        if avg_excl > 0 and amt >= VELOCITY_FLOOR and amt > VELOCITY_MUL * avg_excl:
            g["velocity_anomalies"].append({
                "transaction_id":   tid,
                "customer_id":      cid,
                "txn_amount":       amt,
                "customer_avg":     round(avg_excl, 2),
                "multiplier":       round(amt / avg_excl, 1),
                "txn_date":         txn["timestamp"][:10],
                "flag":             f"{round(amt/avg_excl,1)}× customer average — manual review recommended",
            })

    # ── summary ───────────────────────────────────────────────────────────────
    total_gaps = sum(len(v) for v in g.values())
    results["summary"] = {
        "total_gaps_found":           total_gaps,
        "gap_counts": {k: len(v) for k, v in g.items()},
        "financial_impact": {
            "next_month_missing":    round(sum(x["txn_amount"]  for x in g["next_month_settlements"]), 2),
            "rounding_total_delta":  round(sum(x["difference"]  for x in g["rounding_differences"]),  6),
            "duplicate_overcharge":  round(sum(x["overcharge"]  for x in g["duplicate_settlements"]), 2),
            "partial_shortfall":     round(sum(x["shortfall"]   for x in g["partial_settlements"]),   2),
            "ghost_settlement_risk": round(sum(x["settled_amount"] for x in g["ghost_settlements"]), 2),
        },
        "sla_breach_count": len(g["late_settlements"]),
        "fraud_flag_count":  len(g["velocity_anomalies"]),
    }

    return results


if __name__ == "__main__":
    report = run_reconciliation(
        "/home/claude/reconciliation/data/transactions.csv",
        "/home/claude/reconciliation/data/settlements.csv",
    )
    out = "/home/claude/reconciliation/output/report_v2.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report["summary"], indent=2))
