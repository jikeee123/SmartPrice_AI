import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime
import numpy as np
import pandas as pd

def _safe_float(value):
    try:
        value = float(value)
        return value if np.isfinite(value) else 0.0
    except Exception:
        return 0.0

def _fmt_money(value):
    return f"¥{_safe_float(value):,.0f}"

def _fmt_pct(value):
    return f"{_safe_float(value):+.1%}"

def _month_table(daily):
    if daily is None or daily.empty:
        return pd.DataFrame()
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["month"] = frame["date"].dt.to_period("M").astype(str)
    agg_cols = {
        "total_revenue_cny": "sum",
        "ticket_package_revenue_cny": "sum",
        "addon_fnb_revenue_cny": "sum",
        "merchandise_revenue_cny": "sum",
        "actual_visitors": "sum",
        "contribution_profit_cny": "sum",
        "total_variable_cost_cny": "sum",
        "ticket_variable_cost_cny": "sum",
        "secondary_cogs_cny": "sum",
    }
    available = {k:v for k,v in agg_cols.items() if k in frame.columns}
    monthly = frame.groupby("month", as_index=False).agg(available)
    monthly["revenue_per_visitor_cny"] = np.where(
        monthly["actual_visitors"] > 0,
        monthly["total_revenue_cny"] / monthly["actual_visitors"], 0
    )
    monthly["contribution_margin_rate"] = np.where(
        monthly["total_revenue_cny"] > 0,
        monthly["contribution_profit_cny"] / monthly["total_revenue_cny"], 0
    )
    return monthly.sort_values("month").reset_index(drop=True)

def explain_monthly_variance(daily, month):
    monthly = _month_table(daily)
    if monthly.empty or month not in monthly["month"].values:
        return {"available": False, "message": "所选月份不在当前日期筛选范围内。"}
    idx = monthly.index[monthly["month"] == month][0]
    if idx == 0:
        return {
            "available": False,
            "message": "当前筛选范围没有所选月份的上一个月数据。请扩大左侧日期筛选范围后再进行环比归因。"
        }
    current = monthly.loc[idx].to_dict()
    previous = monthly.loc[idx - 1].to_dict()

    metrics = [
        "total_revenue_cny", "actual_visitors", "revenue_per_visitor_cny",
        "contribution_profit_cny", "total_variable_cost_cny",
        "contribution_margin_rate"
    ]
    changes = {}
    for key in metrics:
        old = _safe_float(previous.get(key, 0))
        new = _safe_float(current.get(key, 0))
        changes[key] = {
            "previous": old, "current": new, "delta": new-old,
            "change_rate": (new-old)/abs(old) if old else None
        }

    revenue_components = {}
    for key, label in [
        ("ticket_package_revenue_cny", "门票及套餐"),
        ("addon_fnb_revenue_cny", "增量餐饮"),
        ("merchandise_revenue_cny", "周边商品")
    ]:
        old = _safe_float(previous.get(key, 0))
        new = _safe_float(current.get(key, 0))
        revenue_components[label] = {"previous": old, "current": new, "delta": new-old}

    cost_components = {}
    for key, label in [
        ("ticket_variable_cost_cny", "门票及套餐变动成本"),
        ("secondary_cogs_cny", "二次消费商品成本")
    ]:
        old = _safe_float(previous.get(key, 0))
        new = _safe_float(current.get(key, 0))
        cost_components[label] = {"previous": old, "current": new, "delta": new-old}

    # Exact sequential decomposition: Revenue = Visitors x Revenue per Visitor.
    v0 = _safe_float(previous["actual_visitors"])
    v1 = _safe_float(current["actual_visitors"])
    r0 = _safe_float(previous["revenue_per_visitor_cny"])
    r1 = _safe_float(current["revenue_per_visitor_cny"])
    volume_effect = (v1-v0) * r0
    spend_effect = v1 * (r1-r0)
    revenue_delta = _safe_float(current["total_revenue_cny"]) - _safe_float(previous["total_revenue_cny"])
    # Numerical reconciliation residual should be near zero.
    revenue_reconciliation = revenue_delta - volume_effect - spend_effect

    cost_delta = (
        _safe_float(current["total_variable_cost_cny"])
        - _safe_float(previous["total_variable_cost_cny"])
    )
    profit_delta = (
        _safe_float(current["contribution_profit_cny"])
        - _safe_float(previous["contribution_profit_cny"])
    )
    return {
        "available": True,
        "month": month,
        "previous_month": previous["month"],
        "current": current,
        "previous": previous,
        "changes": changes,
        "revenue_components": revenue_components,
        "cost_components": cost_components,
        "revenue_volume_effect": volume_effect,
        "revenue_spend_per_visitor_effect": spend_effect,
        "revenue_reconciliation_residual": revenue_reconciliation,
        "revenue_delta": revenue_delta,
        "cost_delta": cost_delta,
        "profit_delta": profit_delta,
        "profit_identity_residual": profit_delta - (revenue_delta-cost_delta),
    }

