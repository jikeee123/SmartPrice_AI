"""SmartPrice AI competition platform. Run with streamlit run app.py."""
from datetime import date
import json,time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
st.set_page_config(
    page_title="SmartPrice AI | 主题乐园经营分析平台",
    page_icon="🎡",
    layout="wide",
    initial_sidebar_state="auto"
)

import legacy_app as legacy
from smartprice_src.data_access import load_core_data
from smartprice_src.platform_core import validate_platform,read_runs,audit_connection,approve_run,dumps
from smartprice_src.scenario_engine import DEFAULT_SCENARIO,forecast_future,train_forecaster,pricing_scenarios,market_alerts,pricing_models
from smartprice_src.tools import ask,get_business_kpi,generate_business_report

from smartprice_src.labels import LABELS
legacy.page_header=lambda *args: None
def show_table(frame, **kwargs):
    st.dataframe(frame.rename(columns=LABELS).round(2), **kwargs)

from smartprice_src.ui_theme import apply_theme,brand,module_header
apply_theme()
PAGES=['经营数据分析中心','市场需求预测','智能定价决策','收益与利润分析','AI经营决策助手']
@st.cache_data(ttl=60)
def quality(): return validate_platform()
@st.cache_data(ttl=60)
def data(): return load_core_data()
@st.cache_data(ttl=60)
def business(a,b): return get_business_kpi(a,b)

def download(frame,label='下载明细CSV',key=None):
    st.download_button(label,frame.to_csv(index=False).encode('utf-8-sig'),file_name='SmartPrice_AI.csv',mime='text/csv',key=key)

def scenario_controls(key):
    saved=st.session_state.get('shared_scenario',DEFAULT_SCENARIO)
    with st.expander('情景假设：天气、竞品与节假日',expanded=True):
        c=st.columns(3)
        weather=sorted(data()['fact_daily_context'].weather_type.unique())
        w=c[0].selectbox('天气类型',weather,index=weather.index(saved['weather_type']),key=key+'w')
        temp=c[1].number_input('平均温度（℃）',-30.,50.,float(saved['avg_temp_c']),key=key+'t')
        rain=c[2].number_input('降雨量（毫米）',0.,500.,float(saved['precipitation_mm']),key=key+'r')
        comp=c[0].number_input('竞品平均票价（元）',1.,2000.,float(saved['competitor_price_cny']),key=key+'c')
        holiday=c[1].checkbox('假设为节假日',bool(saved['is_holiday']),key=key+'h')
        vacation=c[2].checkbox('假设为寒暑假',bool(saved['is_school_vacation']),key=key+'v')
        marketing=c[0].checkbox('营销活动',bool(saved['marketing_campaign_flag']),key=key+'m')
        event=c[1].checkbox('特殊活动',bool(saved['special_event_flag']),key=key+'e')
        hours=c[2].number_input('计划开放小时',1.,24.,float(saved['planned_open_hours']),key=key+'o')
    s=dict(weather_type=w,avg_temp_c=temp,precipitation_mm=rain,competitor_price_cny=comp,is_holiday=int(holiday),is_school_vacation=int(vacation),marketing_campaign_flag=int(marketing),special_event_flag=int(event),planned_open_hours=hours)
    st.session_state.shared_scenario=s
    return s

