from pathlib import Path
import json
import sys
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smartprice_src.metrics import calculate_business_metrics
from smartprice_src.data_access import load_core_data
from smartprice_src.elasticity import fit_price_elasticity_models
from smartprice_src.forecasting import run_forecast_backtest
from smartprice_src.pricing import optimize_pricing
from smartprice_src.dashboard_data import (
    get_daily_metrics, get_product_analysis, get_channel_analysis,
    get_secondary_analysis, build_decision_insights
)
from smartprice_src.ai_decision import (
    answer_management_question, build_monthly_report,
    explain_monthly_variance, get_monthly_variance_table, llm_configuration
)

@st.cache_data(show_spinner="正在读取经营数据库…")
def cached_metrics():
    return calculate_business_metrics()

@st.cache_data(show_spinner="正在读取业务数据…")
def cached_tables():
    return load_core_data()

@st.cache_data(show_spinner="正在估计各产品价格弹性…")
def cached_elasticity():
    results, _, diagnostics, _ = fit_price_elasticity_models()
    return results, diagnostics

@st.cache_data(show_spinner="正在执行客流预测回测…")
def cached_forecast():
    _, metrics, backtest = run_forecast_backtest(
        model_dir=ROOT / "models",
        report_dir=ROOT / "reports" / "stage3"
    )
    return metrics, backtest

@st.cache_data(show_spinner="正在运行动态定价优化…")
def cached_pricing(target_date, objective, capacity_target_rate, max_change_rate):
    result, summary, elasticity = optimize_pricing(
        target_date=target_date,
        objective=objective,
        capacity_target_rate=capacity_target_rate,
        max_change_rate=max_change_rate
    )
    return result, summary, elasticity

def money(value, digits=0):
    return f"¥{float(value):,.{digits}f}"

def pct(value):
    return f"{float(value):.1%}"

def to_csv_bytes(frame):
    return frame.to_csv(index=False).encode("utf-8-sig")

