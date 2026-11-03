"""Shared scenario inputs, calibrated recursive forecasting and discrete pricing."""
from functools import lru_cache
import math
import numpy as np
import pandas as pd
from scipy.optimize import milp, Bounds, LinearConstraint
from sklearn.ensemble import RandomForestRegressor
from .data_access import load_core_data, load_daily_operating_frame, ROOT
from .elasticity import fit_price_elasticity_models, predict_product_orders
from .platform_core import require_valid, price_grid, save_run, dumps

DEFAULT_SCENARIO={'weather_type':'雨','avg_temp_c':20.,'precipitation_mm':15.,'competitor_price_cny':240.,'is_holiday':0,'is_school_vacation':0,'marketing_campaign_flag':0,'special_event_flag':0,'planned_open_hours':10.}

def scenario_values(scenario=None):
    s={**DEFAULT_SCENARIO,**(scenario or {})}
    t=load_core_data()
    s['weather_type']={'Rainy':'雨','Sunny':'晴','Cloudy':'多云','Snowy':'雪'}.get(s['weather_type'],s['weather_type'])
    if s['weather_type'] not in t['fact_daily_context'].weather_type.unique(): raise ValueError('未知天气类型')
    for k in DEFAULT_SCENARIO:
        if k=='weather_type': continue
        s[k]=float(s[k])
        if not math.isfinite(s[k]): raise ValueError('情景数值必须有限')
    if s['precipitation_mm']<0 or s['competitor_price_cny']<=0 or s['planned_open_hours']<=0: raise ValueError('情景参数无效')
    for k in ['is_holiday','is_school_vacation','marketing_campaign_flag','special_event_flag']:
        if s[k] not in [0,1]: raise ValueError('标志必须为0或1')
    return s

@lru_cache(maxsize=4)
def pricing_models(db_path=None):
    return fit_price_elasticity_models(db_path)

def market_alerts(scenario=None,capacity_utilization=None):
    s=scenario_values(scenario); out=[]
    if s['precipitation_mm']>=10: out.append('降雨情景：关注需求下降与室内套餐分流。')
    if s['is_holiday']: out.append('节假日情景：关注高峰容量与排队。')
    ref=float(load_core_data()['fact_competitor_price'].competitor_price_cny.mean())
    if abs(s['competitor_price_cny']/ref-1)>=.1: out.append('竞品情景价格偏离历史均值超过10%。')
    if capacity_utilization is not None and capacity_utilization>=.85: out.append('容量达到85%预警线：建议限流、分时入园和套餐分流。')
    return out or ['当前情景未触发管理预警。']

