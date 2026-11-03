import numpy as np
import pandas as pd
from .data_access import load_core_data
from .metrics import calculate_business_metrics

def _date_bounds(start_date=None, end_date=None):
    start = pd.Timestamp(start_date) if start_date is not None else None
    end = pd.Timestamp(end_date) if end_date is not None else None
    return start, end

def get_daily_metrics(start_date=None, end_date=None, db_path=None):
    daily = calculate_business_metrics(db_path)["daily_metrics"].copy()
    daily["date"] = pd.to_datetime(daily["date"])
    start, end = _date_bounds(start_date, end_date)
    if start is not None:
        daily = daily[daily["date"] >= start]
    if end is not None:
        daily = daily[daily["date"] <= end]
    return daily.sort_values("date").reset_index(drop=True)

def get_product_analysis(start_date=None, end_date=None, db_path=None):
    tables = load_core_data(db_path)
    ticket = tables["fact_ticket_sales"].copy()
    products = tables["dim_product"].copy()
    ticket["date"] = pd.to_datetime(ticket["date"])
    start, end = _date_bounds(start_date, end_date)
    if start is not None:
        ticket = ticket[ticket["date"] >= start]
    if end is not None:
        ticket = ticket[ticket["date"] <= end]
    merged = ticket.merge(products, on="product_id", how="left")
    result = merged.groupby(
        ["product_id", "product_name", "product_category"], as_index=False
    ).agg(
        net_orders=("net_orders", "sum"),
        net_sales_cny=("net_sales_cny", "sum"),
        ticket_variable_cost_cny=("ticket_variable_cost_cny", "sum"),
        admission_revenue_cny=("admission_revenue_cny", "sum"),
        included_fnb_revenue_cny=("included_fnb_revenue_cny", "sum"),
    )
    result["contribution_profit_cny"] = result["net_sales_cny"] - result["ticket_variable_cost_cny"]
    result["contribution_margin_rate"] = np.where(
        result["net_sales_cny"] > 0,
        result["contribution_profit_cny"] / result["net_sales_cny"], 0
    )
    result["realized_price_cny"] = np.where(
        result["net_orders"] > 0, result["net_sales_cny"] / result["net_orders"], 0
    )
    return result.sort_values("net_sales_cny", ascending=False).reset_index(drop=True)

def get_channel_analysis(start_date=None, end_date=None, db_path=None):
    tables = load_core_data(db_path)
    ticket = tables["fact_ticket_sales"].copy()
    secondary = tables["fact_secondary_sales"].copy()
    for frame in [ticket, secondary]:
        frame["date"] = pd.to_datetime(frame["date"])
    start, end = _date_bounds(start_date, end_date)
    if start is not None:
        ticket = ticket[ticket["date"] >= start]
        secondary = secondary[secondary["date"] >= start]
    if end is not None:
        ticket = ticket[ticket["date"] <= end]
        secondary = secondary[secondary["date"] <= end]
    ticket_channel = ticket.groupby("sales_channel", as_index=False).agg(
        ticket_package_revenue_cny=("net_sales_cny", "sum"),
        ticket_package_orders=("net_orders", "sum")
    )
    secondary_channel = secondary.groupby("sales_channel", as_index=False).agg(
        secondary_revenue_cny=("net_sales_cny", "sum"),
        secondary_transactions=("transaction_count", "sum")
    )
    result = ticket_channel.merge(secondary_channel, on="sales_channel", how="outer").fillna(0)
    result["total_revenue_cny"] = (
        result["ticket_package_revenue_cny"] + result["secondary_revenue_cny"]
    )
    return result.sort_values("total_revenue_cny", ascending=False).reset_index(drop=True)

def get_secondary_analysis(start_date=None, end_date=None, db_path=None):
    tables = load_core_data(db_path)
    secondary = tables["fact_secondary_sales"].copy()
    secondary["date"] = pd.to_datetime(secondary["date"])
    start, end = _date_bounds(start_date, end_date)
    if start is not None:
        secondary = secondary[secondary["date"] >= start]
    if end is not None:
        secondary = secondary[secondary["date"] <= end]
    result = secondary.groupby("consumption_category", as_index=False).agg(
        transactions=("transaction_count", "sum"),
        net_sales_cny=("net_sales_cny", "sum"),
        cogs_cny=("cogs_cny", "sum"),
        gross_profit_cny=("gross_profit_cny", "sum")
    )
    result["gross_margin_rate"] = np.where(
        result["net_sales_cny"] > 0,
        result["gross_profit_cny"] / result["net_sales_cny"], 0
    )
    return result.sort_values("net_sales_cny", ascending=False).reset_index(drop=True)

def build_decision_insights(daily, products, elasticity=None):
    insights = []
    if daily is None or daily.empty:
        return ["当前筛选范围没有可分析的数据。"]
    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"])

    total_revenue = float(daily["total_revenue_cny"].sum())
    total_visitors = int(daily["actual_visitors"].sum())
    rpv = total_revenue / max(total_visitors, 1)
    margin = float(daily["contribution_profit_cny"].sum() / max(total_revenue, 1))
    insights.append(
        f"当前期间综合经营收入为 ¥{total_revenue:,.0f}，模拟游客数为 {total_visitors:,} 人，"
        f"游客人均收入为 ¥{rpv:,.2f}，贡献利润率为 {margin:.1%}。"
    )

    if products is not None and not products.empty:
        top = products.sort_values("net_sales_cny", ascending=False).iloc[0]
        insights.append(
            f"收入贡献最高的产品是「{top['product_name']}」，净销售额 ¥{top['net_sales_cny']:,.0f}。"
            "建议优先保障其销售、库存及服务承载能力，并进一步观察其价格与销量关系。"
        )
        lowest = products.sort_values("contribution_margin_rate", ascending=True).iloc[0]
        insights.append(
            f"当前产品中贡献利润率最低的是「{lowest['product_name']}」（{lowest['contribution_margin_rate']:.1%}）。"
            "建议拆解折扣、退款、单位变动成本及套餐内权益，不宜仅凭毛利率直接下架。"
        )

    high_capacity_days = int((daily["capacity_utilization_rate"] >= 0.85).sum())
    if high_capacity_days:
        insights.append(
            f"筛选期间有 {high_capacity_days} 天容量利用率达到或超过85%。"
            "建议结合排队时长、游客满意度和时段客流评估峰值管理，而不是单纯提高票价。"
        )
    else:
        peak = float(daily["capacity_utilization_rate"].max())
        insights.append(
            f"筛选期间没有日期达到85%的容量利用率，最高值为 {peak:.1%}。"
            "可进一步评估淡时段套餐、渠道促销及二次消费转化。"
        )

    if elasticity is not None and not elasticity.empty:
        nonsig = elasticity.loc[~elasticity["statistical_significance_5pct"], "product_name"].tolist()
        if nonsig:
            insights.append(
                f"价格弹性回归中「{'、'.join(nonsig)}」的价格系数未达到5%显著性水平。"
                "该产品暂不宜仅依据当前模型进行自动调价，建议补充价格实验或更多成交样本。"
            )
    return insights