def build_monthly_report(daily, products, channels, secondary, month, elasticity=None):
    variance = explain_monthly_variance(daily, month)
    monthly = _month_table(daily)
    row_match = monthly.loc[monthly["month"] == month]
    if row_match.empty:
        return f"# {month} 月度经营分析报告\n\n当前筛选范围内没有该月份的数据。"
    current = row_match.iloc[0].to_dict()

    lines = [
        f"# SmartPrice AI｜{month} 月度经营分析报告",
        "",
        "> 数据性质：模拟经营数据。本报告用于产品原型和分析方法演示，不代表真实主题乐园业绩。",
        "",
        "## 一、管理层摘要",
        "",
        f"- 综合经营收入：**{_fmt_money(current['total_revenue_cny'])}**",
        f"- 模拟游客人数：**{_safe_float(current['actual_visitors']):,.0f} 人**",
        f"- 游客人均收入：**{_fmt_money(current['revenue_per_visitor_cny'])}**",
        f"- 贡献利润：**{_fmt_money(current['contribution_profit_cny'])}**",
        f"- 贡献利润率：**{_safe_float(current['contribution_margin_rate']):.1%}**",
        "",
    ]

    if variance.get("available"):
        lines += [
            "## 二、环比业绩变化",
            "",
            f"与 {variance['previous_month']} 相比，{month} 综合经营收入变化 "
            f"**{_fmt_money(variance['revenue_delta'])}**；贡献利润变化 "
            f"**{_fmt_money(variance['profit_delta'])}**。",
            "",
            "| 指标 | 上月 | 本月 | 变化 |",
            "|---|---:|---:|---:|",
        ]
        for key, label in [
            ("total_revenue_cny", "综合经营收入"),
            ("actual_visitors", "游客人数"),
            ("revenue_per_visitor_cny", "游客人均收入"),
            ("contribution_profit_cny", "贡献利润"),
            ("total_variable_cost_cny", "变动成本"),
        ]:
            c = variance["changes"][key]
            if key == "actual_visitors":
                vals = f"{c['previous']:,.0f} | {c['current']:,.0f} | {c['delta']:+,.0f}"
            else:
                vals = f"{_fmt_money(c['previous'])} | {_fmt_money(c['current'])} | {_fmt_money(c['delta'])}"
            lines.append(f"| {label} | {vals.replace(' | ', ' | ')} |")
        lines += [
            "",
            "### 收入变化拆解",
            "",
            f"- 客流规模影响：{_fmt_money(variance['revenue_volume_effect'])}",
            f"- 游客人均收入影响：{_fmt_money(variance['revenue_spend_per_visitor_effect'])}",
            "",
            "| 收入类别 | 环比变化 |",
            "|---|---:|",
        ]
        for label, item in variance["revenue_components"].items():
            lines.append(f"| {label} | {_fmt_money(item['delta'])} |")
        lines += [
            "",
            "### 贡献利润变化拆解",
            "",
            f"- 收入变化影响：{_fmt_money(variance['revenue_delta'])}",
            f"- 变动成本变化：{_fmt_money(variance['cost_delta'])}",
            f"- 贡献利润变化：{_fmt_money(variance['profit_delta'])}",
            "",
        ]
    else:
        lines += [
            "## 二、环比业绩变化",
            "",
            variance["message"],
            "",
        ]

    if products is not None and not products.empty:
        top = products.sort_values("net_sales_cny", ascending=False).head(5)
        lines += [
            "## 三、产品经营表现 TOP 5",
            "",
            "| 产品 | 净销售额 | 贡献利润 | 贡献利润率 |",
            "|---|---:|---:|---:|",
        ]
        for _, r in top.iterrows():
            lines.append(
                f"| {r['product_name']} | {_fmt_money(r['net_sales_cny'])} "
                f"| {_fmt_money(r['contribution_profit_cny'])} | {r['contribution_margin_rate']:.1%} |"
            )
        low = products.sort_values("contribution_margin_rate").iloc[0]
        lines += [
            "",
            f"当前产品中贡献利润率最低的是「{low['product_name']}」（{low['contribution_margin_rate']:.1%}），"
            "建议进一步核查折扣、退款、单位变动成本和套餐权益分摊。",
            "",
        ]

    if channels is not None and not channels.empty:
        lines += [
            "## 四、渠道表现",
            "",
            "| 渠道 | 综合收入 |",
            "|---|---:|",
        ]
        for _, r in channels.sort_values("total_revenue_cny", ascending=False).iterrows():
            lines.append(f"| {r['sales_channel']} | {_fmt_money(r['total_revenue_cny'])} |")
        lines.append("")

    if secondary is not None and not secondary.empty:
        lines += [
            "## 五、二次消费表现",
            "",
            "| 消费类别 | 净销售额 | 毛利 | 毛利率 |",
            "|---|---:|---:|---:|",
        ]
        for _, r in secondary.iterrows():
            lines.append(
                f"| {r['consumption_category']} | {_fmt_money(r['net_sales_cny'])} "
                f"| {_fmt_money(r['gross_profit_cny'])} | {r['gross_margin_rate']:.1%} |"
            )
        lines.append("")

    if elasticity is not None and not elasticity.empty:
        nonsig = elasticity.loc[~elasticity["statistical_significance_5pct"], "product_name"].tolist()
        lines += ["## 六、定价模型风险提示", ""]
        if nonsig:
            lines.append(
                "以下产品价格弹性估计未达到5%显著性水平：" + "、".join(nonsig) +
                "。不建议仅依据当前系数自动调价。"
            )
        else:
            lines.append(
                "当前模拟回归中的产品价格系数均达到5%显著性水平，但这并不代表真实市场因果效应已经得到验证。"
            )
        lines.append("")

    lines += [
        "## 七、管理建议",
        "",
        "1. 将收入变化拆分为客流规模和游客人均收入两个驱动因素，避免只看收入总额。",
        "2. 对贡献利润率偏低的产品，检查折扣、退款、变动成本和套餐权益结构。",
        "3. 对二次消费业务，分别跟踪交易转化率、客单价、商品毛利率和游客人均二次消费。",
        "4. 对任何价格调整，先进行小范围价格实验和容量压力测试，再考虑扩大实施。",
        "",
        "## 八、口径与限制",
        "",
        "- 综合经营收入 = 门票及套餐净销售额 + 套餐外增量餐饮净销售额 + 周边商品净销售额。",
        "- 套餐内餐饮分配字段用于结构分析，不重复加总。",
        "- 贡献利润 = 综合经营收入 - 门票/套餐变动成本 - 二次消费商品成本。",
        "- 贡献利润未扣除固定成本、人工、租金、折旧、税费和融资费用，不等同于营业利润或净利润。",
        "- 价格弹性来自模拟数据回归，不是经随机价格实验验证的因果关系。",
        "- 本报告的建议为管理分析提示，需结合真实业务数据及管理审批复核。",
    ]
    return "\n".join(lines)