def pricing_page():
    st.subheader('智能定价 · 三种策略同口径比较')
    s=scenario_controls('price')
    c=st.columns(4)
    target=c[0].date_input('目标日期',date(2026,1,1),key='pricingdate')
    objective=c[1].selectbox('优化目标',['综合收入最大化','贡献利润最大化'])
    capacity=c[2].number_input('容量上限比例',.001,1.,.85,.01)
    change=c[3].number_input('最大单次调价比例',0.,1.,.1,.01)
    p=data()['dim_product'][['product_id','product_name','base_price_cny','min_price_cny','max_price_cny']].copy()
    st.caption('价格步长5元；产品绝对边界与单次调价限制同时生效。基准价不在网格时取最近可行价格。')
    bounds=st.data_editor(p,disabled=['product_id','product_name','base_price_cny'],hide_index=True,key='bounds',column_config={k:LABELS.get(k,k) for k in p.columns})
    if st.button('计算三种定价策略',type='primary'):
        with st.spinner('正在估计价格弹性并优化离散价格…'):
            started=time.perf_counter()
            r=pricing_scenarios(str(target),s,'revenue' if objective.startswith('综合') else 'profit',capacity,change,{x['product_id']:[x['min_price_cny'],x['max_price_cny']] for x in bounds.to_dict('records')})
            st.session_state.pricing_result=r; st.session_state.pricing_elapsed=time.perf_counter()-started
    if 'pricing_result' in st.session_state:
        r=st.session_state.pricing_result
        st.caption('以下为上次计算的结果，参数变化后需重新计算。运行编号：'+r['run_id'])
        (st.success if r['feasible'] else st.warning)(r['message'])
        st.caption('运行耗时：%.2f秒'%st.session_state.pricing_elapsed)
        compare=pd.DataFrame(r['scenarios']).drop(columns='prices')
        compare=compare[['name','total_revenue','contribution_profit','visitors','capacity_utilization','feasible','queue_minutes','ticket_revenue','package_revenue','fnb_revenue','merch_revenue']]
        show_table(compare.rename(columns={'name':'策略','total_revenue':'综合收入','contribution_profit':'贡献利润','visitors':'预计客流','feasible':'约束通过'}),hide_index=True)
        st.plotly_chart(px.bar(compare.rename(columns=LABELS),x='策略',y=['综合收入','贡献利润'],barmode='group',labels={'value':'元','variable':'指标'}),theme=None,width='stretch')
        if r['prices']:
            master=data()['dim_product'].set_index('product_id')
            rec=[]
            for pid,price in r['prices'].items():
                candidate=next(x for x in r['candidates'] if x['product_id']==pid and x['price']==price)
                rec.append({'产品':master.loc[pid,'product_name'],'基准价格':master.loc[pid,'base_price_cny'],'推荐价格':price,'调价幅度（%）':(price/master.loc[pid,'base_price_cny']-1)*100,'预计净订单':candidate['orders']})
            show_table(pd.DataFrame(rec),hide_index=True)
        st.info('推荐依据：结合日历、天气和历史产品价格弹性，在价格与容量约束内优化门票、套餐及增量消费收益。弹性来自模拟回归，不能解释为真实因果效应。')
        with st.expander('候选价格与模型诊断'):
            show_table(pd.DataFrame(r['candidates']),hide_index=True); show_table(pd.DataFrame(r['elasticity']),hide_index=True)
        download(compare,key='pricing_csv')
        st.download_button('下载定价报告',('# 定价模拟报告\n运行编号：'+r['run_id']+'\n'+r['message']+'\n```json\n'+dumps(r)+'\n```').encode('utf-8'),'定价模拟报告.md')

def forecast_page(start,end):
    history_tab,future_tab,factors_tab,alerts_tab=st.tabs(['历史回测','未来情景预测','季节与环境影响','需求预警'])
    with history_tab:
        with st.spinner('训练并校准随机森林…'):
            _,_,_,metrics,back=train_forecaster()
        c=st.columns(4)
        for col,k,label in zip(c,['mae','wape','baseline_wape','interval_coverage'],['MAE（人）','WAPE','上周同日基线WAPE','区间测试覆盖率']): col.metric(label,f'{metrics[k]:.2f}' if k=='mae' else f'{metrics[k]:.1%}')
        st.caption('训练：'+metrics['train']+'；校准：'+metrics['calibration']+'；测试：'+metrics['test']+'。历史回测为滚动单步，逐日使用此前已观测历史。')
        st.plotly_chart(px.line(back.rename(columns=LABELS),x='日期',y=['实际游客数','预测游客数','预测区间下界','预测区间上界']),theme=None,width='stretch');download(back,key='backtest_csv')
    with future_tab:
        s=scenario_controls('forecast')
        c=st.columns(2); forecast_start=c[0].date_input('预测起点',date(2026,1,1)); days=c[1].slider('预测天数',1,30,7)
        if st.button('生成未来情景预测',type='primary'):
            with st.spinner('递归预测中…'): st.session_state.future_result=forecast_future(str(forecast_start),days,s)
        if 'future_result' in st.session_state:
            r=st.session_state.future_result; frame=pd.DataFrame(r['rows'])
            st.caption('上次计算运行编号：'+r['run_id']);st.info(r['interval_note'])
            st.plotly_chart(px.line(frame.rename(columns=LABELS),x='日期',y=['预测游客数','预测区间下界','预测区间上界']),theme=None,width='stretch');show_table(frame,hide_index=True);download(frame,key='future_csv')
            st.caption('预测起点只支持历史末日后的30天内；中间缺口同样递归预测。产品售票量按历史客流份额分配，是辅助估计。')
    with factors_tab: demand_factors(start,end)
    with alerts_tab: demand_alerts(start,end)

