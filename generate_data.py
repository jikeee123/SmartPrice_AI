from pathlib import Path
import json
import sqlite3
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
DB_DIR = ROOT / "data" / "database"
REPORT_DIR = ROOT / "reports"
SEED = 20261102
YEAR = 2025
CHANNELS = ["online", "onsite", "ota"]

PRODUCTS = [
    {"product_id": "T_ADULT", "product_name": "成人日间票", "product_category": "single_ticket",
     "customer_segment": "adult", "base_price_cny": 220, "min_price_cny": 160, "max_price_cny": 320,
     "visitor_units_per_order": 1, "admission_revenue_share": 1.0, "included_fnb_revenue_share": 0.0,
     "unit_variable_cost_cny": 18, "is_active": 1, "base_daily_orders": 600, "elasticity": -1.25},
    {"product_id": "T_CHILD", "product_name": "儿童日间票", "product_category": "single_ticket",
     "customer_segment": "child", "base_price_cny": 150, "min_price_cny": 110, "max_price_cny": 230,
     "visitor_units_per_order": 1, "admission_revenue_share": 1.0, "included_fnb_revenue_share": 0.0,
     "unit_variable_cost_cny": 14, "is_active": 1, "base_daily_orders": 190, "elasticity": -1.15},
    {"product_id": "T_NIGHT", "product_name": "夜场票", "product_category": "single_ticket",
     "customer_segment": "all", "base_price_cny": 120, "min_price_cny": 80, "max_price_cny": 190,
     "visitor_units_per_order": 1, "admission_revenue_share": 1.0, "included_fnb_revenue_share": 0.0,
     "unit_variable_cost_cny": 12, "is_active": 1, "base_daily_orders": 120, "elasticity": -1.40},
    {"product_id": "P_FAMILY", "product_name": "家庭组合票", "product_category": "package",
     "customer_segment": "family", "base_price_cny": 560, "min_price_cny": 430, "max_price_cny": 760,
     "visitor_units_per_order": 3, "admission_revenue_share": 1.0, "included_fnb_revenue_share": 0.0,
     "unit_variable_cost_cny": 48, "is_active": 1, "base_daily_orders": 90, "elasticity": -1.10},
    {"product_id": "P_MEAL", "product_name": "门票餐饮组合套餐", "product_category": "package",
     "customer_segment": "all", "base_price_cny": 280, "min_price_cny": 220, "max_price_cny": 390,
     "visitor_units_per_order": 1, "admission_revenue_share": 0.85, "included_fnb_revenue_share": 0.15,
     "unit_variable_cost_cny": 62, "is_active": 1, "base_daily_orders": 100, "elasticity": -1.30},
    {"product_id": "P_RAINY", "product_name": "雨天室内优先套餐", "product_category": "package",
     "customer_segment": "all", "base_price_cny": 240, "min_price_cny": 190, "max_price_cny": 340,
     "visitor_units_per_order": 1, "admission_revenue_share": 0.90, "included_fnb_revenue_share": 0.10,
     "unit_variable_cost_cny": 30, "is_active": 1, "base_daily_orders": 40, "elasticity": -1.50},
]

HOLIDAYS = [
    ("2025-01-01", "2025-01-01", "元旦"),
    ("2025-01-28", "2025-02-04", "春节"),
    ("2025-04-04", "2025-04-06", "清明节"),
    ("2025-05-01", "2025-05-05", "劳动节"),
    ("2025-05-31", "2025-06-02", "端午节"),
    ("2025-10-01", "2025-10-08", "国庆节/中秋节"),
]

