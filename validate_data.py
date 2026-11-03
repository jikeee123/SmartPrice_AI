from pathlib import Path
import json
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "database" / "smartprice_ai.db"
REPORT_PATH = ROOT / "reports" / "validation_run.json"

def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"数据库不存在：{DB_PATH}。请先运行 python generate_data.py")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    tables = [
        "dim_date", "dim_product", "fact_daily_context", "fact_daily_operations",
        "fact_ticket_sales", "fact_secondary_sales", "fact_competitor_price"
    ]
    counts = {}
    for table in tables:
        counts[table] = int(pd.read_sql_query(f"SELECT COUNT(*) AS n FROM {table}", conn)["n"].iloc[0])

    fk_check = pd.read_sql_query("PRAGMA foreign_key_check", conn)
    integrity = pd.read_sql_query("PRAGMA integrity_check", conn).iloc[0, 0]

    visitors = pd.read_sql_query("""
        SELECT SUM(s.net_orders * p.visitor_units_per_order) AS reconstructed_visitors
        FROM fact_ticket_sales s
        JOIN dim_product p ON s.product_id = p.product_id
    """, conn).iloc[0, 0]
    actual_visitors = pd.read_sql_query(
        "SELECT SUM(actual_visitors) AS n FROM fact_daily_operations", conn
    ).iloc[0, 0]

    capacity_violations = pd.read_sql_query("""
        SELECT COUNT(*) AS n
        FROM fact_daily_operations
        WHERE actual_visitors > park_capacity
    """, conn).iloc[0, 0]

    ticket_reconciliation = pd.read_sql_query("""
        SELECT MAX(ABS(net_sales_cny - admission_revenue_cny - included_fnb_revenue_cny)) AS max_diff
        FROM fact_ticket_sales
    """, conn).iloc[0, 0]

    secondary_reconciliation = pd.read_sql_query("""
        SELECT MAX(ABS(net_sales_cny - (gross_sales_cny - discount_amount_cny - refund_amount_cny))) AS max_diff
        FROM fact_secondary_sales
    """, conn).iloc[0, 0]

    result = {
        "database_integrity": integrity,
        "foreign_key_violations": int(len(fk_check)),
        "row_counts": counts,
        "visitor_reconciliation_difference": round(float(visitors - actual_visitors), 4),
        "capacity_violations": int(capacity_violations),
        "ticket_revenue_allocation_max_difference": round(float(ticket_reconciliation or 0), 4),
        "secondary_revenue_max_difference": round(float(secondary_reconciliation or 0), 4),
    }
    result["status"] = (
        "PASS" if integrity == "ok" and len(fk_check) == 0
        and abs(result["visitor_reconciliation_difference"]) < 0.01
        and capacity_violations == 0
        and result["ticket_revenue_allocation_max_difference"] < 0.02
        and result["secondary_revenue_max_difference"] < 0.02
        else "CHECK_REQUIRED"
    )

    conn.close()
    REPORT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