def analysis_page(start,end):
    t=data(); products=t['dim_product']; ticket=t['fact_ticket_sales'].copy(); sec=t['fact_secondary_sales'].copy()
    selected=st.multiselect('产品筛选',products.product_id.tolist(),default=products.product_id.tolist(),format_func=lambda x:products.set_index('product_id').loc[x,'product_name'])
    channels=st.multiselect('销售渠道',sorted(ticket.sales_channel.unique()),default=sorted(ticket.sales_channel.unique()))
    ticket=ticket[ticket.date.between(str(start),str(end))&ticket.product_id.isin(selected)&ticket.sales_channel.isin(channels)]
    sec=sec[sec.date.between(str(start),str(end))&sec.sales_channel.isin(channels)]
    if ticket.empty: st.info('当前筛选没有门票或套餐记录。');return
    daily=ticket.groupby('date',as_index=False)[['net_sales_cny','net_orders','ticket_variable_cost_cny']].sum()
    c=st.columns(3);c[0].metric('所选产品净收入',f'¥{ticket.net_sales_cny.sum():,.0f}');c[1].metric('所选产品净订单',f'{ticket.net_orders.sum():,}');c[2].metric('渠道二次消费收入',f'¥{sec.net_sales_cny.sum():,.0f}')
    st.caption('门票/套餐来自 fact_ticket_sales；二次消费来自 fact_secondary_sales，仅按日期和渠道筛选，不按产品分摊。两类收入独立展示。')
    st.plotly_chart(px.line(daily,x='date',y='net_sales_cny',labels={'date':'日期','net_sales_cny':'元'}),theme=None,width='stretch')
    c=st.columns(2)
    c[0].plotly_chart(px.bar(ticket.groupby('product_id',as_index=False).net_sales_cny.sum(),x='product_id',y='net_sales_cny'),theme=None,width='stretch')
    c[1].plotly_chart(px.bar(ticket.groupby('sales_channel',as_index=False).net_sales_cny.sum(),x='sales_channel',y='net_sales_cny'),theme=None,width='stretch')
    show_table(daily,hide_index=True);download(ticket,key='analysis_csv')

def assistant_qa(start,end):
    st.caption('本地工具调度可直接运行。外部模型配置后仅润色计算证据，失败自动回退。未来目标日期以控件为准；客流预测与价格弹性模型分别测算，结果可能不同。')
    s=scenario_controls('assistant'); target=st.date_input('AI情景目标日期',date(2026,1,1)); days=st.slider('AI预测天数',1,30,7)
    q=st.text_input('经营问题',placeholder='下周下雨，应该如何调整票价？')
    if st.button('分析经营问题',type='primary') and q.strip():
        with st.spinner('正在调用经营分析与模型工具…'): st.session_state.answer=ask(q,str(start),str(end),str(target),days,s)
    if 'answer' in st.session_state:
        r=st.session_state.answer;st.markdown(r['answer']);st.caption('模式：'+r['mode']+'；运行编号：'+str(r['run_id']))
        if r.get('warning'):st.warning(r['warning'])
        with st.expander('查看工具、参数和计算证据'): st.json(r['trace'])
        st.download_button('下载AI分析记录',dumps(r).encode('utf-8'),'AI分析记录.json')

def assistant_report(start,end):
    d,p,c,sec=business(str(start),str(end))
    months=sorted(pd.to_datetime(d.date).dt.strftime('%Y-%m').unique())
    if months:
        st.caption('月报明细按所选月份与历史筛选范围的交集计算。非完整月份筛选时，环比仅比较已选数据。')
        month=st.selectbox('报告及归因月份',months,index=len(months)-1)
        if st.button('生成月度经营报告'):
            report=generate_business_report(str(start),str(end),month); st.session_state.month_report=report
        if 'month_report' in st.session_state:
            st.markdown(st.session_state.month_report);st.download_button('下载月度报告',st.session_state.month_report.encode('utf-8'),'月度经营报告.md')

