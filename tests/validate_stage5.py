from pathlib import Path
import ast
import json
import os
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    from smartprice_src.dashboard_data import (
        get_daily_metrics, get_product_analysis, get_channel_analysis, get_secondary_analysis
    )
    from smartprice_src.elasticity import fit_price_elasticity_models
    from smartprice_src.ai_decision import (
        explain_monthly_variance, build_monthly_report, build_local_answer,
        answer_management_question, llm_configuration
    )

    checks = {}
    ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    ast.parse((ROOT / "smartprice_src" / "ai_decision.py").read_text(encoding="utf-8"))
    checks["app_and_ai_module_syntax"] = True

    daily = get_daily_metrics("2025-01-01", "2025-12-31")
    products = get_product_analysis("2025-01-01", "2025-12-31")
    channels = get_channel_analysis("2025-01-01", "2025-12-31")
    secondary = get_secondary_analysis("2025-01-01", "2025-12-31")
    elasticity, _, _, _ = fit_price_elasticity_models()

    checks["daily_data_available"] = len(daily) == 365
    checks["product_data_available"] = len(products) == 6
    checks["channel_data_available"] = len(channels) >= 2
    checks["secondary_data_available"] = len(secondary) >= 2

    variance = explain_monthly_variance(daily, "2025-10")
    checks["variance_available"] = variance["available"]
    checks["revenue_decomposition_reconciles"] = abs(variance["revenue_reconciliation_residual"]) < 0.01
    checks["profit_identity_reconciles"] = abs(variance["profit_identity_residual"]) < 0.01
    checks["revenue_components_reconcile"] = abs(
        sum(v["delta"] for v in variance["revenue_components"].values()) - variance["revenue_delta"]
    ) < 0.01
    checks["cost_components_reconcile"] = abs(
        sum(v["delta"] for v in variance["cost_components"].values()) - variance["cost_delta"]
    ) < 0.01

    report = build_monthly_report(
        daily, products, channels, secondary, "2025-10", elasticity
    )
    checks["monthly_report_generated"] = len(report) > 1000
    checks["report_contains_synthetic_data_notice"] = "模拟经营数据" in report
    checks["report_contains_management_recommendations"] = "管理建议" in report

    q1 = build_local_answer("当前经营收入和贡献利润是多少？", daily, products, channels, secondary)
    q2 = build_local_answer("哪个产品贡献利润最高？", daily, products, channels, secondary)
    q3 = build_local_answer("2025年10月收入变化的原因是什么？", daily, products, channels, secondary, "2025-12", elasticity)
    q4 = build_local_answer("线上渠道表现如何？", daily, products, channels, secondary)
    checks["local_kpi_question_answered"] = "综合经营收入" in q1
    checks["local_product_question_answered"] = "贡献利润" in q2
    checks["local_variance_question_answered"] = "客流规模影响" in q3
    checks["local_channel_question_answered"] = "online" in q4 or "ota" in q4 or "onsite" in q4

    # Test graceful local fallback even if external environment variables are absent.
    for key in ["SMARTPRICE_LLM_ENDPOINT", "SMARTPRICE_LLM_API_KEY", "SMARTPRICE_LLM_MODEL"]:
        os.environ.pop(key, None)
    result = answer_management_question(
        "当前经营情况如何？", daily, products, channels, secondary, "2025-12", elasticity
    )
    checks["local_fallback_works"] = result["mode"] == "local_rules" and len(result["answer"]) > 10
    checks["no_external_llm_required"] = llm_configuration()["enabled"] is False

    checks["status"] = "PASS" if all(v for k,v in checks.items() if k != "status") else "CHECK_REQUIRED"
    out = ROOT / "reports" / "stage5"
    out.mkdir(parents=True, exist_ok=True)
    (out / "stage5_validation.json").write_text(
        json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if checks["status"] != "PASS":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