def pricing_scenarios(target_date='2026-01-01',scenario=None,objective='revenue',capacity_rate=.85,max_change=.1,price_bounds=None,manual_prices=None,persist=True,db_path=None):
    require_valid(db_path)
    date=pd.Timestamp(target_date)
    if pd.isna(date) or objective not in ['revenue','profit'] or not 0<capacity_rate<=1: raise ValueError('日期、目标或容量约束无效')
    s=scenario_values(scenario); s.update(month_num=date.month,is_weekend=int(date.weekday()>=5))
    t=load_core_data(db_path); products=t['dim_product']; ticket=t['fact_ticket_sales']; sec=t['fact_secondary_sales']; ops=t['fact_daily_operations']
    elasticity,models,_,features=pricing_models(str(db_path) if db_path else None)
    pids=products.product_id.tolist(); capacity=float(ops.park_capacity.iloc[-1])
    visitors=float(ops.actual_visitors.sum())
    spend=sec.groupby('consumption_category')[['net_sales_cny','cogs_cny']].sum()/visitors
    # Categories are read from source values; F&B is all categories except merchandise.
    merch_keys=[k for k in spend.index if 'merch' in str(k).lower() or '周边' in str(k)]
    merch=float(spend.loc[merch_keys,'net_sales_cny'].sum()); fnb=float(spend.net_sales_cny.sum()-merch)
    secondary_cost=float(spend.cogs_cny.sum())
    grids={}; rows=[]
    for p in products.to_dict('records'):
        pid=p['product_id']; base=float(p['base_price_cny'])
        bounds=(price_bounds or {}).get(pid,[p['min_price_cny'],p['max_price_cny']])
        lo=max(float(bounds[0]),float(p['min_price_cny'])); hi=min(float(bounds[1]),float(p['max_price_cny']))
        grids[pid]=price_grid(base,lo,hi,max_change)
        row=features[features.product_id==pid].iloc[-1].to_dict(); row.update(s)
        part=ticket[ticket.product_id==pid]
        factor=float(part.net_sales_cny.sum()/(part.net_orders*part.list_unit_price_cny).sum())
        for price in grids[pid]:
            q=predict_product_orders(models[pid],row,price); v=q*p['visitor_units_per_order']; rev=q*price*factor
            package=str(p['product_category']).lower() in ['package','套餐'] or pid.startswith('P_')
            rows.append(dict(product_id=pid,product_name=p['product_name'],price=price,orders=q,visitors=v,ticket_revenue=0. if package else rev,package_revenue=rev if package else 0.,fnb_revenue=v*fnb,merch_revenue=v*merch,cost=q*p['unit_variable_cost_cny']+v*secondary_cost))
    candidates=pd.DataFrame(rows)
    candidates['total_revenue']=candidates[['ticket_revenue','package_revenue','fnb_revenue','merch_revenue']].sum(axis=1)
    candidates['contribution_profit']=candidates.total_revenue-candidates.cost
    def evaluate(prices,name):
        chosen=pd.DataFrame([candidates[(candidates.product_id==pid)&(candidates.price==price)].iloc[0] for pid,price in prices.items()])
        keys=['ticket_revenue','package_revenue','fnb_revenue','merch_revenue','total_revenue','contribution_profit','visitors']
        result={k:float(chosen[k].sum()) for k in keys}
        result.update(name=name,capacity_utilization=result['visitors']/capacity,queue_minutes=5+38*(result['visitors']/capacity)**2,prices=prices)
        result['feasible']=result['visitors']<=capacity*capacity_rate+1e-6
        return result
    fixed={p['product_id']:min(grids[p['product_id']],key=lambda x:abs(x-p['base_price_cny'])) for p in products.to_dict('records')}
    rate=.1 if s['is_holiday'] else .05 if s['is_weekend'] else 0.
    rule={p['product_id']:min(grids[p['product_id']],key=lambda x:abs(x-p['base_price_cny']*(1+rate))) for p in products.to_dict('records')}
    A=np.array([(candidates.product_id==pid).astype(float).values for pid in pids]+[candidates.visitors.values])
    result=milp(-candidates['total_revenue' if objective=='revenue' else 'contribution_profit'].values,integrality=np.ones(len(candidates)),bounds=Bounds(0,1),constraints=LinearConstraint(A,[1]*len(pids)+[-np.inf],[1]*len(pids)+[capacity*capacity_rate]),options={'time_limit':15})
    prices={}; scenarios=[evaluate(fixed,'固定基准定价'),evaluate(rule,'规则定价')]
    if result.success:
        for r in candidates.loc[result.x>.5].to_dict('records'): prices[r['product_id']]=int(r['price'])
    if manual_prices is not None:
        if set(manual_prices)!=set(pids) or any(float(manual_prices[p]) not in grids[p] for p in pids): raise ValueError('修改价格必须包含全部产品，且符合5元步长、边界及调价约束')
        prices={p:int(v) for p,v in manual_prices.items()}
    feasible=bool(prices)
    if prices:
        best=evaluate(prices,'AI动态定价' if manual_prices is None else '人工调整测算'); scenarios.append(best); feasible=best['feasible']
        if not feasible and manual_prices is None: prices={}
    out=dict(feasible=feasible,prices=prices,scenarios=scenarios,candidates=candidates.to_dict('records'),elasticity=elasticity.to_dict('records'),message='离散价格与容量约束检查通过。' if feasible else '无可行方案：建议限流、分时入园或套餐分流。',assumptions=s)
    params=dict(target_date=str(date.date()),scenario=scenario or {},objective=objective,capacity_rate=capacity_rate,max_change=max_change,price_bounds=price_bounds)
    if persist:
        rid=save_run('pricing',params,out,db_path); out['run_id']=rid
        from .platform_core import audit_connection
        with audit_connection(db_path) as c:
            for i,r in enumerate(scenarios):
                c.execute('INSERT INTO scenario_result VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid+str(i),rid,r['name'],str(date.date()),r['name'],r['ticket_revenue'],r['package_revenue'],r['fnb_revenue'],r['merch_revenue'],r['total_revenue'],r['contribution_profit'],r['visitors'],r['capacity_utilization'],r['queue_minutes']))
            if feasible:
                for pid,price in prices.items():
                    r=candidates[(candidates.product_id==pid)&(candidates.price==price)].iloc[0]
                    c.execute('INSERT INTO pricing_recommendation VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid+pid,rid,str(date.date()),pid,float(products.set_index('product_id').loc[pid,'base_price_cny']),price,r.orders,r.ticket_revenue+r.package_revenue,scenarios[-1]['capacity_utilization'],objective,'PASS',out['message'],'待审批'))
    return out

FEATURES=['avg_temp_c','precipitation_mm','competitor_price_cny','marketing_campaign_flag','special_event_flag','planned_open_hours','is_weekend','is_holiday','is_school_vacation','month_sin','month_cos','weekday_sin','weekday_cos','lag_1_visitors','lag_7_visitors','rolling_7d_mean_visitors']
def feature_frame(df,weather_columns=None):
    d=df.copy(); dates=pd.to_datetime(d['date'])
    d['month_sin']=np.sin(2*np.pi*dates.dt.month/12); d['month_cos']=np.cos(2*np.pi*dates.dt.month/12)
    d['weekday_sin']=np.sin(2*np.pi*dates.dt.dayofweek/7); d['weekday_cos']=np.cos(2*np.pi*dates.dt.dayofweek/7)
    cat=pd.get_dummies(d.weather_type,prefix='weather',dtype=int)
    if weather_columns is not None: cat=cat.reindex(columns=weather_columns,fill_value=0)
    return pd.concat([d[FEATURES].reset_index(drop=True),cat.reset_index(drop=True)],axis=1)

@lru_cache(maxsize=2)
def train_forecaster(db_path=None):
    require_valid(db_path)
    df=load_daily_operating_frame(db_path)
    df['lag_1_visitors']=df.actual_visitors.shift(1); df['lag_7_visitors']=df.actual_visitors.shift(7)
    df['rolling_7d_mean_visitors']=df.actual_visitors.shift(1).rolling(7).mean(); df=df.dropna().reset_index(drop=True)
    X=feature_frame(df); y=df.actual_visitors
    train=df.date<'2025-09-01'; cal=(df.date>='2025-09-01')&(df.date<'2025-11-01'); test=df.date>='2025-11-01'
    model=RandomForestRegressor(n_estimators=200,max_depth=8,min_samples_leaf=3,random_state=20261102,n_jobs=-1)
    model.fit(X[train],y[train]); residual=np.abs(y[cal]-model.predict(X[cal])); radius=float(np.quantile(residual,.9,method='higher'))
    pred=model.predict(X[test]); actual=y[test].to_numpy(); baseline=df.loc[test,'lag_7_visitors'].to_numpy()
    metrics=dict(mae=float(np.mean(abs(actual-pred))),wape=float(sum(abs(actual-pred))/sum(actual)),baseline_mae=float(np.mean(abs(actual-baseline))),baseline_wape=float(sum(abs(actual-baseline))/sum(actual)),interval_coverage=float(np.mean(abs(actual-pred)<=radius)),train='2025-01-08 ~ 2025-08-31',calibration='2025-09-01 ~ 2025-10-31',test='2025-11-01 ~ 2025-12-31')
    back=df.loc[test,['date','actual_visitors']].copy(); back['predicted_visitors']=pred; back['lower']=np.maximum(0,pred-radius); back['upper']=pred+radius
    from joblib import dump
    (ROOT/'models').mkdir(exist_ok=True)
    dump({'model':model,'feature_columns':list(X.columns),'radius':radius,'metrics':metrics},ROOT/'models'/'platform_forecaster.joblib')
    return model,list(X.columns),radius,metrics,back

def forecast_future(start_date='2026-01-01',days=7,scenario=None,persist=True,db_path=None):
    require_valid(db_path)
    start=pd.Timestamp(start_date); history=load_daily_operating_frame(db_path)
    if not 1<=days<=30 or int(days)!=days or start<=history.date.max(): raise ValueError('预测起点须晚于历史末日，范围1至30天')
    if start>history.date.max()+pd.Timedelta(days=30): raise ValueError('起点距离历史末日不能超过30天，请先补充历史数据')
    s=scenario_values(scenario); model,columns,radius,metrics,_=train_forecaster(str(db_path) if db_path else None)
    past=history.actual_visitors.astype(float).tolist(); rows=[]
    for date in pd.date_range(history.date.max()+pd.Timedelta(days=1),start+pd.Timedelta(days=days-1)):
        r={**s,'date':date,'is_weekend':int(date.weekday()>=5),'lag_1_visitors':past[-1],'lag_7_visitors':past[-7],'rolling_7d_mean_visitors':float(np.mean(past[-7:]))}
        X=feature_frame(pd.DataFrame([r]),[c for c in columns if c.startswith('weather_')]).reindex(columns=columns)
        pred=max(0.,float(model.predict(X)[0])); past.append(pred)
        # Multi-step uncertainty is a heuristic expansion of held-out calibration error.
        width=radius*math.sqrt(len(past)-len(history))
        if date>=start: rows.append(dict(date=str(date.date()),predicted_visitors=pred,lower=max(0.,pred-width),upper=pred+width,lag_1=r['lag_1_visitors']))
    out=dict(rows=rows,metrics=metrics,assumptions=s,interval_note='90%校准残差区间，多步按平方根扩大，为情景参考区间，不保证未来覆盖率。')
    if persist:
        out['run_id']=save_run('forecast',dict(start_date=str(start.date()),days=days,scenario=s),out,db_path,training_period=('2025-01-08','2025-08-31'))
        # Allocate park forecasts by historical visitor shares, keeping model totals reconciled.
        t=load_core_data(db_path); q=t['fact_ticket_sales'].groupby('product_id').net_orders.sum(); p=t['dim_product'].set_index('product_id'); weights=q*p.visitor_units_per_order; weights=weights/weights.sum()
        from .platform_core import audit_connection,VERSION
        with audit_connection(db_path) as c:
            for r in rows:
                for pid,w in weights.items():
                    units=float(p.loc[pid,'visitor_units_per_order'])
                    c.execute('INSERT INTO forecast_result VALUES(?,?,?,?,?,?,?,?)',(out['run_id'],r['date'],pid,r['predicted_visitors']*w/units,r['lower']*w/units,r['upper']*w/units,r['predicted_visitors']*w,VERSION))
    return out