def runs_page(kinds=('pricing','forecast'),approval=True):
    runs=read_runs()
    runs=runs[runs.kind.isin(kinds)]
    if runs.empty: st.info('尚无运行记录，请先执行预测或定价。');return
    show_table(runs.drop(columns=['parameters_json','result_json']),hide_index=True)
    rid=st.selectbox('选择运行编号',runs.run_id.tolist()); row=runs[runs.run_id==rid].iloc[0]
    st.write('运行参数');st.json(json.loads(row.parameters_json))
    r=json.loads(row.result_json)
    with audit_connection() as conn:
        latest=conn.execute("SELECT after_json FROM approval_event WHERE run_id=? AND after_json!='null' ORDER BY created_at DESC LIMIT 1",(rid,)).fetchone()
    current=json.loads(latest[0]) if latest else r
    if row.kind=='pricing' and current.get('prices'):
        st.write('当前有效方案价格（后续采纳或修改以此为准）');show_table(pd.DataFrame([{'产品':p,'价格':v} for p,v in current['prices'].items()]),hide_index=True)
    with st.expander('完整计算结果'):st.json(r)
    if row.kind=='pricing' and approval:
        operator=st.text_input('操作者姓名或称呼');action=st.selectbox('审批动作',['采纳','修改','拒绝']);comment=st.text_area('审批意见')
        revised=None
        if action=='修改':
            default=current['prices'] or {p['product_id']:p['base_price_cny'] for p in data()['dim_product'].to_dict('records')}
            edited=st.data_editor(pd.DataFrame([{'product_id':p,'price':v} for p,v in default.items()]),disabled=['product_id'],hide_index=True)
            revised={x['product_id']:x['price'] for x in edited.to_dict('records')}
        if st.button('提交审批记录'):
            with st.spinner('重新测算并保存审批…'):
                result=approve_run(rid,action,operator,comment,revised)
            st.success('审批记录已保存。')
            if result: st.json({k:v for k,v in result.items() if k not in ['candidates','elasticity']})
    with audit_connection() as conn: events=pd.read_sql_query('SELECT * FROM approval_event WHERE run_id=? ORDER BY created_at DESC',conn,params=[rid])
    st.write('审批历史');show_table(events,hide_index=True)
    st.download_button('导出运行记录',row.result_json.encode('utf-8'),'运行记录.json');download(events,key='events_csv')



def money_short(value):
    return f'¥{value/1e8:.2f}亿' if abs(value)>=1e8 else f'¥{value/1e4:.1f}万' if abs(value)>=1e4 else f'¥{value:,.2f}'

def overview_page(start,end):
    d,p,c,sec=business(str(start),str(end))
    revenue=float(d.total_revenue_cny.sum());visitors=float(d.actual_visitors.sum());profit=float(d.contribution_profit_cny.sum())
    cols=st.columns(4)
    cols[0].metric('综合经营收入',money_short(revenue),help=f'精确金额 ¥{revenue:,.2f}')
    cols[1].metric('入园游客人数',f'{visitors/1e4:.2f}万人' if visitors>=1e4 else f'{visitors:,.0f}人')
    cols[2].metric('游客人均收入',f'¥{revenue/max(visitors,1):,.2f}')
    cols[3].metric('贡献利润',money_short(profit),help='综合收入减票务变动成本和二次消费COGS，不等同于净利润。')
    st.caption(f'筛选期间 {start} 至 {end}  ｜  门票及套餐净订单 {d.net_ticket_package_orders.sum():,.0f} 单  ｜  套餐外餐饮 {money_short(d.addon_fnb_revenue_cny.sum())}  ｜  周边商品 {money_short(d.merchandise_revenue_cny.sum())}')
    left,right=st.columns([1.7,1])
    with left:
        st.subheader('销售收入与经营趋势')
        monthly=legacy.monthly_from_daily(d)
        st.plotly_chart(px.line(monthly,x='month',y='total_revenue_cny',markers=True,labels={'month':'月份','total_revenue_cny':'综合收入（元）'}),theme=None,width='stretch',key='overview_revenue')
    with right:
        st.subheader('收入来源')
        mix=pd.DataFrame({'业务':['门票及套餐','增量餐饮','周边商品'],'收入':[d.ticket_package_revenue_cny.sum(),d.addon_fnb_revenue_cny.sum(),d.merchandise_revenue_cny.sum()]})
        fig=px.pie(mix,names='业务',values='收入',hole=.72)
        fig.update_traces(textinfo='percent',textposition='inside')
        st.plotly_chart(fig,theme=None,width='stretch',key='overview_mix')
    left,right=st.columns([1.7,1])
    with left:
        st.subheader('客流与门票销量')
        frame=d[['date','actual_visitors','net_ticket_package_orders']].rename(columns={'date':'日期','actual_visitors':'入园人数','net_ticket_package_orders':'门票及套餐净订单'})
        st.plotly_chart(px.line(frame,x='日期',y=['入园人数','门票及套餐净订单'],labels={'value':'人数 / 订单数','variable':'指标'}),theme=None,width='stretch',key='overview_visitors')
    with right:
        st.subheader('游客人均收入趋势')
        st.plotly_chart(px.line(d,x='date',y='revenue_per_visitor_cny',labels={'date':'日期','revenue_per_visitor_cny':'元 / 人'}),theme=None,width='stretch',key='overview_spend')
    st.caption('收入来源：门票及套餐净额 + 套餐外餐饮 + 周边商品。套餐内权益分配不重复计入。门票订单与入园人数按产品每单游客数区分。')

