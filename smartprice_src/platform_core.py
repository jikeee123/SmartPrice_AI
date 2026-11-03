"""Validation, audit persistence and deterministic tool routing."""
import json, sqlite3, uuid, math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from .data_access import DB_PATH, load_core_data

VERSION = "1.0.0"
def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=lambda x: x.item() if hasattr(x,'item') else str(x), allow_nan=False)

def validate_platform(db_path=None):
    errors=[]
    try:
        with sqlite3.connect(db_path or DB_PATH,factory=ClosingConnection) as c:
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok': errors.append('数据库完整性异常')
            if c.execute('PRAGMA foreign_key_check').fetchall(): errors.append('外键不一致')
        t=load_core_data(db_path)
        expected=pd.date_range('2025-01-01','2025-12-31').strftime('%Y-%m-%d').tolist()
        for name,df in t.items():
            if df.empty or df.isna().any().any(): errors.append(name+': 空表或缺失值')
            if 'date' in df and sorted(df.date.unique())!=expected: errors.append(name+': 日期不完整')
            nums=df.select_dtypes(include='number')
            nonnegative=[k for k in nums if k not in ['avg_temp_c']]
            if not np.isfinite(nums.to_numpy()).all() or (nums[nonnegative]<0).any().any(): errors.append(name+': 非法数值')
        s=t['fact_ticket_sales']; sec=t['fact_secondary_sales']; ops=t['fact_daily_operations']
        for label,diff in [('套餐分配',s.net_sales_cny-s.admission_revenue_cny-s.included_fnb_revenue_cny),
                           ('门票净额',s.net_sales_cny-s.gross_sales_cny+s.discount_amount_cny+s.refund_amount_cny),
                           ('二消净额',sec.net_sales_cny-sec.gross_sales_cny+sec.discount_amount_cny+sec.refund_amount_cny),
                           ('二消毛利',sec.gross_profit_cny-sec.net_sales_cny+sec.cogs_cny),
                           ('净订单',s.net_orders-s.orders_sold+s.refunded_orders)]:
            if diff.abs().max()>.03: errors.append(label+'勾稽失败')
        v=s.merge(t['dim_product'],on='product_id').assign(v=lambda d:d.net_orders*d.visitor_units_per_order).groupby('date').v.sum()
        if not np.allclose(v.reindex(ops.date),ops.actual_visitors): errors.append('逐日游客勾稽失败')
        if not np.allclose(ops.actual_visitors/ops.park_capacity,ops.capacity_utilization_rate,atol=.0001): errors.append('容量利用率不一致')
    except Exception as e: errors.append(str(e))
    return errors

def require_valid(db_path=None):
    errors=validate_platform(db_path)
    if errors: raise ValueError('数据校验失败：'+'；'.join(errors))

def price_grid(base, low, high, change=.1):
    if not all(math.isfinite(float(x)) for x in [base,low,high,change]) or base<=0 or low<=0 or high<low or not 0<=change<=1:
        raise ValueError('价格或调价约束无效')
    lo=math.ceil(max(low,base*(1-change))/5)*5
    hi=math.floor(min(high,base*(1+change))/5)*5
    if lo>hi: raise ValueError('价格边界内没有符合5元步长的价格')
    return list(range(lo,hi+1,5))

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()

def audit_connection(db_path=None):
    c=sqlite3.connect(db_path or DB_PATH, factory=ClosingConnection)
    c.execute("CREATE TABLE IF NOT EXISTS platform_run(run_id TEXT PRIMARY KEY, kind TEXT, created_at TEXT, version TEXT, parameters_json TEXT, result_json TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS approval_event(event_id TEXT PRIMARY KEY, run_id TEXT REFERENCES platform_run(run_id), created_at TEXT, action TEXT, operator TEXT, comment TEXT, before_json TEXT, after_json TEXT)")
    c.execute('PRAGMA foreign_keys=ON')
    return c

def save_run(kind, parameters, result, db_path=None, training_period=None):
    rid=uuid.uuid4().hex
    if training_period is None:
        training_period=('2025-01-01','2025-12-31') if kind=='pricing' else (None,None)
    with audit_connection(db_path) as c:
        c.execute('INSERT INTO platform_run VALUES(?,?,?,?,?,?)',(rid,kind,datetime.now(timezone.utc).isoformat(),VERSION,dumps(parameters),dumps(result)))
        # Mirror model identity in the supplied project's canonical table.
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='model_run'").fetchone():
            c.execute('INSERT INTO model_run VALUES(?,?,?,?,?,?,?,?)',(rid,'SmartPrice '+kind,VERSION,kind,training_period[0],training_period[1],datetime.now(timezone.utc).isoformat(),dumps(parameters)))
    return rid

def read_runs(db_path=None):
    with audit_connection(db_path) as c: return pd.read_sql_query('SELECT * FROM platform_run ORDER BY created_at DESC',c)

def approve_run(rid, action, operator, comment, revised=None, db_path=None):
    if not operator.strip() or action not in ['采纳','修改','拒绝']: raise ValueError('请填写操作者并选择有效审批动作')
    with audit_connection(db_path) as c:
        row=c.execute('SELECT kind,parameters_json,result_json FROM platform_run WHERE run_id=?',(rid,)).fetchone()
        if not row: raise ValueError('运行记录不存在')
        effective=c.execute("SELECT after_json FROM approval_event WHERE run_id=? AND after_json IS NOT NULL AND after_json!='null' ORDER BY created_at DESC LIMIT 1",(rid,)).fetchone()
        before=json.loads(effective[0] if effective else row[2]); after=None
        if action!='拒绝':
            if row[0]!='pricing': raise ValueError('只能审批定价运行')
            from .scenario_engine import pricing_scenarios
            params=json.loads(row[1]); params.pop('persist',None)
            after=pricing_scenarios(**params,manual_prices=revised if action=='修改' else before['prices'],persist=False,db_path=db_path)
            if action=='修改' and revised is None: raise ValueError('修改时必须提供新价格')
            if not after['feasible']: raise ValueError('价格未满足约束，无法采纳')
        c.execute('INSERT INTO approval_event VALUES(?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,rid,datetime.now(timezone.utc).isoformat(),action,operator.strip(),comment,dumps(before),dumps(after)))
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='pricing_recommendation'").fetchone():
            c.execute('UPDATE pricing_recommendation SET approval_status=? WHERE run_id=?',(action,rid))
            if after:
                for pid,price in after['prices'].items():
                    result=next(x for x in after['candidates'] if x['product_id']==pid and x['price']==price)
                    c.execute('UPDATE pricing_recommendation SET recommended_price_cny=?,predicted_orders=?,predicted_product_revenue_cny=?,predicted_capacity_utilization_rate=? WHERE run_id=? AND product_id=?',(price,result['orders'],result['ticket_revenue']+result['package_revenue'],after['scenarios'][-1]['capacity_utilization'],rid,pid))
    return after

def route_question(question):
    if any(x in question for x in ['票价','定价','策略','价格调整']): return ['get_market_alerts','forecast_demand','calculate_elasticity','optimize_pricing','compare_scenarios']
    if any(x in question for x in ['预测','下周','明天','未来','下雨']): return ['get_market_alerts','forecast_demand']
    if any(x in question for x in ['竞品','预警','天气']): return ['get_market_alerts']
    if any(x in question for x in ['弹性']): return ['calculate_elasticity']
    if any(x in question for x in ['报告']): return ['get_business_kpi','generate_business_report']
    if any(x in question for x in ['经营','收入','利润','产品','渠道','餐饮','周边','归因','客流']): return ['get_business_kpi']
    return []