def build_local_answer(question, daily, products, channels=None, secondary=None, month=None, elasticity=None):
    q = (question or "").strip()
    if not q:
        return "请先输入一个经营问题。"
    if daily is None or daily.empty:
        return "当前日期范围没有经营数据，请调整左侧日期筛选范围。"

    total_revenue = _safe_float(daily["total_revenue_cny"].sum())
    visitors = _safe_float(daily["actual_visitors"].sum())
    profit = _safe_float(daily["contribution_profit_cny"].sum())
    rpv = total_revenue / max(visitors, 1)
    margin = profit / max(total_revenue, 1)
    start = pd.to_datetime(daily["date"]).min().strftime("%Y-%m-%d")
    end = pd.to_datetime(daily["date"]).max().strftime("%Y-%m-%d")

    if any(k in q for k in ["价格弹性", "价格敏感", "调价风险"]):
        if elasticity is None or elasticity.empty:
            return "当前没有可用的价格弹性回归结果。"
        lines = ["当前价格弹性模型结果（模拟数据）："]
        for _, row in elasticity.iterrows():
            status = "统计显著" if row["statistical_significance_5pct"] else "未达到5%显著性"
            lines.append(
                f"- {row['product_name']}：弹性 {row['price_elasticity']:.3f}，"
                f"p值 {row['p_value']:.4f}，{status}。"
            )
        lines.append("注意：统计关联不等于因果关系，真实调价前应通过实验或准实验重新验证。")
        return "\n".join(lines)

    if any(k in q for k in ["渠道", "线上", "线下", "ota"]):
        if channels is None or channels.empty:
            return "当前没有渠道明细。"
        lines = ["当前筛选期间渠道收入排名："]
        for _, row in channels.sort_values("total_revenue_cny", ascending=False).iterrows():
            share = row["total_revenue_cny"] / max(channels["total_revenue_cny"].sum(), 1)
            lines.append(f"- {row['sales_channel']}：{_fmt_money(row['total_revenue_cny'])}，收入占比 {share:.1%}。")
        return "\n".join(lines)

    if any(k in q for k in ["餐饮", "周边", "二次消费"]):
        if secondary is None or secondary.empty:
            return "当前没有二次消费数据。"
        lines = ["当前筛选期间二次消费表现："]
        for _, row in secondary.iterrows():
            lines.append(
                f"- {row['consumption_category']}：净销售额 {_fmt_money(row['net_sales_cny'])}，"
                f"毛利率 {row['gross_margin_rate']:.1%}，交易笔数 {row['transactions']:,.0f}。"
            )
        lines.append("建议同时观察游客人均二次消费、交易转化率和毛利率。")
        return "\n".join(lines)

    if any(k in q for k in ["产品", "门票", "套餐", "贡献利润最高", "毛利最高"]):
        if products is None or products.empty:
            return "当前没有产品明细。"
        sort_col = "contribution_profit_cny" if any(k in q for k in ["利润", "毛利"]) else "net_sales_cny"
        top = products.sort_values(sort_col, ascending=False).head(5)
        label = "贡献利润" if sort_col == "contribution_profit_cny" else "净销售额"
        lines = [f"当前产品按{label}排名 TOP 5："]
        for _, row in top.iterrows():
            lines.append(
                f"- {row['product_name']}：{_fmt_money(row[sort_col])}，"
                f"贡献利润率 {row['contribution_margin_rate']:.1%}。"
            )
        return "\n".join(lines)

    if any(k in q for k in ["为什么", "原因", "下降", "增长", "环比", "变化", "归因"]):
        selected_month = month
        match = re.search(r"(20\d{2})[-年/.](1[0-2]|0?[1-9])", q)
        if match:
            selected_month = f"{match.group(1)}-{int(match.group(2)):02d}"
        elif month is None:
            selected_month = _month_table(daily)["month"].iloc[-1]
        variance = explain_monthly_variance(daily, selected_month)
        if not variance["available"]:
            return variance["message"]
        rev_change = variance["revenue_delta"]
        profit_change = variance["profit_delta"]
        direction = "增加" if rev_change >= 0 else "减少"
        return (
            f"{selected_month} 相比 {variance['previous_month']}，综合经营收入{direction} "
            f"{_fmt_money(abs(rev_change))}，贡献利润变化 {_fmt_money(profit_change)}。\n\n"
            f"收入变化可拆分为：客流规模影响 {_fmt_money(variance['revenue_volume_effect'])}；"
            f"游客人均收入影响 {_fmt_money(variance['revenue_spend_per_visitor_effect'])}。\n\n"
            "收入类别变化：" +
            "；".join(f"{k} {_fmt_money(v['delta'])}" for k,v in variance["revenue_components"].items()) +
            f"。\n变动成本变化 {_fmt_money(variance['cost_delta'])}。"
        )

    if any(k in q for k in ["客流", "游客", "人均", "客单价"]):
        return (
            f"当前筛选期间（{start} 至 {end}）：模拟游客人数 {visitors:,.0f} 人，"
            f"游客人均收入 {_fmt_money(rpv)}。建议结合节假日、天气、营销活动和容量利用率进一步分析客流变化。"
        )

    if any(k in q for k in ["利润", "盈利", "毛利"]) and not any(k in q for k in ["收入", "营收"]):
        return (
            f"当前筛选期间贡献利润为 {_fmt_money(profit)}，贡献利润率为 {margin:.1%}。"
            f"该指标已扣除门票/套餐变动成本和二次消费商品成本，但未扣除固定成本、人工、租金、折旧、税费及融资费用。"
        )

    return (
        f"当前经营概览（{start} 至 {end}）：\n"
        f"- 综合经营收入：{_fmt_money(total_revenue)}\n"
        f"- 模拟游客人数：{visitors:,.0f} 人\n"
        f"- 游客人均收入：{_fmt_money(rpv)}\n"
        f"- 贡献利润：{_fmt_money(profit)}\n"
        f"- 贡献利润率：{margin:.1%}\n\n"
        "你还可以询问产品排名、渠道表现、二次消费、价格弹性，或指定月份的收入变化原因。"
    )