def page_header(title, subtitle):
    st.markdown(f"""
    <div class="hero">
        <h1>{title}</h1>
        <p>{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)

def get_filtered_frames(start_date, end_date):
    daily = get_daily_metrics(start_date, end_date)
    products = get_product_analysis(start_date, end_date)
    channels = get_channel_analysis(start_date, end_date)
    secondary = get_secondary_analysis(start_date, end_date)
    return daily, products, channels, secondary

def monthly_from_daily(daily):
    if daily.empty:
        return pd.DataFrame()
    temp = daily.copy()
    temp["month"] = temp["date"].dt.to_period("M").astype(str)
    return temp.groupby("month", as_index=False).agg(
        total_revenue_cny=("total_revenue_cny", "sum"),
        contribution_profit_cny=("contribution_profit_cny", "sum"),
        actual_visitors=("actual_visitors", "sum"),
        addon_fnb_revenue_cny=("addon_fnb_revenue_cny", "sum"),
        merchandise_revenue_cny=("merchandise_revenue_cny", "sum"),
        ticket_package_revenue_cny=("ticket_package_revenue_cny", "sum")
    )

def render_overview(daily, products, channels):
    page_header("经营管理驾驶舱", "主题乐园综合经营表现 · 收入、客流、利润与产品结构")
    if daily.empty:
        st.warning("所选日期范围没有数据。")
        return

    revenue = daily["total_revenue_cny"].sum()
    visitors = daily["actual_visitors"].sum()
    profit = daily["contribution_profit_cny"].sum()
    rpv = revenue / max(visitors, 1)
    margin = profit / max(revenue, 1)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("综合经营收入", f"¥{revenue/1e8:.2f}亿" if revenue>=1e8 else f"¥{revenue/1e4:.1f}万" if revenue>=1e4 else money(revenue), help=money(revenue,2))
    c2.metric("模拟游客人数", f"{visitors/1e4:.2f}万" if visitors>=1e4 else f"{visitors:,.0f}", help=f"{visitors:,.0f}人")
    c3.metric("游客人均收入", money(rpv, 2))
    c4.metric("贡献利润", f"¥{profit/1e8:.2f}亿" if profit>=1e8 else f"¥{profit/1e4:.1f}万" if profit>=1e4 else money(profit), help=money(profit,2))
    c5.metric("贡献利润率", pct(margin))

    monthly = monthly_from_daily(daily)
    left, right = st.columns([1.7, 1])
    with left:
        st.subheader("收入趋势")
        if not monthly.empty:
            fig = px.line(
                monthly, x="month", y="total_revenue_cny",
                markers=True, labels={"month":"月份","total_revenue_cny":"综合经营收入（元）"}
            )
            fig.update_layout(margin=dict(l=10,r=10,t=15,b=10), height=330)
            st.plotly_chart(fig, theme=None,width="stretch")
    with right:
        st.subheader("收入结构")
        mix = pd.DataFrame({
            "收入类别": ["门票及套餐", "增量餐饮", "周边商品"],
            "收入": [
                daily["ticket_package_revenue_cny"].sum(),
                daily["addon_fnb_revenue_cny"].sum(),
                daily["merchandise_revenue_cny"].sum()
            ]
        })
        fig = px.pie(mix, names="收入类别", values="收入", hole=0.55)
        fig.update_layout(margin=dict(l=5,r=5,t=15,b=5), height=330, legend_title="")
        st.plotly_chart(fig, theme=None,width="stretch")

    left, right = st.columns(2)
    with left:
        st.subheader("每日客流与容量利用率")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=daily["date"], y=daily["actual_visitors"], name="实际游客数",
            mode="lines", line=dict(width=2)
        ))
        fig.update_layout(
            xaxis_title="日期", yaxis_title="游客人数",
            margin=dict(l=10,r=10,t=15,b=10), height=300
        )
        st.plotly_chart(fig, theme=None,width="stretch")
    with right:
        st.subheader("产品收入贡献 TOP 6")
        top = products.sort_values("net_sales_cny", ascending=True).tail(6)
        fig = px.bar(
            top, x="net_sales_cny", y="product_name", orientation="h",
            labels={"net_sales_cny":"净销售额（元）","product_name":"产品"}
        )
        fig.update_layout(margin=dict(l=10,r=10,t=15,b=10), height=300)
        st.plotly_chart(fig, theme=None,width="stretch")

    st.caption("数据说明：本原型使用模拟经营数据。贡献利润为管理分析口径，不等同于营业利润或净利润。")

def render_business_analysis(daily, products, channels, secondary):
    page_header("经营数据分析", "从收入、客流、渠道和产品结构识别经营变化")
    if daily.empty:
        st.warning("所选日期范围没有数据。")
        return
    monthly = monthly_from_daily(daily)
    a, b = st.columns(2)
    with a:
        st.subheader("月度收入与贡献利润")
        if not monthly.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=monthly["month"], y=monthly["total_revenue_cny"], name="综合经营收入"))
            fig.add_trace(go.Scatter(x=monthly["month"], y=monthly["contribution_profit_cny"], name="贡献利润", mode="lines+markers"))
            fig.update_layout(barmode="group", height=350, margin=dict(l=10,r=10,t=15,b=10))
            st.plotly_chart(fig, theme=None,width="stretch")
    with b:
        st.subheader("销售渠道收入")
        fig = px.bar(
            channels, x="sales_channel", y="total_revenue_cny", color="sales_channel",
            labels={"sales_channel":"渠道","total_revenue_cny":"综合收入（元）"}
        )
        fig.update_layout(showlegend=False, height=350, margin=dict(l=10,r=10,t=15,b=10))
        st.plotly_chart(fig, theme=None,width="stretch")

    st.subheader("经营指标明细")
    display_daily = daily[[
        "date","actual_visitors","total_revenue_cny","revenue_per_visitor_cny",
        "contribution_profit_cny","contribution_margin_rate","capacity_utilization_rate"
    ]].copy()
    display_daily["date"] = display_daily["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(display_daily, width="stretch", hide_index=True)
    st.download_button(
        "下载经营分析明细 CSV", to_csv_bytes(display_daily),
        file_name="smartprice_business_analysis.csv", mime="text/csv"
    )

    left, right = st.columns(2)
    with left:
        st.subheader("产品收入结构")
        st.dataframe(products, width="stretch", hide_index=True)
    with right:
        st.subheader("二次消费结构")
        st.dataframe(secondary, width="stretch", hide_index=True)

def render_forecast():
    page_header("客流需求预测", "基于历史经营数据进行客流预测回测与模型效果评估")
    try:
        metrics, backtest = cached_forecast()
    except Exception as exc:
        st.error(f"客流预测模型运行失败：{exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("测试集 MAE", f"{metrics['mae_visitors']:,.1f} 人")
    c2.metric("测试集 WAPE", pct(metrics["wape"]))
    c3.metric("Lag-7 基线 WAPE", pct(metrics["baseline_lag7_wape"]))
    c4.metric("测试集 R²", f"{metrics['r_squared']:.3f}")

    st.subheader("预测值与实际客流对比")
    frame = backtest.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["actual_visitors"], name="实际客流", mode="lines"))
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["predicted_visitors"], name="模型预测", mode="lines"))
    fig.update_layout(height=390, xaxis_title="日期", yaxis_title="游客人数", margin=dict(l=10,r=10,t=15,b=10))
    st.plotly_chart(fig, theme=None,width="stretch")

    st.subheader("模型评估说明")
    st.write(
        f"训练期：{metrics['train_period'][0]} 至 {metrics['train_period'][1]}；"
        f"测试期：{metrics['test_period'][0]} 至 {metrics['test_period'][1]}。"
    )
    st.write(
        f"模型 MAE 为 {metrics['mae_visitors']:.1f} 人，WAPE 为 {metrics['wape']:.1%}；"
        f"简单的7天滞后基线 WAPE 为 {metrics['baseline_lag7_wape']:.1%}。"
    )
    st.info(
        "当前页面展示的是历史滚动单步回测：预测某一天时，使用此前已观察到的客流构造滞后特征。"
        "它不是对当前日期未来数周的实时预测。要用于真实未来预测，需要更新到最新经营数据，并输入未来天气、活动和开放计划。"
    )
    st.download_button(
        "下载客流预测回测 CSV", to_csv_bytes(frame),
        file_name="smartprice_visitor_forecast_backtest.csv", mime="text/csv"
    )

def render_pricing(tables):
    page_header("AI 智能定价中心", "在需求、收入、贡献利润和园区容量约束下进行价格情景优化")
    dates = pd.to_datetime(tables["dim_date"]["date"])
    default_date = pd.Timestamp("2025-10-04").date()
    if default_date < dates.min().date() or default_date > dates.max().date():
        default_date = dates.max().date()

    with st.form("pricing_scenario_form"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            target_date = st.date_input(
                "模拟场景日期", value=default_date,
                min_value=dates.min().date(), max_value=dates.max().date()
            )
        with col2:
            objective_label = st.selectbox("优化目标", ["综合收入最大化", "贡献利润最大化"])
        with col3:
            capacity_target = st.slider("容量利用率上限", 0.60, 0.95, 0.85, 0.01)
        with col4:
            max_change = st.slider("单次价格调整上限", 0.05, 0.20, 0.10, 0.01)

        submitted = st.form_submit_button("运行定价优化", type="primary", width="stretch")

    objective = "revenue" if objective_label == "综合收入最大化" else "profit"
    if submitted or "pricing_result" not in st.session_state:
        with st.spinner("正在估计价格弹性并求解价格组合…"):
            try:
                result, summary, elasticity = cached_pricing(
                    str(target_date), objective, float(capacity_target), float(max_change)
                )
                st.session_state["pricing_result"] = result
                st.session_state["pricing_summary"] = summary
                st.session_state["pricing_elasticity"] = elasticity
            except Exception as exc:
                st.error(f"定价优化运行失败：{exc}")
                return

    result = st.session_state["pricing_result"]
    summary = st.session_state["pricing_summary"]
    elasticity = st.session_state["pricing_elasticity"]

    base = summary["baseline"]
    opt = summary["optimized"]
    st.subheader("优化情景对比")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("预测收入", money(opt["total_revenue_cny"]), f"{summary['total_revenue_change_rate']:+.2%}")
    c2.metric("预测贡献利润", money(opt["contribution_profit_cny"]), f"{summary['contribution_profit_change_rate']:+.2%}")
    c3.metric("预测游客人数", f"{opt['predicted_visitors']:,.0f}", f"{opt['predicted_visitors']-base['predicted_visitors']:+,.0f} 人")
    c4.metric("预测容量利用率", pct(opt["capacity_utilization_rate"]))

    st.subheader("产品价格建议")
    view = result[[
        "product_name","baseline_price_cny","recommended_price_cny",
        "price_change_rate","baseline_predicted_orders","recommended_predicted_orders",
        "at_price_bound","capacity_constraint_status"
    ]].copy()
    view = view.rename(columns={
        "product_name":"产品",
        "baseline_price_cny":"基准价格（元）",
        "recommended_price_cny":"建议价格（元）",
        "price_change_rate":"价格变化率",
        "baseline_predicted_orders":"基准预测订单",
        "recommended_predicted_orders":"建议价格下预测订单",
        "at_price_bound":"是否触及价格边界",
        "capacity_constraint_status":"容量约束"
    })
    st.dataframe(view, width="stretch", hide_index=True)
    st.download_button(
        "下载定价建议 CSV", to_csv_bytes(view),
        file_name="smartprice_pricing_recommendations.csv", mime="text/csv"
    )

    if bool(result["at_price_bound"].all()):
        st.warning(
            "本次所有产品的建议价格均触及单次调整边界。"
            "这说明当前模型在给定价格范围内倾向于边界解，应进一步进行价格敏感性分析，"
            "不能直接将其作为真实园区调价指令。"
        )
    if summary["capacity_constraint_status"] != "PASS":
        st.error("本次优化未通过容量约束，请调整场景参数后重新运行。")
    else:
        st.success("求解器已成功运行，当前模拟方案满足设置的容量约束。")

    st.subheader("价格弹性参考")
    if not elasticity.empty:
        st.dataframe(
            elasticity[[
                "product_name","price_elasticity","p_value",
                "ci_95_lower","ci_95_upper","statistical_significance_5pct"
            ]].rename(columns={
                "product_name":"产品","price_elasticity":"价格弹性",
                "p_value":"p值","ci_95_lower":"95%置信区间下限",
                "ci_95_upper":"95%置信区间上限","statistical_significance_5pct":"5%水平显著"
            }),
            width="stretch", hide_index=True
        )
    st.caption("全部价格和收益均为模拟数据下的模型估计，不是实际成交结果或已验证的经营增益。")

def render_product_analysis(products, secondary):
    page_header("套餐及收益分析", "比较不同门票、组合套餐及二次消费业务的销售规模与贡献能力")
    if products.empty:
        st.warning("当前筛选范围没有产品数据。")
        return
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("产品净销售额")
        fig = px.bar(
            products.sort_values("net_sales_cny", ascending=True),
            x="net_sales_cny", y="product_name", orientation="h",
            labels={"net_sales_cny":"净销售额（元）","product_name":"产品"}
        )
        fig.update_layout(height=360, margin=dict(l=10,r=10,t=15,b=10))
        st.plotly_chart(fig, theme=None,width="stretch")
    with c2:
        st.subheader("产品贡献利润率")
        fig = px.bar(
            products.sort_values("contribution_margin_rate", ascending=True),
            x="contribution_margin_rate", y="product_name", orientation="h",
            labels={"contribution_margin_rate":"贡献利润率","product_name":"产品"}
        )
        fig.update_xaxes(tickformat=".0%")
        fig.update_layout(height=360, margin=dict(l=10,r=10,t=15,b=10))
        st.plotly_chart(fig, theme=None,width="stretch")

    st.subheader("产品经营明细")
    st.dataframe(products, width="stretch", hide_index=True)
    st.download_button(
        "下载产品收益分析 CSV", to_csv_bytes(products),
        file_name="smartprice_product_profitability.csv", mime="text/csv"
    )

    st.subheader("餐饮及周边二次消费")
    if not secondary.empty:
        fig = px.bar(
            secondary, x="consumption_category", y="net_sales_cny",
            color="consumption_category",
            labels={"consumption_category":"消费类别","net_sales_cny":"净销售额（元）"}
        )
        fig.update_layout(showlegend=False, height=300, margin=dict(l=10,r=10,t=15,b=10))
        st.plotly_chart(fig, theme=None,width="stretch")
        st.dataframe(secondary, width="stretch", hide_index=True)


def render_decision_assistant(daily, products, channels=None, secondary=None):
    page_header(
        "AI经营决策助手",
        "自然语言经营问答、月度经营报告与收入利润差异归因"
    )
    if daily is None or daily.empty:
        st.warning("当前日期筛选范围没有经营数据，请调整左侧日期筛选。")
        return

    try:
        elasticity, diagnostics = cached_elasticity()
    except Exception as exc:
        st.warning(f"价格弹性结果暂不可用：{exc}")
        elasticity = pd.DataFrame()

    cfg = llm_configuration()
    if cfg["enabled"]:
        st.success(f"外部AI模型已配置：{cfg['model']}。系统会将当前筛选范围的聚合经营数据发送至所配置的模型服务。")
    else:
        st.info(
            "当前运行在本地分析模式：无需API密钥，可使用经营问答、月度报告和差异归因。"
            "如需启用外部大模型，请按第五阶段说明配置环境变量。"
        )

    tabs = st.tabs(["自然语言经营问答", "月度经营报告", "业绩变化归因", "管理提示"])

    # Tab 1: business Q&A
    with tabs[0]:
        st.subheader("向 SmartPrice AI 提问")
        st.caption(
            "示例：本期收入是多少？哪个产品贡献利润最高？线上渠道表现如何？"
            "为什么2025年10月收入发生变化？儿童票价格弹性可靠吗？"
        )
        if "smartprice_ai_chat_history" not in st.session_state:
            st.session_state["smartprice_ai_chat_history"] = []

        q_col, clear_col = st.columns([5, 1])
        with clear_col:
            if st.button("清空对话", width="stretch"):
                st.session_state["smartprice_ai_chat_history"] = []
                st.rerun()

        question = st.chat_input("输入经营问题，例如：为什么本月收入下降？")
        if question:
            latest_month = pd.to_datetime(daily["date"]).dt.to_period("M").astype(str).max()
            result = answer_management_question(
                question=question,
                daily=daily,
                products=products,
                channels=channels,
                secondary=secondary,
                month=latest_month,
                elasticity=elasticity
            )
            st.session_state["smartprice_ai_chat_history"].append({
                "role": "user", "content": question
            })
            st.session_state["smartprice_ai_chat_history"].append({
                "role": "assistant",
                "content": result["answer"],
                "mode": result["mode"],
                "warning": result["warning"]
            })

        for message in st.session_state["smartprice_ai_chat_history"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message["role"] == "assistant":
                    mode_label = "外部大模型" if message.get("mode") == "external_llm" else "本地分析引擎"
                    st.caption(f"回答来源：{mode_label}")
                    if message.get("warning"):
                        st.caption(message["warning"])

    # Tab 2: monthly report
    with tabs[1]:
        st.subheader("自动生成月度经营分析报告")
        report_daily = daily.copy()
        report_daily["date"] = pd.to_datetime(report_daily["date"])
        available_months = sorted(report_daily["date"].dt.to_period("M").astype(str).unique().tolist())
        selected_report_month = st.selectbox(
            "选择报告月份", available_months,
            index=len(available_months)-1,
            key="smartprice_report_month"
        )
        if st.button("生成月度经营报告", type="primary", key="generate_monthly_report"):
            month_start = pd.Timestamp(selected_report_month + "-01")
            month_end = month_start + pd.offsets.MonthEnd(0)
            report_products = get_product_analysis(month_start.date(), month_end.date())
            report_channels = get_channel_analysis(month_start.date(), month_end.date())
            report_secondary = get_secondary_analysis(month_start.date(), month_end.date())
            report_text = build_monthly_report(
                report_daily, report_products, report_channels,
                report_secondary, selected_report_month, elasticity
            )
            st.session_state["smartprice_monthly_report"] = report_text
            st.session_state["smartprice_monthly_report_name"] = selected_report_month

        if st.session_state.get("smartprice_monthly_report"):
            report_name = st.session_state.get("smartprice_monthly_report_name", "monthly")
            st.markdown(st.session_state["smartprice_monthly_report"])
            st.download_button(
                "下载 Markdown 月度报告",
                data=st.session_state["smartprice_monthly_report"].encode("utf-8-sig"),
                file_name=f"SmartPrice_AI_{report_name}_Monthly_Report.md",
                mime="text/markdown",
                key="download_monthly_report"
            )
        else:
            st.caption("选择月份并点击生成，即可输出包含KPI、环比归因、产品、渠道和二次消费分析的报告。")

    # Tab 3: monthly variance attribution
    with tabs[2]:
        st.subheader("收入与贡献利润变化归因")
        variance_months = sorted(
            pd.to_datetime(daily["date"]).dt.to_period("M").astype(str).unique().tolist()
        )
        variance_month = st.selectbox(
            "选择需要分析的月份（与上月比较）",
            variance_months,
            index=len(variance_months)-1,
            key="smartprice_variance_month"
        )
        variance = explain_monthly_variance(daily, variance_month)
        if not variance.get("available"):
            st.warning(variance.get("message", "无法计算环比归因。"))
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                "收入环比变化",
                f"¥{variance['current']['total_revenue_cny']:,.0f}",
                f"{variance['revenue_delta']:+,.0f} 元"
            )
            c2.metric(
                "游客人数变化",
                f"{variance['current']['actual_visitors']:,.0f} 人",
                f"{variance['current']['actual_visitors']-variance['previous']['actual_visitors']:+,.0f} 人"
            )
            c3.metric(
                "人均收入变化",
                f"¥{variance['current']['revenue_per_visitor_cny']:,.2f}",
                f"{variance['current']['revenue_per_visitor_cny']-variance['previous']['revenue_per_visitor_cny']:+,.2f} 元"
            )
            c4.metric(
                "贡献利润变化",
                f"¥{variance['current']['contribution_profit_cny']:,.0f}",
                f"{variance['profit_delta']:+,.0f} 元"
            )

            st.markdown("#### 收入变化驱动因素")
            driver_frame = pd.DataFrame([
                {"驱动因素": "客流规模影响", "变化金额": variance["revenue_volume_effect"]},
                {"驱动因素": "游客人均收入影响", "变化金额": variance["revenue_spend_per_visitor_effect"]}
            ])
            fig = px.bar(
                driver_frame, x="驱动因素", y="变化金额", color="驱动因素",
                labels={"驱动因素":"收入驱动因素","变化金额":"对收入变化的影响（元）"}
            )
            fig.add_hline(y=0, line_dash="dash")
            fig.update_layout(showlegend=False, height=330, margin=dict(l=10,r=10,t=15,b=10))
            st.plotly_chart(fig, theme=None,width="stretch")

            st.markdown("#### 收入类别与成本变化")
            component_frame = get_monthly_variance_table(variance)
            st.dataframe(component_frame, width="stretch", hide_index=True)

            st.markdown("#### 归因结论")
            st.write(
                f"{variance_month} 相比 {variance['previous_month']}，综合经营收入变化 "
                f"¥{variance['revenue_delta']:+,.0f}。其中客流规模影响 "
                f"¥{variance['revenue_volume_effect']:+,.0f}，游客人均收入影响 "
                f"¥{variance['revenue_spend_per_visitor_effect']:+,.0f}。"
            )
            st.write(
                f"变动成本变化 ¥{variance['cost_delta']:+,.0f}，"
                f"因此贡献利润变化为 ¥{variance['profit_delta']:+,.0f}。"
            )
            st.caption(
                "分解采用 Revenue = Visitors × Revenue per Visitor 的顺序分解；"
                "贡献利润按收入减变动成本计算。均为模拟数据管理分析口径。"
            )

    # Tab 4: rule-based management prompts and model risk
    with tabs[3]:
        st.subheader("可解释经营提示")
        insights = build_decision_insights(daily, products, elasticity)
        for i, item in enumerate(insights, 1):
            st.markdown(f"**管理提示 {i}**")
            st.write(item)
            st.divider()

        if not elasticity.empty:
            st.subheader("价格弹性模型风险")
            nonsig = elasticity.loc[~elasticity["statistical_significance_5pct"], "product_name"].tolist()
            if nonsig:
                st.warning(
                    "以下产品的价格系数未达到5%显著性水平：" +
                    "、".join(nonsig) +
                    "。当前数据不支持对这些产品进行仅依赖模型系数的自动调价。"
                )
            else:
                st.info("本次模拟回归中产品价格系数均达到5%显著性水平，但仍需真实价格实验验证。")
        st.caption("管理提示由可解释规则生成；外部大模型仅在配置后用于自然语言问答，不自动执行任何调价操作。")

def main():
    st.sidebar.markdown("## 🎡 SmartPrice AI")
    st.sidebar.caption("主题乐园经营分析与智能定价平台")
    page = st.sidebar.radio(
        "功能导航",
        [
            "经营管理驾驶舱",
            "经营数据分析",
            "客流需求预测",
            "AI智能定价中心",
            "套餐及收益分析",
            "经营决策助手"
        ]
    )
    st.sidebar.divider()
    tables = cached_tables()
    date_values = pd.to_datetime(tables["dim_date"]["date"])
    min_date, max_date = date_values.min().date(), date_values.max().date()
    st.sidebar.markdown("### 数据筛选")
    selected_range = st.sidebar.date_input(
        "经营日期范围",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    elif isinstance(selected_range, tuple) and len(selected_range) == 1:
        start_date, end_date = selected_range[0], selected_range[0]
    else:
        start_date = end_date = selected_range
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    st.sidebar.divider()
    st.sidebar.caption("数据期间：2025-01-01 至 2025-12-31")
    st.sidebar.caption("数据性质：模拟经营数据")
    st.sidebar.caption("版本：MVP 0.5.0")

    if page == "客流需求预测":
        render_forecast()
        return
    if page == "AI智能定价中心":
        render_pricing(tables)
        return

    daily, products, channels, secondary = get_filtered_frames(start_date, end_date)
    if page == "经营管理驾驶舱":
        render_overview(daily, products, channels)
    elif page == "经营数据分析":
        render_business_analysis(daily, products, channels, secondary)
    elif page == "套餐及收益分析":
        render_product_analysis(products, secondary)
    elif page == "经营决策助手":
        render_decision_assistant(daily, products, channels, secondary)

if __name__ == "__main__":
    main()
