"""Local tool dispatcher; model providers only rephrase computed evidence."""
import re
import pandas as pd
from .dashboard_data import get_daily_metrics,get_product_analysis,get_channel_analysis,get_secondary_analysis
from .platform_core import route_question,save_run,dumps,require_valid
from .scenario_engine import forecast_future,pricing_scenarios,market_alerts,pricing_models
from .ai_decision import build_local_answer,build_monthly_report,build_llm_context,_call_openai_compatible

def get_business_kpi(start_date='2025-01-01',end_date='2025-12-31'):
    require_valid()
    return (get_daily_metrics(start_date,end_date),get_product_analysis(start_date,end_date),get_channel_analysis(start_date,end_date),get_secondary_analysis(start_date,end_date))

def get_market_alerts(scenario=None): return market_alerts(scenario)
def forecast_demand(**kwargs): return forecast_future(**kwargs)
def calculate_elasticity(): return pricing_models()[0]
def optimize_pricing(**kwargs): return pricing_scenarios(**kwargs)
def compare_scenarios(result): return result['scenarios']
def generate_business_report(start_date,end_date,month):
    d,p,c,s=get_business_kpi(start_date,end_date)
    if d.empty: raise ValueError('当前范围无数据')
    period=pd.Period(month,freq='M')
    lo=max(pd.Timestamp(start_date),period.start_time).strftime('%Y-%m-%d')
    hi=min(pd.Timestamp(end_date),period.end_time).strftime('%Y-%m-%d')
    p=get_product_analysis(lo,hi); c=get_channel_analysis(lo,hi); s=get_secondary_analysis(lo,hi)
    report=build_monthly_report(d,p,c,s,month,calculate_elasticity())
    rid=save_run('report',dict(start_date=str(start_date),end_date=str(end_date),month=month),dict(report=report))
    return report+'\n\n运行编号：'+rid+'\n数据筛选范围：'+str(start_date)+' 至 '+str(end_date)+'\n全部数据为模拟经营数据。'

def ask(question,start_date='2025-01-01',end_date='2025-12-31',target_date='2026-01-01',days=7,scenario=None):
    names=route_question(question)
    if not names: return dict(answer='当前支持经营指标、客流预测、价格弹性、定价策略、市场预警和月度报告，请围绕这些内容提问。',trace=[],mode='local',run_id=None)
    s=dict(scenario or {})
    if any(k in question for k in ['雨','降雨']): s.update(weather_type='Rainy',precipitation_mm=20.)
    d,p,c,sec=get_business_kpi(start_date,end_date)
    if d.empty: raise ValueError('当前范围无数据')
    trace=[]; evidence={}; pricing=None
    for name in names:
        if name=='get_business_kpi':
            evidence[name]=build_llm_context(d,p,c,sec,calculate_elasticity())
        elif name=='get_market_alerts': evidence[name]=get_market_alerts(s)
        elif name=='forecast_demand':
            f=forecast_demand(start_date=target_date,days=days,scenario=s,persist=False); evidence[name]=f
        elif name=='calculate_elasticity': evidence[name]=calculate_elasticity().to_dict('records')
        elif name=='optimize_pricing':
            pricing=optimize_pricing(target_date=target_date,scenario=s); evidence[name]={k:v for k,v in pricing.items() if k not in ['candidates','elasticity']}
        elif name=='compare_scenarios': evidence[name]=compare_scenarios(pricing)
        elif name=='generate_business_report':
            match=re.search(r'2025[-年](\d{1,2})',question); month='2025-'+match.group(1).zfill(2) if match else pd.to_datetime(d.date).max().strftime('%Y-%m')
            evidence[name]=generate_business_report(start_date,end_date,month)
        trace.append(dict(tool=name,parameters=dict(history=[str(start_date),str(end_date)],target_date=str(target_date),days=days,scenario=s),result=evidence[name]))
    answer=build_local_answer(question,d,p,c,sec,elasticity=calculate_elasticity())
    if 'forecast_demand' in evidence:
        f=evidence['forecast_demand']; answer='情景预测（非历史实绩）：未来%d天合计预计客流 %.0f 人。%s'%(days,sum(r['predicted_visitors'] for r in f['rows']),f['interval_note'])
    if pricing:
        answer+='\n\n'+pricing['message']
        if pricing['feasible']:
            best=pricing['scenarios'][-1]; base=pricing['scenarios'][0]
            answer+='\n推荐方案预计综合收入 ¥{:,.0f}，基准方案 ¥{:,.0f}；预计客流 {:.0f} 人，容量利用率 {:.1%}。这是模拟测算，需人工审批。'.format(best['total_revenue'],base['total_revenue'],best['visitors'],best['capacity_utilization'])
    if 'get_market_alerts' in evidence: answer+='\n\n'+'\n'.join(evidence['get_market_alerts'])
    if 'generate_business_report' in evidence: answer=evidence['generate_business_report']
    external,warning=_call_openai_compatible(question,{'computed_evidence':evidence,'local_answer':answer})
    result=dict(answer=external or answer,trace=trace,mode='external' if external else 'local',warning=warning)
    result['run_id']=save_run('assistant',dict(question=question,start_date=str(start_date),end_date=str(end_date)),result)
    return result