def llm_configuration():
    endpoint = os.getenv("SMARTPRICE_LLM_ENDPOINT", "").strip()
    api_key = os.getenv("SMARTPRICE_LLM_API_KEY", "").strip()
    model = os.getenv("SMARTPRICE_LLM_MODEL", "").strip()
    return {
        "enabled": bool(endpoint and api_key and model),
        "endpoint": endpoint,
        "api_key": api_key,
        "model": model
    }

def _call_openai_compatible(question, context, timeout=35):
    cfg = llm_configuration()
    if not cfg["enabled"]:
        return None, "未配置外部模型，使用本地经营分析模式。"
    system_prompt = (
        "你是主题乐园经营分析顾问。只能依据用户提供的聚合经营数据回答。"
        "明确区分数据事实、计算结果、推断和建议；不能编造数据。"
        "如数据不足，明确说明。解释贡献利润时，必须说明其不等同于营业利润或净利润。"
        "价格弹性来自模拟数据时，必须说明不能据此得出真实因果结论。"
        "回答使用简体中文，结构清晰、先结论后依据，给出可执行但需人工复核的建议。"
    )
    payload = {
        "model": cfg["model"],
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                "以下为模拟园区经营数据的聚合摘要：\n"
                + json.dumps(context, ensure_ascii=False, default=str)
                + "\n\n经营管理人员的问题：\n" + question
            )}
        ]
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        cfg["endpoint"],
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "\n".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            )
        return str(content).strip(), None
    except Exception as exc:
        return None, f"外部模型调用失败，已回退本地分析：{exc}"

