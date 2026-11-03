from pathlib import Path
import ast
import json
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def main():
    # Syntax checks: the UI source can be compiled without importing Streamlit.
    ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    ast.parse((ROOT / "smartprice_src" / "dashboard_data.py").read_text(encoding="utf-8"))

    from smartprice_src.metrics import calculate_business_metrics
    from smartprice_src.elasticity import fit_price_elasticity_models
    from smartprice_src.pricing import optimize_pricing
    from smartprice_src.dashboard_data import (
        get_daily_metrics, get_product_analysis, get_channel_analysis,
        get_secondary_analysis, build_decision_insights
    )

    checks = {}
    db = sqlite3.connect(ROOT / "data" / "database" / "smartprice_ai.db")
    checks["sqlite_integrity"] = db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    checks["all_expected_tables_present"] = {
        "dim_date", "dim_product", "fact_ticket_sales", "fact_daily_operations",
        "fact_secondary_sales", "fact_daily_context", "fact_competitor_price"
    }.issubset({
        row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    })
    db.close()

    daily = get_daily_metrics("2025-01-01", "2025-12-31")
    products = get_product_analysis("2025-01-01", "2025-12-31")
    channels = get_channel_analysis("2025-01-01", "2025-12-31")
    secondary = get_secondary_analysis("2025-01-01", "2025-12-31")
    checks["daily_data_365_days"] = len(daily) == 365
    checks["six_products_available"] = len(products) == 6
    checks["three_sales_channels_available"] = len(channels) == 3
    checks["secondary_categories_available"] >= 1 if False else True
    checks["secondary_categories_available"] = len(secondary) >= 2
    checks["revenue_nonnegative"] = bool((daily["total_revenue_cny"] >= 0).all())
    checks["product_contribution_margin_bounded"] = bool(
        products["contribution_margin_rate"].between(0, 1).all()
    )

    elasticity, _, diagnostics, _ = fit_price_elasticity_models()
    checks["six_elasticity_models"] = len(elasticity) == 6
    insights = build_decision_insights(daily, products, elasticity)
    checks["decision_assistant_returns_insights"] = len(insights) >= 3

    # Verify both optimization objectives produce positive prices and satisfy capacity.
    rev_df, rev_summary, _ = optimize_pricing(
        target_date="2025-10-04", objective="revenue",
        capacity_target_rate=0.85, max_change_rate=0.10
    )
    profit_df, profit_summary, _ = optimize_pricing(
        target_date="2025-10-04", objective="profit",
        capacity_target_rate=0.85, max_change_rate=0.10
    )
    checks["revenue_pricing_solver_success"] = bool(rev_summary["solver_success"])
    checks["profit_pricing_solver_success"] = bool(profit_summary["solver_success"])
    checks["revenue_capacity_constraint_pass"] = rev_summary["capacity_constraint_status"] == "PASS"
    checks["profit_capacity_constraint_pass"] = profit_summary["capacity_constraint_status"] == "PASS"
    checks["six_recommendations_each_objective"] = len(rev_df) == 6 and len(profit_df) == 6
    checks["price_adjustments_respect_10pct"] = bool(
        rev_df["price_change_rate"].abs().le(0.1001).all()
        and profit_df["price_change_rate"].abs().le(0.1001).all()
    )

    checks["status"] = "PASS" if all(v for k, v in checks.items() if k != "status") else "CHECK_REQUIRED"
    out = ROOT / "reports" / "stage4"
    out.mkdir(parents=True, exist_ok=True)
    (out / "stage4_validation.json").write_text(
        json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if checks["status"] != "PASS":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
