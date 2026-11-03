from pathlib import Path
import json
import pandas as pd
from smartprice_src.metrics import calculate_business_metrics
from smartprice_src.elasticity import fit_price_elasticity_models
from smartprice_src.forecasting import run_forecast_backtest
from smartprice_src.pricing import optimize_pricing

ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports" / "stage3"
MODEL_DIR = ROOT / "models"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

def main():
    print("=== SmartPrice AI | Stage 3 ===")

    metrics = calculate_business_metrics()
    for name in ["daily_metrics", "monthly_metrics", "product_metrics", "secondary_metrics", "channel_metrics"]:
        metrics[name].to_csv(REPORT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")
    (REPORT_DIR / "business_kpi_summary.json").write_text(
        json.dumps(metrics["summary"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Business and financial metrics completed.")

    elasticity, model_objects, diagnostics, _ = fit_price_elasticity_models()
    elasticity.to_csv(REPORT_DIR / "price_elasticity_results.csv", index=False, encoding="utf-8-sig")
    diagnostics.to_csv(REPORT_DIR / "price_elasticity_diagnostics.csv", index=False, encoding="utf-8-sig")
    for product_id, model in model_objects.items():
        (REPORT_DIR / f"elasticity_model_{product_id}.txt").write_text(
            model.summary().as_text(), encoding="utf-8"
        )
    print("Product-level price elasticity regressions completed.")

    model, forecast_metrics, backtest = run_forecast_backtest(
        model_dir=MODEL_DIR, report_dir=REPORT_DIR
    )
    print("Chronological visitor forecast backtest completed.")

    optimization_summaries = {}
    pricing_outputs = {}
    for objective in ["revenue", "profit"]:
        pricing, summary, _ = optimize_pricing(
            target_date="2025-10-04", objective=objective,
            capacity_target_rate=0.85, max_change_rate=0.10
        )
        pricing.to_csv(
            REPORT_DIR / f"pricing_recommendation_{objective}_demo.csv",
            index=False, encoding="utf-8-sig"
        )
        optimization_summaries[objective] = summary
        pricing_outputs[objective] = pricing
    # Keep the revenue-objective file as the primary demo output for compatibility.
    pricing_outputs["revenue"].to_csv(
        REPORT_DIR / "pricing_recommendation_demo.csv", index=False, encoding="utf-8-sig"
    )
    (REPORT_DIR / "pricing_optimization_summary.json").write_text(
        json.dumps(optimization_summaries["revenue"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORT_DIR / "pricing_optimization_summaries.json").write_text(
        json.dumps(optimization_summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    comparison_rows = []
    for objective, summary in optimization_summaries.items():
        comparison_rows.append({
            "objective": objective,
            "baseline_total_revenue_cny": summary["baseline"]["total_revenue_cny"],
            "optimized_total_revenue_cny": summary["optimized"]["total_revenue_cny"],
            "total_revenue_change_rate": summary["total_revenue_change_rate"],
            "baseline_contribution_profit_cny": summary["baseline"]["contribution_profit_cny"],
            "optimized_contribution_profit_cny": summary["optimized"]["contribution_profit_cny"],
            "contribution_profit_change_rate": summary["contribution_profit_change_rate"],
            "optimized_visitors": summary["optimized"]["predicted_visitors"],
            "capacity_utilization_rate": summary["optimized"]["capacity_utilization_rate"],
            "capacity_constraint_status": summary["capacity_constraint_status"],
            "solver_success": summary["solver_success"],
        })
    pd.DataFrame(comparison_rows).to_csv(
        REPORT_DIR / "pricing_objective_comparison.csv", index=False, encoding="utf-8-sig"
    )
    print("Revenue and contribution-profit pricing optimizations completed.")

    summary = {
        "stage": "Stage 3 - Business Analytics and Pricing Models",
        "status": "COMPLETED",
        "business_kpi_summary": metrics["summary"],
        "elasticity_models_fitted": int(len(elasticity)),
        "elasticity_diagnostics": diagnostics[["product_id", "status", "nobs"]].to_dict("records"),
        "elasticity_results": elasticity.to_dict("records"),
        "forecast_metrics": forecast_metrics,
        "pricing_optimizations": optimization_summaries,
        "important_limitations": [
            "All source data are synthetic.",
            "Forecast backtest uses rolling one-step-ahead lag features, not a fixed-origin 60-day forecast.",
            "Price elasticity is estimated from synthetic data and should not be interpreted as a real market causal effect.",
            "At least one product may have a statistically insignificant price coefficient; interpret product-level results individually.",
            "Pricing recommendations are demonstration scenarios, not operational instructions.",
            "Contribution profit excludes fixed costs, depreciation, tax and financing costs."
        ]
    }
    (REPORT_DIR / "stage3_execution_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary_md = [
        "# SmartPrice AI — Stage 3 执行报告",
        "",
        "本报告基于2025年模拟经营数据。所有结果均为模型演示，不代表真实园区业绩。",
        "",
        "## 经营指标摘要",
        "",
        f"- 综合经营收入：¥{metrics['summary']['total_revenue_cny']:,.2f}",
        f"- 模拟游客数：{metrics['summary']['actual_visitors']:,}",
        f"- 游客人均收入：¥{metrics['summary']['revenue_per_visitor_cny']:,.2f}",
        f"- 贡献利润：¥{metrics['summary']['contribution_profit_cny']:,.2f}",
        f"- 贡献利润率：{metrics['summary']['contribution_margin_rate']:.2%}",
        "",
        "## 产品级价格弹性回归",
        "",
        "| 产品 | 估计价格弹性 | p值 | 95%置信区间 | R² | 5%显著性 |",
        "|---|---:|---:|---|---:|---|",
    ]
    for r in elasticity.to_dict("records"):
        summary_md.append(
            f"| {r['product_name']} | {r['price_elasticity']:.3f} | {r['p_value']:.4f} "
            f"| [{r['ci_95_lower']:.3f}, {r['ci_95_upper']:.3f}] | {r['r_squared']:.3f} "
            f"| {'是' if r['statistical_significance_5pct'] else '否'} |"
        )
    summary_md += [
        "",
        "说明：价格弹性系数来自模拟数据回归；不显著结果不能作为明确的定价依据。",
        "",
        "## 客流预测回测",
        "",
        f"- 训练期：{forecast_metrics['train_period'][0]} 至 {forecast_metrics['train_period'][1]}",
        f"- 测试期：{forecast_metrics['test_period'][0]} 至 {forecast_metrics['test_period'][1]}",
        f"- 测试集MAE：{forecast_metrics['mae_visitors']:.2f}人",
        f"- 测试集WAPE：{forecast_metrics['wape']:.2%}",
        f"- Lag-7基线WAPE：{forecast_metrics['baseline_lag7_wape']:.2%}",
        "",
        "## 动态定价：收入目标与贡献利润目标对比",
        "",
        "| 优化目标 | 预测收入变化率 | 预测贡献利润变化率 | 容量约束 |",
        "|---|---:|---:|---|",
    ]
    for objective, s in optimization_summaries.items():
        summary_md.append(
            f"| {objective} | {s['total_revenue_change_rate']:.2%} "
            f"| {s['contribution_profit_change_rate']:.2%} | {s['capacity_constraint_status']} |"
        )
    summary_md += [
        "",
        "动态定价使用2025-10-04历史模拟场景，价格受产品上下限和相对基准价格±10%约束，预测游客人数受85%容量利用率约束。",
        "",
        "## 限制说明",
        "",
        "- 所有数据均为模拟数据。",
        "- 价格弹性是模拟数据中的统计关联，不是经真实市场验证的因果结论。",
        "- 客流回测为滚动单步预测，不能直接等同于一次性预测未来60天。",
        "- 动态定价优化可能触及价格边界，边界解说明当前目标函数和约束下最优解位于允许区间端点，应进一步做敏感性分析。",
        "- 贡献利润未扣除固定成本、折旧、税费和融资费用，不等同于营业利润或净利润。",
    ]
    (REPORT_DIR / "stage3_summary.md").write_text("\n".join(summary_md), encoding="utf-8")
    print("Stage 3 completed. See reports/stage3/stage3_summary.md")

if __name__ == "__main__":
    main()
