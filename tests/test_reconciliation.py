"""
tests/test_reconciliation.py
Verifies the reconciliation engine catches every planted gap correctly.
Run with: python -m pytest tests/ -v
"""

import sys, json, csv, io
sys.path.insert(0, "src")
import pytest
from reconcile import run_reconciliation, load_csv

# ── Fixtures ─────────────────────────────────────────────────────────────────

TXN_PATH  = "data/transactions.csv"
SETT_PATH = "data/settlements.csv"

@pytest.fixture(scope="module")
def report():
    return run_reconciliation(TXN_PATH, SETT_PATH)

# ── GAP 1: Next-month settlement ─────────────────────────────────────────────

def test_gap1_detected(report):
    """TXN-0046 transacted on Mar 31 and must be flagged as next-month settlement."""
    ids = [g["transaction_id"] for g in report["gaps"]["next_month_settlements"]]
    assert "TXN-0046" in ids, "Should detect TXN-0046 as a next-month settlement"

def test_gap1_settlement_date(report):
    """The flagged settlement date should be April 2025."""
    gap = next(g for g in report["gaps"]["next_month_settlements"] if g["transaction_id"] == "TXN-0046")
    assert gap["settlement_date"].startswith("2025-04"), \
        f"Settlement date should be April 2025, got {gap['settlement_date']}"

def test_gap1_amount(report):
    """The flagged amount should be $847.50."""
    gap = next(g for g in report["gaps"]["next_month_settlements"] if g["transaction_id"] == "TXN-0046")
    assert gap["txn_amount"] == 847.50

def test_gap1_missing_from_march_total(report):
    """March settlement total must be lower than transaction total by at least $847.50."""
    assert report["totals"]["net_difference"] > 0, "Net difference should be positive (under-settled)"

# ── GAP 2: Rounding differences ──────────────────────────────────────────────

def test_gap2_count(report):
    """Should detect exactly 6 rounding differences (TXN-0047 to TXN-0052)."""
    assert len(report["gaps"]["rounding_differences"]) == 6

def test_gap2_all_txn_ids(report):
    ids = {g["transaction_id"] for g in report["gaps"]["rounding_differences"]}
    expected = {f"TXN-{i:04d}" for i in range(47, 53)}
    assert ids == expected

def test_gap2_each_diff_is_half_cent(report):
    """Each individual rounding difference should be $0.005."""
    for g in report["gaps"]["rounding_differences"]:
        assert abs(g["difference"] - 0.005) < 1e-9, \
            f"{g['transaction_id']} diff expected 0.005, got {g['difference']}"

def test_gap2_cumulative_delta(report):
    """Six × $0.005 = $0.03 total rounding delta."""
    assert abs(report["summary"]["rounding_total_delta"] - 0.03) < 1e-9

# ── GAP 3: Duplicate settlement ───────────────────────────────────────────────

def test_gap3_detected(report):
    """TXN-0012 should appear in duplicate_settlements."""
    ids = [g["transaction_id"] for g in report["gaps"]["duplicate_settlements"]]
    assert "TXN-0012" in ids

def test_gap3_occurrence_count(report):
    gap = next(g for g in report["gaps"]["duplicate_settlements"] if g["transaction_id"] == "TXN-0012")
    assert gap["occurrence_count"] == 2, "Should have exactly 2 settlement rows"

def test_gap3_two_settlement_ids(report):
    gap = next(g for g in report["gaps"]["duplicate_settlements"] if g["transaction_id"] == "TXN-0012")
    assert len(gap["settlement_ids"]) == 2

def test_gap3_overcharge_equals_one_txn_amount(report):
    """Overcharge should equal the original transaction amount (double-billed once)."""
    gap = next(g for g in report["gaps"]["duplicate_settlements"] if g["transaction_id"] == "TXN-0012")
    assert gap["overcharge"] == gap["expected"]

# ── GAP 4: Orphan refund ──────────────────────────────────────────────────────

def test_gap4_detected(report):
    ids = [g["transaction_id"] for g in report["gaps"]["orphan_refunds"]]
    assert "REF-9001" in ids