MONTH_SEASON_FACTOR = {
    1: 0.78, 2: 0.82, 3: 0.92, 4: 1.00, 5: 1.08, 6: 1.12,
    7: 1.25, 8: 1.22, 9: 1.04, 10: 1.28, 11: 0.90, 12: 0.82
}
MONTH_TEMP_MEAN = {
    1: 2, 2: 4, 3: 10, 4: 17, 5: 23, 6: 27,
    7: 30, 8: 29, 9: 24, 10: 17, 11: 9, 12: 3
}
MONTH_RAIN_PROB = {
    1: 0.12, 2: 0.15, 3: 0.18, 4: 0.22, 5: 0.28, 6: 0.34,
    7: 0.38, 8: 0.36, 9: 0.27, 10: 0.19, 11: 0.15, 12: 0.12
}

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_date (
    date TEXT PRIMARY KEY,
    weekday_num INTEGER NOT NULL,
    weekday_name TEXT NOT NULL,
    month_num INTEGER NOT NULL,
    quarter_num INTEGER NOT NULL,
    is_weekend INTEGER NOT NULL,
    is_holiday INTEGER NOT NULL,
    holiday_name TEXT NOT NULL,
    is_school_vacation INTEGER NOT NULL,
    season TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    product_category TEXT NOT NULL,
    customer_segment TEXT NOT NULL,
    base_price_cny REAL NOT NULL,
    min_price_cny REAL NOT NULL,
    max_price_cny REAL NOT NULL,
    visitor_units_per_order INTEGER NOT NULL,
    admission_revenue_share REAL NOT NULL,
    included_fnb_revenue_share REAL NOT NULL,
    unit_variable_cost_cny REAL NOT NULL,
    is_active INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_daily_context (
    date TEXT PRIMARY KEY,
    avg_temp_c REAL NOT NULL,
    precipitation_mm REAL NOT NULL,
    weather_type TEXT NOT NULL,
    marketing_campaign_flag INTEGER NOT NULL,
    special_event_flag INTEGER NOT NULL,
    planned_open_hours REAL NOT NULL,
    FOREIGN KEY (date) REFERENCES dim_date(date)
);

CREATE TABLE IF NOT EXISTS fact_daily_operations (
    date TEXT PRIMARY KEY,
    actual_visitors INTEGER NOT NULL,
    park_capacity INTEGER NOT NULL,
    capacity_utilization_rate REAL NOT NULL,
    avg_queue_wait_min REAL NOT NULL,
    actual_open_hours REAL NOT NULL,
    FOREIGN KEY (date) REFERENCES dim_date(date)
);

CREATE TABLE IF NOT EXISTS fact_ticket_sales (
    date TEXT NOT NULL,
    product_id TEXT NOT NULL,
    sales_channel TEXT NOT NULL,
    list_unit_price_cny REAL NOT NULL,
    orders_sold INTEGER NOT NULL,
    refunded_orders INTEGER NOT NULL,
    net_orders INTEGER NOT NULL,
    discount_amount_cny REAL NOT NULL,
    refund_amount_cny REAL NOT NULL,
    gross_sales_cny REAL NOT NULL,
    net_sales_cny REAL NOT NULL,
    realized_unit_price_cny REAL NOT NULL,
    admission_revenue_cny REAL NOT NULL,
    included_fnb_revenue_cny REAL NOT NULL,
    ticket_variable_cost_cny REAL NOT NULL,
    price_test_flag INTEGER NOT NULL,
    PRIMARY KEY (date, product_id, sales_channel),
    FOREIGN KEY (date) REFERENCES dim_date(date),
    FOREIGN KEY (product_id) REFERENCES dim_product(product_id)
);

CREATE TABLE IF NOT EXISTS fact_secondary_sales (
    date TEXT NOT NULL,
    consumption_category TEXT NOT NULL,
    sales_channel TEXT NOT NULL,
    transaction_count INTEGER NOT NULL,
    gross_sales_cny REAL NOT NULL,
    discount_amount_cny REAL NOT NULL,
    refund_amount_cny REAL NOT NULL,
    net_sales_cny REAL NOT NULL,
    cogs_cny REAL NOT NULL,
    gross_profit_cny REAL NOT NULL,
    PRIMARY KEY (date, consumption_category, sales_channel),
    FOREIGN KEY (date) REFERENCES dim_date(date)
);

CREATE TABLE IF NOT EXISTS fact_competitor_price (
    date TEXT NOT NULL,
    competitor_id TEXT NOT NULL,
    competitor_name TEXT NOT NULL,
    comparable_product TEXT NOT NULL,
    competitor_price_cny REAL NOT NULL,
    observation_type TEXT NOT NULL,
    PRIMARY KEY (date, competitor_id),
    FOREIGN KEY (date) REFERENCES dim_date(date)
);

CREATE TABLE IF NOT EXISTS model_run (
    run_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    run_type TEXT NOT NULL,
    training_start_date TEXT,
    training_end_date TEXT,
    created_at TEXT NOT NULL,
    parameters_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_result (
    run_id TEXT NOT NULL,
    forecast_date TEXT NOT NULL,
    product_id TEXT NOT NULL,
    predicted_orders REAL NOT NULL,
    lower_bound_orders REAL NOT NULL,
    upper_bound_orders REAL NOT NULL,
    predicted_visitors REAL NOT NULL,
    model_version TEXT NOT NULL,
    PRIMARY KEY (run_id, forecast_date, product_id),
    FOREIGN KEY (run_id) REFERENCES model_run(run_id),
    FOREIGN KEY (product_id) REFERENCES dim_product(product_id)
);

CREATE TABLE IF NOT EXISTS pricing_recommendation (
    recommendation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    target_date TEXT NOT NULL,
    product_id TEXT NOT NULL,
    baseline_price_cny REAL NOT NULL,
    recommended_price_cny REAL NOT NULL,
    predicted_orders REAL NOT NULL,
    predicted_product_revenue_cny REAL NOT NULL,
    predicted_capacity_utilization_rate REAL NOT NULL,
    objective_type TEXT NOT NULL,
    constraint_status TEXT NOT NULL,
    reason_summary TEXT NOT NULL,
    approval_status TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES model_run(run_id),
    FOREIGN KEY (product_id) REFERENCES dim_product(product_id)
);

CREATE TABLE IF NOT EXISTS scenario_result (
    scenario_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    scenario_name TEXT NOT NULL,
    target_date TEXT NOT NULL,
    pricing_strategy TEXT NOT NULL,
    standalone_ticket_revenue_cny REAL NOT NULL,
    package_revenue_cny REAL NOT NULL,
    addon_fnb_revenue_cny REAL NOT NULL,
    merchandise_revenue_cny REAL NOT NULL,
    total_revenue_cny REAL NOT NULL,
    contribution_profit_cny REAL NOT NULL,
    predicted_visitors REAL NOT NULL,
    predicted_capacity_utilization_rate REAL NOT NULL,
    predicted_avg_queue_wait_min REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES model_run(run_id)
);

CREATE INDEX IF NOT EXISTS idx_ticket_sales_date ON fact_ticket_sales(date);
CREATE INDEX IF NOT EXISTS idx_ticket_sales_product ON fact_ticket_sales(product_id);
CREATE INDEX IF NOT EXISTS idx_secondary_sales_date ON fact_secondary_sales(date);
CREATE INDEX IF NOT EXISTS idx_competitor_date ON fact_competitor_price(date);
"""

def get_holiday(date_value):
    for start, end, name in HOLIDAYS:
        if pd.Timestamp(start) <= date_value <= pd.Timestamp(end):
            return name
    return ""

def get_season(month):
    if month in (3, 4, 5):
        return "春"
    if month in (6, 7, 8):
        return "夏"
    if month in (9, 10, 11):
        return "秋"
    return "冬"

def build_calendar():
    dates = pd.date_range(f"{YEAR}-01-01", f"{YEAR}-12-31", freq="D")
    weekday_names = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    rows = []
    for d in dates:
        holiday_name = get_holiday(d)
        is_school_vacation = (
            pd.Timestamp("2025-01-15") <= d <= pd.Timestamp("2025-02-16")
            or pd.Timestamp("2025-07-01") <= d <= pd.Timestamp("2025-08-31")
        )
        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "weekday_num": int(d.weekday()) + 1,
            "weekday_name": weekday_names[int(d.weekday())],
            "month_num": int(d.month),
            "quarter_num": int(d.quarter),
            "is_weekend": int(d.weekday() >= 5),
            "is_holiday": int(bool(holiday_name)),
            "holiday_name": holiday_name,
            "is_school_vacation": int(is_school_vacation),
            "season": get_season(int(d.month)),
        })
    return pd.DataFrame(rows), dates

def build_context(calendar, dates, rng):
    rows = []
    for d in dates:
        month = int(d.month)
        temp = float(rng.normal(MONTH_TEMP_MEAN[month], 4.5))
        rain_flag = rng.random() < MONTH_RAIN_PROB[month]
        snow_flag = (temp < 1 and rain_flag and rng.random() < 0.35)
        if snow_flag:
            weather = "雪"
            precipitation = float(rng.gamma(1.8, 2.5))
        elif rain_flag:
            weather = "雨"
            precipitation = float(rng.gamma(2.0, 4.5))
        elif rng.random() < 0.34:
            weather = "多云"
            precipitation = 0.0
        else:
            weather = "晴"
            precipitation = 0.0
        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "avg_temp_c": round(temp, 1),
            "precipitation_mm": round(precipitation, 1),
            "weather_type": weather,
            "marketing_campaign_flag": int(rng.random() < 0.07),
            "special_event_flag": int(rng.random() < 0.035),
            "planned_open_hours": 8.5 if month in (1, 2, 11, 12) else 10.0,
        })
    return pd.DataFrame(rows)

def build_competitor_prices(calendar, context, dates, rng):
    context_by_date = context.set_index("date").to_dict("index")
    calendar_by_date = calendar.set_index("date").to_dict("index")
    rows = []
    competitors = [
        ("COMP_A", "星河欢乐世界（模拟）", 215.0),
        ("COMP_B", "奇幻乐园（模拟）", 235.0),
    ]
    for d in dates:
        ds = d.strftime("%Y-%m-%d")
        cal = calendar_by_date[ds]
        ctx = context_by_date[ds]
        for competitor_id, competitor_name, base_price in competitors:
            multiplier = 1.0 + 0.025 * cal["is_weekend"] + 0.045 * cal["is_holiday"]
            multiplier += 0.015 * cal["is_school_vacation"]
            if ctx["weather_type"] == "雨":
                multiplier -= 0.025
            multiplier *= float(rng.normal(1.0, 0.025))
            price = round(base_price * multiplier / 5) * 5
            rows.append({
                "date": ds,
                "competitor_id": competitor_id,
                "competitor_name": competitor_name,
                "comparable_product": "成人日间票",
                "competitor_price_cny": float(max(150, price)),
                "observation_type": "synthetic",
            })
    return pd.DataFrame(rows)

def build_sales_and_operations(calendar, context, products_df, dates, rng):
    calendar_by_date = calendar.set_index("date").to_dict("index")
    context_by_date = context.set_index("date").to_dict("index")
    product_rows = products_df.to_dict("records")
    ticket_rows = []
    operation_rows = []

    channel_base = np.array([0.55, 0.22, 0.23], dtype=float)
    channel_discount = {"online": 0.025, "onsite": 0.005, "ota": 0.070}
    channel_refund = {"online": 0.012, "onsite": 0.004, "ota": 0.020}
    park_capacity = 5000

    for d in dates:
        ds = d.strftime("%Y-%m-%d")
        cal = calendar_by_date[ds]
        ctx = context_by_date[ds]
        month = int(d.month)

        weather_factor = {"晴": 1.04, "多云": 1.00, "雨": 0.72, "雪": 0.62}[ctx["weather_type"]]
        temp = ctx["avg_temp_c"]
        if temp > 34 or temp < 1:
            temp_factor = 0.86
        elif 18 <= temp <= 28:
            temp_factor = 1.04
        else:
            temp_factor = 1.0

        season_factor = MONTH_SEASON_FACTOR[month]
        weekend_factor = 1.34 if cal["is_weekend"] else 1.0
        holiday_factor = 1.58 if cal["is_holiday"] else 1.0
        school_factor = 1.16 if cal["is_school_vacation"] else 1.0
        marketing_factor = 1.10 if ctx["marketing_campaign_flag"] else 1.0
        event_factor = 1.14 if ctx["special_event_flag"] else 1.0

        if cal["is_holiday"]:
            channel_probs = np.array([0.49, 0.19, 0.32])
        elif ctx["weather_type"] == "雨":
            channel_probs = np.array([0.61, 0.19, 0.20])
        else:
            channel_probs = channel_base.copy()
        channel_probs = channel_probs / channel_probs.sum()

        daily_product_orders = {}
        daily_product_prices = {}
        daily_price_test = {}
        for p in product_rows:
            pid = p["product_id"]
            base_price = float(p["base_price_cny"])
            price_multiplier = 1.0 + 0.025 * cal["is_weekend"] + 0.045 * cal["is_holiday"]
            price_multiplier += 0.012 * cal["is_school_vacation"]
            price_multiplier += 0.018 * ctx["special_event_flag"]
            if ctx["weather_type"] == "雨":
                price_multiplier += 0.025 if pid == "P_RAINY" else -0.035
            test_flag = int(rng.random() < 0.25)
            if test_flag:
                price_multiplier *= float(rng.uniform(0.93, 1.07))
            raw_price = base_price * price_multiplier
            price = round(raw_price / 5) * 5
            price = float(min(max(price, p["min_price_cny"]), p["max_price_cny"]))
            daily_product_prices[pid] = price
            daily_price_test[pid] = test_flag

            product_weather_factor = weather_factor
            if pid == "P_RAINY" and ctx["weather_type"] == "雨":
                product_weather_factor = 1.35
            elif pid == "P_RAINY" and ctx["weather_type"] in ("晴", "多云"):
                product_weather_factor = 0.90

            price_ratio = max(price / base_price, 0.01)
            price_effect = price_ratio ** float(p["elasticity"])
            noise = float(rng.lognormal(mean=-0.5 * 0.12**2, sigma=0.12))
            expected_orders = (
                float(p["base_daily_orders"])
                * season_factor * weekend_factor * holiday_factor * school_factor
                * product_weather_factor * temp_factor * marketing_factor * event_factor
                * price_effect * noise
            )
            daily_product_orders[pid] = max(0, int(round(expected_orders)))

        estimated_visitors = sum(
            daily_product_orders[p["product_id"]] * int(p["visitor_units_per_order"])
            for p in product_rows
        )
        if estimated_visitors > park_capacity:
            scale = park_capacity / estimated_visitors
            daily_product_orders = {
                p["product_id"]: int(np.floor(daily_product_orders[p["product_id"]] * scale))
                for p in product_rows
            }

        daily_visitors = 0
        for p in product_rows:
            pid = p["product_id"]
            net_orders_total = int(daily_product_orders[pid])
            daily_visitors += net_orders_total * int(p["visitor_units_per_order"])
            channel_orders = rng.multinomial(net_orders_total, channel_probs)
            list_price = daily_product_prices[pid]
            for channel, net_orders in zip(CHANNELS, channel_orders):
                net_orders = int(net_orders)
                refund_rate = channel_refund[channel]
                refunded_orders = int(round(net_orders * refund_rate / (1.0 - refund_rate))) if net_orders else 0
                orders_sold = net_orders + refunded_orders
                discount_rate = channel_discount[channel]
                gross_sales = orders_sold * list_price
                discount_amount = gross_sales * discount_rate
                refund_amount = refunded_orders * list_price * (1.0 - discount_rate)
                net_sales = gross_sales - discount_amount - refund_amount
                realized_price = net_sales / net_orders if net_orders else 0.0
                admission_revenue = net_sales * float(p["admission_revenue_share"])
                included_fnb_revenue = net_sales * float(p["included_fnb_revenue_share"])
                ticket_variable_cost = net_orders * float(p["unit_variable_cost_cny"])
                ticket_rows.append({
                    "date": ds,
                    "product_id": pid,
                    "sales_channel": channel,
                    "list_unit_price_cny": round(list_price, 2),
                    "orders_sold": orders_sold,
                    "refunded_orders": refunded_orders,
                    "net_orders": net_orders,
                    "discount_amount_cny": round(discount_amount, 2),
                    "refund_amount_cny": round(refund_amount, 2),
                    "gross_sales_cny": round(gross_sales, 2),
                    "net_sales_cny": round(net_sales, 2),
                    "realized_unit_price_cny": round(realized_price, 2),
                    "admission_revenue_cny": round(admission_revenue, 2),
                    "included_fnb_revenue_cny": round(included_fnb_revenue, 2),
                    "ticket_variable_cost_cny": round(ticket_variable_cost, 2),
                    "price_test_flag": daily_price_test[pid],
                })

        utilization = daily_visitors / park_capacity
        queue_wait = max(4.0, 5.0 + 38.0 * (utilization ** 2) + float(rng.normal(0, 2.0)))
        actual_open_hours = float(ctx["planned_open_hours"])
        if ctx["weather_type"] == "雪":
            actual_open_hours = max(6.0, actual_open_hours - 0.5)
        operation_rows.append({
            "date": ds,
            "actual_visitors": int(daily_visitors),
            "park_capacity": park_capacity,
            "capacity_utilization_rate": round(utilization, 4),
            "avg_queue_wait_min": round(queue_wait, 1),
            "actual_open_hours": round(actual_open_hours, 1),
        })

    ticket_sales = pd.DataFrame(ticket_rows)
    operations = pd.DataFrame(operation_rows)
    return ticket_sales, operations

def build_secondary_sales(operations, dates, rng):
    rows = []
    for op in operations.to_dict("records"):
        ds = op["date"]
        visitors = int(op["actual_visitors"])
        for category in ("FNB", "MERCH"):
            if category == "FNB":
                attach_rate = float(rng.normal(0.54, 0.035))
                avg_basket = float(rng.normal(58, 6))
                cogs_rate = 0.36
            else:
                attach_rate = float(rng.normal(0.17, 0.025))
                avg_basket = float(rng.normal(88, 12))
                cogs_rate = 0.48
            attach_rate = min(max(attach_rate, 0.05), 0.85)
            total_transactions = max(0, int(round(visitors * attach_rate)))
            channel_probs = np.array([0.08, 0.87, 0.05])
            channel_counts = rng.multinomial(total_transactions, channel_probs)
            for channel, transactions in zip(CHANNELS, channel_counts):
                transactions = int(transactions)
                channel_discount = {"online": 0.035, "onsite": 0.010, "ota": 0.055}[channel]
                refund_rate = 0.006 if channel != "ota" else 0.010
                gross_sales = transactions * avg_basket
                discount_amount = gross_sales * channel_discount
                refund_amount = gross_sales * refund_rate
                net_sales = gross_sales - discount_amount - refund_amount
                cogs = net_sales * cogs_rate
                rows.append({
                    "date": ds,
                    "consumption_category": category,
                    "sales_channel": channel,
                    "transaction_count": transactions,
                    "gross_sales_cny": round(gross_sales, 2),
                    "discount_amount_cny": round(discount_amount, 2),
                    "refund_amount_cny": round(refund_amount, 2),
                    "net_sales_cny": round(net_sales, 2),
                    "cogs_cny": round(cogs, 2),
                    "gross_profit_cny": round(net_sales - cogs, 2),
                })
    return pd.DataFrame(rows)

def create_empty_model_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS model_run (
        run_id TEXT PRIMARY KEY, model_name TEXT NOT NULL, model_version TEXT NOT NULL,
        run_type TEXT NOT NULL, training_start_date TEXT, training_end_date TEXT,
        created_at TEXT NOT NULL, parameters_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS forecast_result (
        run_id TEXT NOT NULL, forecast_date TEXT NOT NULL, product_id TEXT NOT NULL,
        predicted_orders REAL NOT NULL, lower_bound_orders REAL NOT NULL,
        upper_bound_orders REAL NOT NULL, predicted_visitors REAL NOT NULL,
        model_version TEXT NOT NULL, PRIMARY KEY(run_id, forecast_date, product_id),
        FOREIGN KEY(run_id) REFERENCES model_run(run_id),
        FOREIGN KEY(product_id) REFERENCES dim_product(product_id)
    );
    CREATE TABLE IF NOT EXISTS pricing_recommendation (
        recommendation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, target_date TEXT NOT NULL,
        product_id TEXT NOT NULL, baseline_price_cny REAL NOT NULL,
        recommended_price_cny REAL NOT NULL, predicted_orders REAL NOT NULL,
        predicted_product_revenue_cny REAL NOT NULL,
        predicted_capacity_utilization_rate REAL NOT NULL, objective_type TEXT NOT NULL,
        constraint_status TEXT NOT NULL, reason_summary TEXT NOT NULL,
        approval_status TEXT NOT NULL, FOREIGN KEY(run_id) REFERENCES model_run(run_id),
        FOREIGN KEY(product_id) REFERENCES dim_product(product_id)
    );
    CREATE TABLE IF NOT EXISTS scenario_result (
        scenario_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, scenario_name TEXT NOT NULL,
        target_date TEXT NOT NULL, pricing_strategy TEXT NOT NULL,
        standalone_ticket_revenue_cny REAL NOT NULL, package_revenue_cny REAL NOT NULL,
        addon_fnb_revenue_cny REAL NOT NULL, merchandise_revenue_cny REAL NOT NULL,
        total_revenue_cny REAL NOT NULL, contribution_profit_cny REAL NOT NULL,
        predicted_visitors REAL NOT NULL, predicted_capacity_utilization_rate REAL NOT NULL,
        predicted_avg_queue_wait_min REAL NOT NULL,
        FOREIGN KEY(run_id) REFERENCES model_run(run_id)
    );
    """)

def make_quality_report(frames, products_df, db_path):
    expected = {
        "dim_date": 365,
        "dim_product": 6,
        "fact_daily_context": 365,
        "fact_daily_operations": 365,
        "fact_ticket_sales": 6570,
        "fact_secondary_sales": 2190,
        "fact_competitor_price": 730,
    }
    actual = {name: int(len(df)) for name, df in frames.items()}
    product_units = products_df.set_index("product_id")["visitor_units_per_order"].to_dict()
    ticket = frames["fact_ticket_sales"].copy()
    ticket["visitor_units_per_order"] = ticket["product_id"].map(product_units)
    visitor_rebuilt = (
        ticket.assign(visitor_calc=ticket["net_orders"] * ticket["visitor_units_per_order"])
        .groupby("date")["visitor_calc"].sum()
    )
    ops = frames["fact_daily_operations"].set_index("date")
    visitor_diff = int((visitor_rebuilt - ops["actual_visitors"]).abs().max())
    ticket = frames["fact_ticket_sales"]
    revenue_diff = float(
        (ticket["net_sales_cny"] -
         ticket["admission_revenue_cny"] -
         ticket["included_fnb_revenue_cny"]).abs().max()
    )
    secondary = frames["fact_secondary_sales"]
    secondary_revenue_diff = float(
        (secondary["net_sales_cny"] -
         (secondary["gross_sales_cny"] - secondary["discount_amount_cny"] - secondary["refund_amount_cny"])).abs().max()
    )
    capacity_exceed = int((ops["actual_visitors"] > ops["park_capacity"]).sum())
    duplicate_counts = {
        "dim_date": int(frames["dim_date"]["date"].duplicated().sum()),
        "dim_product": int(frames["dim_product"]["product_id"].duplicated().sum()),
        "fact_daily_context": int(frames["fact_daily_context"]["date"].duplicated().sum()),
        "fact_daily_operations": int(frames["fact_daily_operations"]["date"].duplicated().sum()),
        "fact_ticket_sales": int(frames["fact_ticket_sales"].duplicated(["date", "product_id", "sales_channel"]).sum()),
        "fact_secondary_sales": int(frames["fact_secondary_sales"].duplicated(["date", "consumption_category", "sales_channel"]).sum()),
        "fact_competitor_price": int(frames["fact_competitor_price"].duplicated(["date", "competitor_id"]).sum()),
    }
    product_ids = set(products_df["product_id"])
    foreign_key_errors = int((~ticket["product_id"].isin(product_ids)).sum())
    null_counts = {name: int(df.isna().sum().sum()) for name, df in frames.items()}
    all_counts_ok = all(actual[k] == expected[k] for k in expected)
    all_duplicates_ok = all(v == 0 for v in duplicate_counts.values())
    passed = (
        all_counts_ok and all_duplicates_ok and visitor_diff == 0
        and revenue_diff < 0.02 and secondary_revenue_diff < 0.02
        and capacity_exceed == 0 and foreign_key_errors == 0
        and all(v == 0 for v in null_counts.values())
    )
    return {
        "project": "SmartPrice AI",
        "dataset_period": ["2025-01-01", "2025-12-31"],
        "seed": SEED,
        "expected_row_counts": expected,
        "actual_row_counts": actual,
        "total_base_records": int(sum(actual.values())),
        "duplicate_key_counts": duplicate_counts,
        "null_value_counts": null_counts,
        "visitor_reconciliation_max_difference": visitor_diff,
        "ticket_revenue_allocation_max_difference_cny": round(revenue_diff, 4),
        "secondary_sales_reconciliation_max_difference_cny": round(secondary_revenue_diff, 4),
        "capacity_exceed_days": capacity_exceed,
        "unknown_product_foreign_key_rows": foreign_key_errors,
        "database_file": str(db_path.name),
        "status": "PASS" if passed else "CHECK_REQUIRED",
    }

def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    calendar, dates = build_calendar()
    context = build_context(calendar, dates, rng)

    product_columns = [
        "product_id", "product_name", "product_category", "customer_segment",
        "base_price_cny", "min_price_cny", "max_price_cny", "visitor_units_per_order",
        "admission_revenue_share", "included_fnb_revenue_share", "unit_variable_cost_cny", "is_active"
    ]
    products_full_df = pd.DataFrame(PRODUCTS)
    products_df = products_full_df[product_columns]

    competitor = build_competitor_prices(calendar, context, dates, rng)
    ticket_sales, operations = build_sales_and_operations(calendar, context, products_full_df, dates, rng)
    secondary_sales = build_secondary_sales(operations, dates, rng)

    frames = {
        "dim_date": calendar,
        "dim_product": products_df,
        "fact_daily_context": context,
        "fact_daily_operations": operations,
        "fact_ticket_sales": ticket_sales,
        "fact_secondary_sales": secondary_sales,
        "fact_competitor_price": competitor,
    }

    # Export CSV source files.
    for table_name, df in frames.items():
        df.to_csv(RAW_DIR / f"{table_name}.csv", index=False, encoding="utf-8-sig")

    # Create SQLite database with relational constraints.
    db_path = DB_DIR / "smartprice_ai.db"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA_SQL)
    for table_name, df in frames.items():
        df.to_sql(table_name, conn, if_exists="append", index=False)
    conn.commit()
    conn.close()

    # Save schema as a standalone SQL file.
    (ROOT / "sql" / "schema.sql").write_text(SCHEMA_SQL, encoding="utf-8")

    report = make_quality_report(frames, products_df, db_path)
    (REPORT_DIR / "data_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary_lines = [
        "# SmartPrice AI 数据生成摘要",
        "",
        f"- 数据周期：2025-01-01 至 2025-12-31",
        f"- 随机种子：{SEED}",
        f"- 基础记录总数：{report['total_base_records']:,}",
        f"- 数据库：data/database/{db_path.name}",
        f"- 数据质量状态：{report['status']}",
        "",
        "## 各表记录数",
        "",
        "| 数据表 | 记录数 |",
        "|---|---:|",
    ]
    for name, count in report["actual_row_counts"].items():
        summary_lines.append(f"| {name} | {count:,} |")
    summary_lines += [
        "",
        "## 关键校验",
        "",
        f"- 客流勾稽最大差异：{report['visitor_reconciliation_max_difference']} 人",
        f"- 套餐/门票收入分配最大差异：{report['ticket_revenue_allocation_max_difference_cny']} 元",
        f"- 二次消费收入勾稽最大差异：{report['secondary_sales_reconciliation_max_difference_cny']} 元",
        f"- 超容量天数：{report['capacity_exceed_days']}",
        "",
        "说明：全部数据为合成模拟数据，仅用于产品开发、算法验证和演示，不代表任何真实主题乐园。",
    ]
    (REPORT_DIR / "generation_summary.md").write_text("\n".join(summary_lines), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