def demand_factors(start,end):
    t=data();d=t['fact_daily_operations'].merge(t['fact_daily_context'],on='date').merge(t['dim_date'],on='date')
    d=d[d.date.between(str(start),str(end))]
    st.caption('以下为所选期间的历史分组统计，用于观察季节、天气和假日与客流的关系，不代表因果影响。')
    monthly=d.groupby('month_num',as_index=False).agg(日均客流=('actual_visitors','mean'),天数=('date','count'))
    left,right=st.columns(2)
    with left:
        st.subheader('季节性需求分布')
        st.plotly_chart(px.bar(monthly,x='month_num',y='日均客流',labels={'month_num':'月份'}),theme=None,width='stretch')
    with right:
        st.subheader('天气与日均客流')
        weather=d.groupby('weather_type',as_index=False).agg(日均客流=('actual_visitors','mean'),天数=('date','count'))
        st.plotly_chart(px.bar(weather,x='weather_type',y='日均客流',hover_data=['天数'],labels={'weather_type':'天气类型'}),theme=None,width='stretch')
    d['日期类型']=d.apply(lambda x:'节假日' if x.is_holiday else '非节假日周末' if x.is_weekend else '普通工作日',axis=1)
    holidays=d.groupby('日期类型',as_index=False).agg(日均客流=('actual_visitors','mean'),天数=('date','count'))
    st.subheader('节假日与周末影响');show_table(holidays,hide_index=True)
    st.plotly_chart(px.bar(holidays,x='日期类型',y='日均客流',hover_data=['天数']),theme=None,width='stretch')

def demand_alerts(start,end):
    st.subheader('需求变化与容量预警')
    s=st.session_state.get('shared_scenario',DEFAULT_SCENARIO)
    st.caption('情景预警沿用“未来情景预测”中的天气及假日设置。')
    for alert in market_alerts(s):st.info(alert)
    if 'future_result' in st.session_state:
        f=st.session_state.future_result; capacity=float(data()['fact_daily_operations'].park_capacity.iloc[-1])
        future=pd.DataFrame(f['rows']);future['预计容量利用率']=future.predicted_visitors/capacity
        st.caption('上次预测运行编号：'+f['run_id'])
        for alert in market_alerts(f['assumptions'],float(future['预计容量利用率'].max())):st.info(alert)
        show_table(future[['date','predicted_visitors','预计容量利用率']],hide_index=True)
    else:st.info('先生成未来情景预测，即可查看未来客流和容量预警。')
    ops=data()['fact_daily_operations'];high=ops[ops.date.between(str(start),str(end))&(ops.capacity_utilization_rate>=.85)]
    st.subheader('历史容量预警日');show_table(high,hide_index=True)
    download(high,'下载容量预警明细',key='capacity_csv')