def test_gap4_no_settlement(report):
    gap = next(g for g in report["gaps"]["orphan_refunds"] if g["transaction_id"] == "REF-9001")
    assert gap["has_settlement"] is False

def test_gap4_amount_is_negative(report):
    gap = next(g for g in report["gaps"]["orphan_refunds"] if g["transaction_id"] == "REF-9001")
    assert gap["amount"] < 0, "Refund should have a negative amount"

# ── Summary sanity checks ─────────────────────────────────────────────────────

def test_total_gaps_nonzero(report):
    assert report["summary"]["total_gaps_found"] > 0

def test_period(report):
    assert report["period"] == "2025-03"

def test_no_false_positives_in_clean_transactions(report):
    """
    Transactions TXN-0001 to TXN-0045 are clean.
    They should NOT appear in next_month_settlements or orphan_refunds.
    """
    nm_ids    = {g["transaction_id"] for g in report["gaps"]["next_month_settlements"]}
    or_ids    = {g["transaction_id"] for g in report["gaps"]["orphan_refunds"]}
    clean_ids = {f"TXN-{i:04d}" for i in range(1, 46)}
    assert nm_ids.isdisjoint(clean_ids), "Clean txns should not appear in next-month gaps"
    assert or_ids.isdisjoint(clean_ids), "Clean txns should not appear in orphan refunds"

# ── Edge-case unit tests ──────────────────────────────────────────────────────

def make_minimal_csv(txn_rows, sett_rows):
    """Helper: write two in-memory CSVs and return paths."""
    import tempfile, os
    txn_path  = tempfile.mktemp(suffix=".csv")
    sett_path = tempfile.mktemp(suffix=".csv")
    txn_fields  = ["transaction_id","customer_id","amount","currency","timestamp","status"]
    sett_fields = ["settlement_id","transaction_id","settled_amount","currency","settlement_date","batch_id"]
    with open(txn_path,"w",newline="") as f:
        w = csv.DictWriter(f,fieldnames=txn_fields); w.writeheader(); w.writerows(txn_rows)
    with open(sett_path,"w",newline="") as f:
        w = csv.DictWriter(f,fieldnames=sett_fields); w.writeheader(); w.writerows(sett_rows)
    return txn_path, sett_path

def test_edge_empty_datasets():
    """Empty inputs should produce a report with zero gaps."""
    tp, sp = make_minimal_csv([], [])
    r = run_reconciliation(tp, sp)
    assert r["summary"]["total_gaps_found"] == 0

def test_edge_exact_match_no_gaps():
    """A single perfectly-matched pair should produce zero gaps."""
    txns = [{"transaction_id":"TXN-X","customer_id":"C1","amount":"100.00",
              "currency":"USD","timestamp":"2025-03-10 12:00:00","status":"completed"}]
    setts = [{"settlement_id":"S1","transaction_id":"TXN-X","settled_amount":"100.00",
               "currency":"USD","settlement_date":"2025-03-11","batch_id":"B1"}]
    tp, sp = make_minimal_csv(txns, setts)
    r = run_reconciliation(tp, sp)
    assert r["summary"]["total_gaps_found"] == 0

def test_edge_both_gap1_and_gap3_simultaneously():
    """A transaction that settles next month AND is duplicated: both gaps should fire."""
    txns = [{"transaction_id":"TXN-Y","customer_id":"C2","amount":"500.00",
              "currency":"USD","timestamp":"2025-03-31 23:59:00","status":"completed"}]
    setts = [
        {"settlement_id":"S2","transaction_id":"TXN-Y","settled_amount":"500.00",
         "currency":"USD","settlement_date":"2025-04-01","batch_id":"B2"},
        {"settlement_id":"S3","transaction_id":"TXN-Y","settled_amount":"500.00",
         "currency":"USD","settlement_date":"2025-04-01","batch_id":"B2"},
    ]
    tp, sp = make_minimal_csv(txns, setts)
    r = run_reconciliation(tp, sp)
    nm_ids  = [g["transaction_id"] for g in r["gaps"]["next_month_settlements"]]
    dup_ids = [g["transaction_id"] for g in r["gaps"]["duplicate_settlements"]]
    assert "TXN-Y" in nm_ids
    assert "TXN-Y" in dup_ids
