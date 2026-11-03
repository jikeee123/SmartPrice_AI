-- SmartPrice AI Stage 3: SQL analysis examples
-- All amounts are synthetic CNY values.
-- Important: total revenue = ticket/package net sales + add-on FNB + merchandise.
-- Do not add allocated admission/FNB split fields again; they are allocation views of ticket/package net sales.

-- 1. Daily total revenue and visitor count
SELECT
    o.date,
    o.actual_visitors,
    SUM(t.net_sales_cny) AS ticket_package_revenue_cny,
    COALESCE(s.addon_fnb_revenue_cny, 0) AS addon_fnb_revenue_cny,
    COALESCE(s.merchandise_revenue_cny, 0) AS merchandise_revenue_cny,
    SUM(t.net_sales_cny)
      + COALESCE(s.addon_fnb_revenue_cny, 0)
      + COALESCE(s.merchandise_revenue_cny, 0) AS total_revenue_cny
FROM fact_daily_operations o
JOIN fact_ticket_sales t ON o.date = t.date
LEFT JOIN (
    SELECT
        date,
        SUM(CASE WHEN consumption_category = 'FNB' THEN net_sales_cny ELSE 0 END) AS addon_fnb_revenue_cny,
        SUM(CASE WHEN consumption_category = 'MERCH' THEN net_sales_cny ELSE 0 END) AS merchandise_revenue_cny
    FROM fact_secondary_sales
    GROUP BY date
) s ON o.date = s.date
GROUP BY o.date, o.actual_visitors, s.addon_fnb_revenue_cny, s.merchandise_revenue_cny
ORDER BY o.date;

-- 2. Product revenue and contribution profit (ticket/package product level)
SELECT
    p.product_id,
    p.product_name,
    SUM(t.net_orders) AS net_orders,
    SUM(t.net_sales_cny) AS net_sales_cny,
    SUM(t.ticket_variable_cost_cny) AS ticket_variable_cost_cny,
    SUM(t.net_sales_cny) - SUM(t.ticket_variable_cost_cny) AS contribution_profit_cny
FROM fact_ticket_sales t
JOIN dim_product p ON t.product_id = p.product_id
GROUP BY p.product_id, p.product_name
ORDER BY net_sales_cny DESC;

-- 3. Monthly operating revenue
SELECT
    substr(o.date, 1, 7) AS month,
    SUM(t.net_sales_cny) AS ticket_package_revenue_cny,
    SUM(o.actual_visitors) AS actual_visitors
FROM fact_daily_operations o
JOIN fact_ticket_sales t ON o.date = t.date
GROUP BY substr(o.date, 1, 7)
ORDER BY month;

-- 4. Competitor price comparison
SELECT
    date,
    AVG(competitor_price_cny) AS avg_competitor_price_cny
FROM fact_competitor_price
GROUP BY date
ORDER BY date;
