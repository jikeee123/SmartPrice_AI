import numpy as np
import pandas as pd
from .data_access import load_core_data

def calculate_business_metrics(db_path=None):
    t = load_core_data(db_path)
    ticket = t["fact_ticket_sales"].copy()
    product = t["dim_product"].copy()
    secondary = t["fact_secondary_sales"].copy()
    ops = t["fact_daily_operations"].copy()

    ticket["date"] = pd.to_datetime(ticket["date"])
    secondary["date"] = pd.to_datetime(secondary["date"])
    ops["date"] = pd.to_datetime(ops["date"])

    ticket_daily = ticket.groupby("date", as_index=False).agg(
        ticket_package_revenue_cny=("net_sales_cny", "sum"),
        allocated_admission_revenue_cny=("admission_revenue_cny", "sum"),
        included_fnb_revenue_cny=("included_fnb_revenue_cny", "sum"),
        net_ticket_package_orders=("net_orders", "sum"),
        ticket_variable_cost_cny=("ticket_variable_cost_cny", "sum"),
    )
    secondary_daily = secondary.pivot_table(
        index="date", columns="consumption_category", values="net_sales_cny",
        aggfunc="sum", fill_value=0
    ).reset_index()
    secondary_daily.columns.name = None
    secondary_daily = secondary_daily.rename(columns={
        "FNB": "addon_fnb_revenue_cny",
        "MERCH": "merchandise_revenue_cny"
    })
    secondary_cost_daily = secondary.groupby("date", as_index=False).agg(
        secondary_cogs_cny=("cogs_cny", "sum"),
        secondary_gross_profit_cny=("gross_profit_cny", "sum"),
        secondary_transactions=("transaction_count", "sum")
    )

    daily = ops.merge(ticket_daily, on="date", how="left")
    daily = daily.merge(secondary_daily, on="date", how="left")
    daily = daily.merge(secondary_cost_daily, on="date", how="left")
    for col in [
        "ticket_package_revenue_cny", "allocated_admission_revenue_cny",
        "included_fnb_revenue_cny", "net_ticket_package_orders",
        "ticket_variable_cost_cny", "addon_fnb_revenue_cny",
        "merchandise_revenue_cny", "secondary_cogs_cny",
        "secondary_gross_profit_cny", "secondary_transactions"
    ]:
        daily[col] = daily[col].fillna(0)

    daily["total_revenue_cny"] = (
        daily["ticket_package_revenue_cny"]
        + daily["addon_fnb_revenue_cny"]
        + daily["merchandise_revenue_cny"]
    )
    daily["total_variable_cost_cny"] = daily["ticket_variable_cost_cny"] + daily["secondary_cogs_cny"]
    daily["contribution_profit_cny"] = daily["total_revenue_cny"] - daily["total_variable_cost_cny"]
    daily["revenue_per_visitor_cny"] = np.where(
        daily["actual_visitors"] > 0,
        daily["total_revenue_cny"] / daily["actual_visitors"], 0
    )
    daily["secondary_spend_per_visitor_cny"] = np.where(
        daily["actual_visitors"] > 0,
        (daily["addon_fnb_revenue_cny"] + daily["merchandise_revenue_cny"]) / daily["actual_visitors"], 0
    )
    daily["contribution_margin_rate"] = np.where(
        daily["total_revenue_cny"] > 0,
        daily["contribution_profit_cny"] / daily["total_revenue_cny"], 0
    )
    daily["date"] = pd.to_datetime(daily["date"])
    daily["month"] = daily["date"].dt.to_period("M").astype(str)

    product_metrics = ticket.merge(product, on="product_id", how="left")
    product_metrics = product_metrics.groupby(
        ["product_id", "product_name", "product_category"], as_index=False
    ).agg(
        net_orders=("net_orders", "sum"),
        net_sales_cny=("net_sales_cny", "sum"),
        admission_revenue_cny=("admission_revenue_cny", "sum"),
        included_fnb_revenue_cny=("included_fnb_revenue_cny", "sum"),
        ticket_variable_cost_cny=("ticket_variable_cost_cny", "sum"),
        avg_list_price_cny=("list_unit_price_cny", "mean"),
    )
    units = product.set_index("product_id")["visitor_units_per_order"].to_dict()
    product_metrics["estimated_visitors"] = product_metrics.apply(
        lambda r: r["net_orders"] * units[r["product_id"]], axis=1
    )
    product_metrics["contribution_profit_cny"] = (
        product_metrics["net_sales_cny"] - product_metrics["ticket_variable_cost_cny"]
    )
    product_metrics["contribution_margin_rate"] = np.where(
        product_metrics["net_sales_cny"] > 0,
        product_metrics["contribution_profit_cny"] / product_metrics["net_sales_cny"], 0
    )

    secondary_metrics = secondary.groupby("consumption_category", as_index=False).agg(
        transactions=("transaction_count", "sum"),
        net_sales_cny=("net_sales_cny", "sum"),
        cogs_cny=("cogs_cny", "sum"),
        gross_profit_cny=("gross_profit_cny", "sum"),
    )
    secondary_metrics["gross_margin_rate"] = np.where(
        secondary_metrics["net_sales_cny"] > 0,
        secondary_metrics["gross_profit_cny"] / secondary_metrics["net_sales_cny"], 0
    )

    channel_ticket = ticket.groupby("sales_channel", as_index=False).agg(
        ticket_package_revenue_cny=("net_sales_cny", "sum"),
        ticket_package_orders=("net_orders", "sum")
    )
    channel_secondary = secondary.groupby("sales_channel", as_index=False).agg(
        secondary_revenue_cny=("net_sales_cny", "sum"),
        secondary_transactions=("transaction_count", "sum")
    )
    channel_metrics = channel_ticket.merge(channel_secondary, on="sales_channel", how="outer").fillna(0)
    channel_metrics["total_revenue_cny"] = (
        channel_metrics["ticket_package_revenue_cny"] + channel_metrics["secondary_revenue_cny"]
    )

    monthly = daily.groupby("month", as_index=False).agg(
        total_revenue_cny=("total_revenue_cny", "sum"),
        ticket_package_revenue_cny=("ticket_package_revenue_cny", "sum"),
        addon_fnb_revenue_cny=("addon_fnb_revenue_cny", "sum"),
        merchandise_revenue_cny=("merchandise_revenue_cny", "sum"),
        actual_visitors=("actual_visitors", "sum"),
        contribution_profit_cny=("contribution_profit_cny", "sum"),
        total_variable_cost_cny=("total_variable_cost_cny", "sum"),
    )
    monthly["revenue_per_visitor_cny"] = np.where(
        monthly["actual_visitors"] > 0,
        monthly["total_revenue_cny"] / monthly["actual_visitors"], 0
    )
    monthly["contribution_margin_rate"] = np.where(
        monthly["total_revenue_cny"] > 0,
        monthly["contribution_profit_cny"] / monthly["total_revenue_cny"], 0
    )

    summary = {
        "period_start": daily["date"].min().strftime("%Y-%m-%d"),
        "period_end": daily["date"].max().strftime("%Y-%m-%d"),
        "total_revenue_cny": round(float(daily["total_revenue_cny"].sum()), 2),
        "ticket_package_revenue_cny": round(float(daily["ticket_package_revenue_cny"].sum()), 2),
        "addon_fnb_revenue_cny": round(float(daily["addon_fnb_revenue_cny"].sum()), 2),
        "merchandise_revenue_cny": round(float(daily["merchandise_revenue_cny"].sum()), 2),
        "actual_visitors": int(daily["actual_visitors"].sum()),
        "revenue_per_visitor_cny": round(
            float(daily["total_revenue_cny"].sum() / max(daily["actual_visitors"].sum(), 1)), 2
        ),
        "contribution_profit_cny": round(float(daily["contribution_profit_cny"].sum()), 2),
        "contribution_margin_rate": round(
            float(daily["contribution_profit_cny"].sum() / max(daily["total_revenue_cny"].sum(), 1)), 4
        ),
    }
    return {
        "daily_metrics": daily,
        "monthly_metrics": monthly,
        "product_metrics": product_metrics,
        "secondary_metrics": secondary_metrics,
        "channel_metrics": channel_metrics,
        "summary": summary,
    }