def competitor_page(start,end):
    st.subheader('竞品价格对比')
    comp=data()['fact_competitor_price'];comp=comp[comp.date.between(str(start),str(end))]
    st.caption('竞品价格为模拟观测，按可比产品展示；不代表实时市场报价。')
    fig=px.line(comp,x='date',y='competitor_price_cny',color='competitor_name',labels=LABELS)
    adult=float(data()['dim_product'].set_index('product_id').loc['T_ADULT','base_price_cny'])
    fig.add_hline(y=adult,line_dash='dot',line_color='#E5A83B',annotation_text='本园成人票基准价')
    st.plotly_chart(fig,theme=None,width='stretch');show_table(comp,hide_index=True)
    download(comp,'下载竞品价格明细',key='competitor_csv')

def elasticity_page(start,end):
    st.subheader('价格弹性与需求敏感性')
    elasticity=pricing_models()[0]
    show_table(elasticity,hide_index=True)
    st.caption('回归来自全年模拟数据，未显著的弹性结果须谨慎使用；不是经随机价格实验验证的因果关系。')
    st.subheader('淡旺季价格观察')
    t=data();prices=t['fact_ticket_sales'].merge(t['dim_product'][['product_id','product_name']],on='product_id')
    prices=prices[prices.date.between(str(start),str(end))].copy();prices['月份']=pd.to_datetime(prices.date).dt.strftime('%Y-%m')
    by_month=prices.groupby(['月份','product_name'],as_index=False).list_unit_price_cny.mean()
    st.plotly_chart(px.line(by_month,x='月份',y='list_unit_price_cny',color='product_name',labels={'list_unit_price_cny':'记录挂牌均价（元）','product_name':'产品'}),theme=None,width='stretch')
    st.info('情景规则：节假日基准价上调10%，非节假日周末上调5%，其他日期保持基准价，再受产品边界、单次调价幅度和5元步长共同约束。淡旺季效果结合需求预测与价格情景验证，不直接套用固定涨幅。')

def attribution_page(start,end,key):
    d,p,c,sec=business(str(start),str(end))
    st.subheader('经营提示与收益变化')
    for insight in legacy.build_decision_insights(d,p):st.info(insight)
    months=sorted(pd.to_datetime(d.date).dt.strftime('%Y-%m').unique())
    month=st.selectbox('归因月份',months,index=len(months)-1,key=key)
    variance=legacy.explain_monthly_variance(d,month)
    if variance.get('available'):
        st.caption('环比仅比较当前筛选范围内的数据，非完整月份需结合覆盖天数理解。')
        if variance['revenue_delta']<0:
            st.warning('所选月份收入较上月下降 '+money_short(abs(variance['revenue_delta']))+'，请结合下方客流与人均收入分解核查原因。')
        cols=st.columns(3)
        cols[0].metric('收入变化',money_short(variance['revenue_delta']))
        cols[1].metric('客流规模影响',money_short(variance['revenue_volume_effect']))
        cols[2].metric('人均收入影响',money_short(variance['revenue_spend_per_visitor_effect']))
        show_table(legacy.get_monthly_variance_table(variance),hide_index=True)
        st.caption('收入变化按客流规模与游客人均收入分解；贡献利润变化等于收入变化减变动成本变化。')
    else:st.info('当前范围缺少可比较的上月数据，无法进行环比归因。')

def strategy_results():
    result=st.session_state.get('pricing_result')
    if result is None:
        runs=read_runs();runs=runs[runs.kind=='pricing']
        if not runs.empty:
            row=runs.iloc[0];result=json.loads(row.result_json);result['run_id']=row.run_id
    if result is None:
        st.info('请先到“智能定价决策”生成方案，这里将读取同一份结果进行收益比较。');return
    st.caption('共享定价运行编号：'+result['run_id'])
    st.caption('本页只读取已计算的方案，不另行调用优化模型；手工修改后的结果请在方案审批记录中查看。')
    compare=pd.DataFrame(result['scenarios']).drop(columns='prices')
    compare=compare[['name','total_revenue','contribution_profit','ticket_revenue','package_revenue','fnb_revenue','merch_revenue','visitors','capacity_utilization','queue_minutes','feasible']]
    show_table(compare,hide_index=True)
    st.plotly_chart(px.bar(compare.rename(columns=LABELS),x='策略',y=['综合收入','贡献利润'],barmode='group',labels={'value':'元','variable':'指标'}),theme=None,width='stretch',key='profit_strategy_chart')
    if not result['feasible']:st.warning(result['message'])
    download(compare,'下载三策略收益对比',key='profit_strategy_csv')