def build_llm_context(daily, products, channels=None, secondary=None, elasticity=None):
    if daily is None or daily.empty:
        return {}
    total_revenue = _safe_float(daily["total_revenue_cny"].sum())
    visitors = _safe_float(daily["actual_visitors"].sum())
    profit = _safe_float(daily["contribution_profit_cny"].sum())
    monthly = _month_table(daily)
    return {
        "data_type": "synthetic_demo_data",
        "period": [
            pd.to_datetime(daily["date"]).min().strftime("%Y-%m-%d"),
            pd.to_datetime(daily["date"]).max().strftime("%Y-%m-%d")
        ],
        "kpis": {
            "total_revenue_cny": round(total_revenue, 2),
            "visitors": int(visitors),
            "revenue_per_visitor_cny": round(total_revenue/max(visitors,1), 2),
            "contribution_profit_cny": round(profit, 2),
            "contribution_margin_rate": round(profit/max(total_revenue,1), 4)
        },
        "monthly": monthly.tail(12).round(2).to_dict("records"),
        "products": (
            products.sort_values("net_sales_cny", ascending=False)
            .head(8)[["product_name","net_sales_cny","contribution_profit_cny","contribution_margin_rate"]]
            .round(3).to_dict("records")
            if products is not None and not products.empty else []
        ),
        "channels": (
            channels.round(2).to_dict("records")
            if channels is not None and not channels.empty else []
        ),
        "secondary_consumption": (
            secondary.round(2).to_dict("records")
            if secondary is not None and not secondary.empty else []
        ),
        "elasticity": (
            elasticity[["product_name","price_elasticity","p_value","statistical_significance_5pct"]]
            .round(4).to_dict("records")
            if elasticity is not None and not elasticity.empty else []
        ),
        "metric_definition": (
            "Contribution profit equals total revenue less ticket/package variable cost and secondary sales COGS; "
            "it excludes fixed costs, payroll, rent, depreciation, taxes and financing costs."
        )
    }

def answer_management_question(question, daily, products, channels=None, secondary=None, month=None, elasticity=None):
    local_answer = build_local_answer(
        question, daily, products, channels, secondary, month, elasticity
    )
    context = build_llm_context(daily, products, channels, secondary, elasticity)
    llm_answer, warning = _call_openai_compatible(question, context)
    if llm_answer:
        return {"answer": llm_answer, "mode": "external_llm", "warning": None}
    return {"answer": local_answer, "mode": "local_rules", "warning": warning}

def get_monthly_variance_table(variance):
    if not variance or not variance.get("available"):
        return pd.DataFrame()
    rows = []
    for label, item in variance["revenue_components"].items():
        rows.append({"类别": label, "变化金额": item["delta"], "类型": "收入"})
    for label, item in variance["cost_components"].items():
        rows.append({"类别": label, "变化金额": item["delta"], "类型": "成本"})
    rows.append({"类别": "贡献利润变化", "变化金额": variance["profit_delta"], "类型": "利润"})
    return pd.DataFrame(rows)
