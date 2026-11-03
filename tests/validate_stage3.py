from pathlib import Path
import json
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "stage3"

def main():
    checks = {}
    db = sqlite3.connect(ROOT / "data" / "database" / "smartprice_ai.db")
    checks["sqlite_integrity"] = db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    checks["foreign_keys"] = len(db.execute("PRAGMA foreign_key_check").fetchall()) == 0
    db.close()

    daily = pd.read_csv(REPORT / "daily_metrics.csv")
    monthly = pd.read_csv(REPORT / "monthly_metrics.csv")
    elastic = pd.read_csv(REPORT / "price_elasticity_results.csv")
    forecast = json.loads((REPORT / "visitor_forecast_metrics.json").read_text(encoding="utf-8"))
    pricing = pd.read_csv(REPORT / "pricing_recommendation_demo.csv")
    summary = json.loads((REPORT / "pricing_optimization_summaries.json").read_text(encoding="utf-8"))

    checks["daily_rows_365"] = len(daily) == 365
    checks["monthly_rows_12"] = len(monthly) == 12
    checks["six_elasticity_models"] = len(elastic) == 6
    checks["forecast_has_test_rows"] = forecast["test_rows"] >= 30
    checks["all_recommended_prices_positive"] = bool((pricing["recommended_price_cny"] > 0).all())
    checks["price_change_within_10pct"] = bool((pricing["price_change_rate"].abs() <= 0.1001).all())
    checks["price_recommendations_within_product_bounds"] = bool(
        ((pricing["recommended_price_cny"] >= 0).all())
    )
    checks["forecast_beats_lag7_baseline_wape"] = bool(
        forecast["wape"] < forecast["baseline_lag7_wape"]
    )
    checks["revenue_optimizer_capacity_pass"] = summary["revenue"]["capacity_constraint_status"] == "PASS"
    checks["profit_optimizer_capacity_pass"] = summary["profit"]["capacity_constraint_status"] == "PASS"
    checks["revenue_optimizer_solver_success"] = summary["revenue"]["solver_success"]
    checks["profit_optimizer_solver_success"] = summary["profit"]["solver_success"]

    checks["status"] = "PASS" if all(v for k, v in checks.items() if k != "status") else "CHECK_REQUIRED"
    (REPORT / "stage3_validation.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if checks["status"] != "PASS":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