def profits_page(start,end):
    profit_tab,package_tab,strategy_tab=st.tabs(['收入与利润贡献','套餐与二次消费','定价策略收益对比'])
    d,p,c,sec=business(str(start),str(end))
    with profit_tab:
        st.subheader('收入与贡献利润趋势')
        monthly=d.groupby('month',as_index=False)[['total_revenue_cny','contribution_profit_cny']].sum()
        st.plotly_chart(px.bar(monthly.rename(columns={'month':'月份','total_revenue_cny':'综合收入','contribution_profit_cny':'贡献利润'}),x='月份',y=['综合收入','贡献利润'],barmode='group',labels={'value':'元','variable':'指标'}),theme=None,width='stretch')
        show_table(p[['product_name','net_sales_cny','ticket_variable_cost_cny','contribution_profit_cny','contribution_margin_rate']],hide_index=True)
        st.caption('产品贡献利润为净销售额减产品变动成本；二次消费毛利为增量餐饮/周边净额减COGS，两者不能混称净利润。')
    with package_tab:
        legacy.render_product_analysis(p,sec)
        package=p[p.product_id.str.startswith('P_')]
        if not package.empty:
            top=package.sort_values('contribution_profit_cny',ascending=False).iloc[0]
            mix=package.net_orders.sum()/max(p.net_orders.sum(),1)
            st.info('套餐净订单占比 {:.1%}；套餐贡献利润最高为「{}」，贡献利润 ¥{:,.0f}。建议结合转化率和服务承载能力评估组合。'.format(mix,top.product_name,top.contribution_profit_cny))
    with strategy_tab:strategy_results()

def assistant_module(start,end):
    qa,insights,report,history=st.tabs(['经营问答与建议','异常与收益归因','经营分析报告','对话与报告记录'])
    with qa:assistant_qa(start,end)
    with insights:attribution_page(start,end,'assistant_variance')
    with report:assistant_report(start,end)
    with history:runs_page(('assistant','report'),approval=False)

DESCRIPTIONS={
'经营数据分析中心':'从销售、客流与游客消费，掌握主题乐园的经营表现。',
'市场需求预测':'结合季节、天气与节假日，提前理解需求变化和运营压力。',
'智能定价决策':'用价格弹性和情景模拟制定建议，并完成方案复核与审批。',
'收益与利润分析':'拆解收入来源、产品贡献与二次消费，比较经营策略的收益。',
'AI经营决策助手':'以可追溯的数据与模型结果，回答管理问题并生成经营报告。'}

def main():
    brand()
    page=st.sidebar.radio('核心业务模块',PAGES)
    st.sidebar.divider()
    period=st.sidebar.date_input('历史经营日期',value=(date(2025,1,1),date(2025,12,31)),min_value=date(2025,1,1),max_value=date(2025,12,31))
    if not isinstance(period,tuple) or len(period)!=2:st.info('请选择完整日期范围。');return
    start,end=period
    st.sidebar.caption('数据期间：2025全年\n\n经营、天气与竞品均为模拟数据')
    if st.sidebar.button('刷新数据与重新校验',width='stretch'):
        st.cache_data.clear();train_forecaster.cache_clear();pricing_models.cache_clear();st.rerun()
    module_header(page,DESCRIPTIONS[page])
    errors=quality()
    if errors:st.error('数据质量未通过，相关计算已阻止。');st.write(errors);return
    try:
        if page=='经营数据分析中心':
            overview,details=st.tabs(['经营总览','销售与渠道明细'])
            with overview:overview_page(start,end)
            with details:analysis_page(start,end)
        elif page=='市场需求预测':forecast_page(start,end)
        elif page=='智能定价决策':
            simulate,elasticity,competitors,records=st.tabs(['定价模拟与建议','价格弹性与淡旺季策略','竞品价格对比','方案审批与记录'])
            with simulate:pricing_page()
            with elasticity:elasticity_page(start,end)
            with competitors:competitor_page(start,end)
            with records:runs_page()
        elif page=='收益与利润分析':profits_page(start,end)
        elif page=='AI经营决策助手':assistant_module(start,end)
    except (ValueError,RuntimeError,KeyError,TypeError) as e:st.error(str(e))
    st.caption('模拟经营演示版 · 收益测算不代表真实经营提升 · 贡献利润不等同于净利润 · 定价方案需人工审批')

if __name__=='__main__':main()
