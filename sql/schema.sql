
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
