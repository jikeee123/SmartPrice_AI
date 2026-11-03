from streamlit.testing.v1 import AppTest
from pathlib import Path
import json,time
pages=['经营数据分析中心','市场需求预测','智能定价决策','收益与利润分析','AI经营决策助手']
a=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=90).run()
results={}
assert a.sidebar.radio[0].options==pages
assert a.sidebar.radio[0].value==pages[0]
expected_tabs={
'经营数据分析中心':['经营总览','销售与渠道明细'],
'市场需求预测':['历史回测','未来情景预测','季节与环境影响','需求预警'],
'智能定价决策':['定价模拟与建议','价格弹性与淡旺季策略','竞品价格对比','方案审批与记录'],
'收益与利润分析':['收入与利润贡献','套餐与二次消费','定价策略收益对比'],
'AI经营决策助手':['经营问答与建议','异常与收益归因','经营分析报告','对话与报告记录']}
for p in pages:
    start=time.perf_counter();a.sidebar.radio[0].set_value(p).run()
    assert any('module-header' in x.value for x in a.markdown),'Styles missing after rerun'
    assert [t.label for t in a.tabs]==expected_tabs[p]
    if p=='市场需求预测':
        assert not a.tabs[2].dataframe[0].value.empty,'历史环境分析应使用历史筛选范围'
        assert not a.tabs[3].dataframe[-1].value.empty,'历史容量预警不应被未来日期覆盖'
    results[p]={'exceptions':[str(e.value) for e in a.exception],'errors':[str(e.value) for e in a.error],'seconds':round(time.perf_counter()-start,3)}
    print(p,results[p])
Path('reports/ui_validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
assert all(not r['exceptions'] and not r['errors'] for r in results.values()),results
