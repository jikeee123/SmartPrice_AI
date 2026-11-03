from pathlib import Path
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "database" / "smartprice_ai.db"

class DatabaseConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try: return super().__exit__(*args)
        finally: self.close()

def get_connection(db_path=None):
    path = Path(db_path) if db_path else DB_PATH
    if not path.exists():
        raise FileNotFoundError(f"SQLite database not found: {path}")
    conn = sqlite3.connect(path,factory=DatabaseConnection)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def read_table(table_name, db_path=None):
    allowed = {
        "dim_date", "dim_product", "fact_daily_context", "fact_daily_operations",
        "fact_ticket_sales", "fact_secondary_sales", "fact_competitor_price"
    }
    if table_name not in allowed:
        raise ValueError(f"Table not allowed: {table_name}")
    with get_connection(db_path) as conn:
        return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

def load_core_data(db_path=None):
    names = [
        "dim_date", "dim_product", "fact_daily_context", "fact_daily_operations",
        "fact_ticket_sales", "fact_secondary_sales", "fact_competitor_price"
    ]
    return {name: read_table(name, db_path) for name in names}

def load_daily_product_features(db_path=None):
    tables = load_core_data(db_path)
    ticket = tables["fact_ticket_sales"].copy()
    ticket["date"] = pd.to_datetime(ticket["date"])
    ticket_agg = ticket.groupby(["date", "product_id"], as_index=False).agg(
        net_orders=("net_orders", "sum"),
        net_sales_cny=("net_sales_cny", "sum"),
        list_unit_price_cny=("list_unit_price_cny", "mean"),
        price_test_flag=("price_test_flag", "max"),
        ticket_variable_cost_cny=("ticket_variable_cost_cny", "sum"),
        admission_revenue_cny=("admission_revenue_cny", "sum"),
        included_fnb_revenue_cny=("included_fnb_revenue_cny", "sum"),
    )
    context = tables["fact_daily_context"].copy()
    context["date"] = pd.to_datetime(context["date"])
    calendar = tables["dim_date"].copy()
    calendar["date"] = pd.to_datetime(calendar["date"])
    competitor = tables["fact_competitor_price"].copy()
    competitor["date"] = pd.to_datetime(competitor["date"])
    competitor_agg = competitor.groupby("date", as_index=False).agg(
        competitor_price_cny=("competitor_price_cny", "mean")
    )
    features = ticket_agg.merge(context, on="date", how="left")
    features = features.merge(calendar, on="date", how="left")
    features = features.merge(competitor_agg, on="date", how="left")
    features = features.merge(tables["dim_product"], on="product_id", how="left")
    return features.sort_values(["product_id", "date"]).reset_index(drop=True)

def load_daily_operating_frame(db_path=None):
    tables = load_core_data(db_path)
    ops = tables["fact_daily_operations"].copy()
    ops["date"] = pd.to_datetime(ops["date"])
    context = tables["fact_daily_context"].copy()
    context["date"] = pd.to_datetime(context["date"])
    calendar = tables["dim_date"].copy()
    calendar["date"] = pd.to_datetime(calendar["date"])
    competitor = tables["fact_competitor_price"].copy()
    competitor["date"] = pd.to_datetime(competitor["date"])
    competitor_agg = competitor.groupby("date", as_index=False).agg(
        competitor_price_cny=("competitor_price_cny", "mean")
    )
    frame = ops.merge(context, on="date", how="left")
    frame = frame.merge(calendar, on="date", how="left")
    frame = frame.merge(competitor_agg, on="date", how="left")
    return frame.sort_values("date").reset_index(drop=True)
