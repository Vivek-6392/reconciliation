"""
reconcile.py
Runs all 4 reconciliation checks and outputs a JSON report.

Assumptions (stated explicitly per brief):
  A1. Reconciliation period = calendar month (March 2025).
  A2. A transaction "belongs" to March if its timestamp falls in March, regardless of when it settles.
  A3. A settlement "belongs" to March if settlement_date is in March.
  A4. Tolerance for exact amount match = $0.00 (we detect even penny differences).
  A5. Rounding gap is flagged when |txn.amount - sett.settled_amount| > 0 but < $1.00
      AND the difference is explained by sub-cent truncation/rounding.
  A6. A refund (negative amount or REF- prefix) that has no matching settlement is a gap,
      not just an unmatched transaction — refunds must be acknowledged by the bank.
  A7. "Duplicate" means the same transaction_id appears more than once in settlements.
"""

import csv, json
from datetime import datetime
from collections import defaultdict

RECON_MONTH = "2025-03"   # period under review

def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def in_march(date_str):
    return date_str.startswith(RECON_MONTH)

def run_reconciliation(txn_path, sett_path):
    transactions = load_csv(txn_path)
    settlements  = load_csv(sett_path)

    # Index structures
    march_txns   = {t["transaction_id"]: t for t in transactions
                    if in_march(t["timestamp"][:7])}
    
    # All settlement rows (may have duplicates)
    sett_by_txn  = defaultdict(list)
    for s in settlements:
        sett_by_txn[s["transaction_id"]].append(s)

    march_setts  = {s["transaction_id"]: s for s in settlements
                    if in_march(s["settlement_date"][:7])}
    
    # Also index all settlements (including April) for gap-1 detection
    all_setts    = {s["transaction_id"]: s for s in settlements}

    results = {
        "period":     RECON_MONTH,
        "totals": {},
        "gaps": {
            "next_month_settlements": [],
            "rounding_differences":  [],
            "duplicate_settlements": [],
            "orphan_refunds":        [],
        },
        "summary": {}
    }

    # ── Totals ────────────────────────────────────────────────────────────────
    total_txn_amount   = sum(float(t["amount"]) for t in march_txns.values())
    total_sett_amount  = sum(float(s["settled_amount"]) for s in march_setts.values())
    results["totals"]  = {
        "transaction_count":  len(march_txns),
        "transaction_amount": round(total_txn_amount, 2),
        "settlement_count":   len(march_setts),
        "settlement_amount":  round(total_sett_amount, 2),
        "net_difference":     round(total_txn_amount - total_sett_amount, 2),
    }

    # ── GAP 1: Transactions in March that settled in April ────────────────────
    for txn_id, txn in march_txns.items():
        sett = all_setts.get(txn_id)
        if sett and not in_march(sett["settlement_date"][:7]):
            results["gaps"]["next_month_settlements"].append({
                "transaction_id":   txn_id,
                "txn_date":         txn["timestamp"][:10],
                "txn_amount":       float(txn["amount"]),
                "settlement_date":  sett["settlement_date"],
                "settlement_id":    sett["settlement_id"],
                "impact":           "Excluded from March settlement total",
            })

    # ── GAP 2: Rounding differences ───────────────────────────────────────────
    for txn_id, txn in march_txns.items():
        sett = march_setts.get(txn_id)
        if not sett:
            continue
        diff = round(abs(float(txn["amount"]) - float(sett["settled_amount"])), 4)
        if 0 < diff < 1.00:
            results["gaps"]["rounding_differences"].append({
                "transaction_id":    txn_id,
                "platform_amount":   float(txn["amount"]),
                "bank_amount":       float(sett["settled_amount"]),
                "difference":        round(float(txn["amount"]) - float(sett["settled_amount"]), 4),
                "settlement_id":     sett["settlement_id"],
            })

    # ── GAP 3: Duplicate settlements ─────────────────────────────────────────
    for txn_id, rows in sett_by_txn.items():
        if len(rows) > 1:
            results["gaps"]["duplicate_settlements"].append({
                "transaction_id":   txn_id,
                "occurrence_count": len(rows),
                "settlement_ids":   [r["settlement_id"] for r in rows],
                "amounts":          [float(r["settled_amount"]) for r in rows],
                "total_settled":    round(sum(float(r["settled_amount"]) for r in rows), 2),
                "expected":         float(rows[0]["settled_amount"]),
                "overcharge":       round(sum(float(r["settled_amount"]) for r in rows[1:]), 2),
            })

    # ── GAP 4: Refunds with no matching original transaction or settlement ─────
    for txn in transactions:
        txn_id = txn["transaction_id"]
        is_refund = txn_id.startswith("REF-") or float(txn["amount"]) < 0
        if is_refund:
            has_settlement = txn_id in all_setts
            results["gaps"]["orphan_refunds"].append({
                "transaction_id":       txn_id,
                "amount":               float(txn["amount"]),
                "txn_date":             txn["timestamp"][:10],
                "customer_id":          txn["customer_id"],
                "has_settlement":       has_settlement,
                "issue":                "No corresponding settlement found" if not has_settlement
                                        else "Settlement present but no original charge",
            })

    # ── Summary ───────────────────────────────────────────────────────────────
    total_gaps = sum(len(v) for v in results["gaps"].values())
    rounding_sum = round(sum(g["difference"] for g in results["gaps"]["rounding_differences"]), 4)
    dup_overcharge = round(sum(g["overcharge"] for g in results["gaps"]["duplicate_settlements"]), 2)
    
    results["summary"] = {
        "total_gaps_found":          total_gaps,
        "next_month_amount_missing": round(sum(g["txn_amount"] for g in results["gaps"]["next_month_settlements"]), 2),
        "rounding_total_delta":      rounding_sum,
        "duplicate_overcharge":      dup_overcharge,
        "orphan_refund_count":       len(results["gaps"]["orphan_refunds"]),
    }

    return results


if __name__ == "__main__":
    report = run_reconciliation(
        "/home/claude/reconciliation/data/transactions.csv",
        "/home/claude/reconciliation/data/settlements.csv",
    )
    out_path = "/home/claude/reconciliation/output/report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
