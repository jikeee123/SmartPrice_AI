import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from .data_access import load_core_data, load_daily_product_features
from .elasticity import fit_price_elasticity_models, predict_product_orders

def optimize_pricing(db_path=None, target_date="2025-10-04", objective="revenue",
                     capacity_target_rate=0.85, max_change_rate=0.10):
    tables = load_core_data(db_path)
    products = tables["dim_product"].copy()
    ops = tables["fact_daily_operations"].copy()
    secondary = tables["fact_secondary_sales"].copy()
    ticket = tables["fact_ticket_sales"].copy()
    context = tables["fact_daily_context"].copy()
    calendar = tables["dim_date"].copy()
    competitors = tables["fact_competitor_price"].copy()

    elasticity_results, models, diagnostics, feature_data = fit_price_elasticity_models(db_path)
    if len(models) != len(products):
        missing = sorted(set(products["product_id"]) - set(models))
        raise RuntimeError(f"Elasticity models missing for products: {missing}")

    # Build one target-date feature row per product from the historical scenario date.
    target = pd.Timestamp(target_date)
    date_text = target.strftime("%Y-%m-%d")
    date_context = context.loc[context["date"] == date_text]
    date_calendar = calendar.loc[calendar["date"] == date_text]
    if date_context.empty or date_calendar.empty:
        raise ValueError(f"Target date {date_text} is not present in the 2025 synthetic context/calendar.")

    competitor_price = float(
        competitors.loc[competitors["date"] == date_text, "competitor_price_cny"].mean()
    )
    ctx = date_context.iloc[0].to_dict()
    cal = date_calendar.iloc[0].to_dict()
    daily_products = feature_data.loc[feature_data["date"] == target].copy()
    daily_products = daily_products.set_index("product_id")

    feature_rows = {}
    baseline_prices = []
    lower_bounds = []
    upper_bounds = []
    for p in products.to_dict("records"):
        pid = p["product_id"]
        if pid not in daily_products.index:
            raise ValueError(f"No daily sales record for {pid} on {date_text}.")
        hist_row = daily_products.loc[pid].to_dict()
        # Use target-date context from the input tables and retain fitted feature schema.
        for k, v in ctx.items():
            if k != "date":
                hist_row[k] = v
        for k, v in cal.items():
            if k != "date":
                hist_row[k] = v
        hist_row["competitor_price_cny"] = competitor_price
        feature_rows[pid] = hist_row
        base_price = float(hist_row["list_unit_price_cny"])
        baseline_prices.append(base_price)
        lower_bounds.append(max(float(p["min_price_cny"]), base_price * (1 - max_change_rate)))
        upper_bounds.append(min(float(p["max_price_cny"]), base_price * (1 + max_change_rate)))

    units = products.set_index("product_id")["visitor_units_per_order"].to_dict()
    variable_cost = products.set_index("product_id")["unit_variable_cost_cny"].to_dict()
    # Net revenue realization factor accounts for discounts/refunds by product.
    ticket["net_factor"] = np.where(
        ticket["net_orders"] > 0,
        ticket["net_sales_cny"] / (ticket["net_orders"] * ticket["list_unit_price_cny"]),
        np.nan
    )
    realization = ticket.groupby("product_id")["net_factor"].mean().to_dict()

    # Incremental secondary spend and cost ratio are estimated from the synthetic history.
    total_secondary_revenue = float(secondary["net_sales_cny"].sum())
    total_secondary_cogs = float(secondary["cogs_cny"].sum())
    total_visitors = float(ops["actual_visitors"].sum())
    secondary_spend_per_visitor = total_secondary_revenue / max(total_visitors, 1)
    secondary_cogs_rate = total_secondary_cogs / max(total_secondary_revenue, 1)

    target_ops = ops.loc[ops["date"] == date_text].iloc[0]
    park_capacity = float(target_ops["park_capacity"])
    capacity_limit = park_capacity * capacity_target_rate

    pids = products["product_id"].tolist()
    model_by_pid = models

    def evaluate(price_vector):
        orders = {}
        product_revenues = {}
        for i, pid in enumerate(pids):
            q = predict_product_orders(model_by_pid[pid], feature_rows[pid], float(price_vector[i]))
            orders[pid] = q
            factor = float(realization.get(pid, 0.95))
            product_revenues[pid] = q * float(price_vector[i]) * factor
        visitors = sum(orders[pid] * float(units[pid]) for pid in pids)
        ticket_package_revenue = sum(product_revenues.values())
        addon_revenue = visitors * secondary_spend_per_visitor
        total_revenue = ticket_package_revenue + addon_revenue
        ticket_cost = sum(orders[pid] * float(variable_cost[pid]) for pid in pids)
        secondary_cost = addon_revenue * secondary_cogs_rate
        contribution_profit = total_revenue - ticket_cost - secondary_cost
        return {
            "orders": orders, "product_revenues": product_revenues,
            "visitors": visitors, "ticket_package_revenue": ticket_package_revenue,
            "addon_revenue": addon_revenue, "total_revenue": total_revenue,
            "contribution_profit": contribution_profit,
            "capacity_utilization": visitors / max(park_capacity, 1),
            "avg_queue_wait_min": max(5.0, 5.0 + 38.0 * (visitors / max(park_capacity, 1)) ** 2)
        }

    baseline = evaluate(np.array(baseline_prices, dtype=float))
    def objective_fn(prices):
        result = evaluate(prices)
        score = result["total_revenue"] if objective == "revenue" else result["contribution_profit"]
        return -float(score)

    constraint = {
        "type": "ineq",
        "fun": lambda prices: capacity_limit - evaluate(prices)["visitors"]
    }
    result = minimize(
        objective_fn,
        x0=np.array(baseline_prices, dtype=float),
        method="SLSQP",
        bounds=list(zip(lower_bounds, upper_bounds)),
        constraints=[constraint],
        options={"maxiter": 500, "ftol": 1e-7, "disp": False}
    )
    optimized_prices = np.array(result.x if result.success else baseline_prices, dtype=float)
    optimized = evaluate(optimized_prices)
    capacity_status = "PASS" if optimized["visitors"] <= capacity_limit + 1e-4 else "WARNING"

    rows = []
    for i, pid in enumerate(pids):
        p = products.loc[products["product_id"] == pid].iloc[0]
        rows.append({
            "target_date": date_text,
            "product_id": pid,
            "product_name": p["product_name"],
            "baseline_price_cny": round(float(baseline_prices[i]), 2),
            "recommended_price_cny": round(float(optimized_prices[i]), 2),
            "price_change_rate": round(float(optimized_prices[i] / baseline_prices[i] - 1), 4),
            "baseline_predicted_orders": round(float(baseline["orders"][pid]), 2),
            "recommended_predicted_orders": round(float(optimized["orders"][pid]), 2),
            "recommended_product_revenue_cny": round(float(optimized["product_revenues"][pid]), 2),
            "optimization_objective": objective,
            "capacity_constraint_status": capacity_status,
            "at_price_bound": bool(
                abs(float(optimized_prices[i]) - float(lower_bounds[i])) < 0.02
                or abs(float(optimized_prices[i]) - float(upper_bounds[i])) < 0.02
            ),
            "solver_success": bool(result.success),
            "solver_message": str(result.message),
        })
    summary = {
        "target_date": date_text,
        "objective": objective,
        "capacity_target_rate": capacity_target_rate,
        "capacity_limit_visitors": round(capacity_limit, 2),
        "solver_success": bool(result.success),
        "solver_message": str(result.message),
        "baseline": {
            "predicted_visitors": round(float(baseline["visitors"]), 2),
            "capacity_utilization_rate": round(float(baseline["capacity_utilization"]), 4),
            "ticket_package_revenue_cny": round(float(baseline["ticket_package_revenue"]), 2),
            "addon_secondary_revenue_cny": round(float(baseline["addon_revenue"]), 2),
            "total_revenue_cny": round(float(baseline["total_revenue"]), 2),
            "contribution_profit_cny": round(float(baseline["contribution_profit"]), 2),
            "predicted_avg_queue_wait_min": round(float(baseline["avg_queue_wait_min"]), 2),
        },
        "optimized": {
            "predicted_visitors": round(float(optimized["visitors"]), 2),
            "capacity_utilization_rate": round(float(optimized["capacity_utilization"]), 4),
            "ticket_package_revenue_cny": round(float(optimized["ticket_package_revenue"]), 2),
            "addon_secondary_revenue_cny": round(float(optimized["addon_revenue"]), 2),
            "total_revenue_cny": round(float(optimized["total_revenue"]), 2),
            "contribution_profit_cny": round(float(optimized["contribution_profit"]), 2),
            "predicted_avg_queue_wait_min": round(float(optimized["avg_queue_wait_min"]), 2),
        },
        "total_revenue_change_rate": round(
            float(optimized["total_revenue"] / max(baseline["total_revenue"], 1) - 1), 4
        ),
        "contribution_profit_change_rate": round(
            float(optimized["contribution_profit"] / max(baseline["contribution_profit"], 1) - 1), 4
        ),
        "capacity_constraint_status": capacity_status,
        "interpretation_note": (
            "All figures are model-based estimates on synthetic data. "
            "They are not observed real-world uplift or a validated production pricing policy."
        )
    }
    return pd.DataFrame(rows), summary, elasticity_results
