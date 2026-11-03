from pathlib import Path
from streamlit.testing.v1 import AppTest
import json
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]
a=AppTest.from_file(str(root/'app.py'),default_timeout=90).run()
def page(name):
    a.sidebar.radio[0].set_value(name).run()
    assert not a.exception,[e.value for e in a.exception]
def button(label):
    next(b for b in a.button if b.label==label).click().run()
    assert not a.exception,[e.value for e in a.exception]
    assert not a.error,[e.value for e in a.error]
page('市场需求预测');button('生成未来情景预测')
assert a.session_state['future_result']['run_id']
page('智能定价决策');button('计算三种定价策略')
rid=a.session_state['pricing_result']['run_id']
assert a.session_state['pricing_result']['feasible']
with patch('smartprice_src.scenario_engine.pricing_scenarios',side_effect=AssertionError('收益页不应重新计算')):
    page('收益与利润分析')
assert a.session_state['pricing_result']['run_id']==rid
assert any(rid in x.value for x in a.caption)
page('AI经营决策助手')
next(x for x in a.text_input if x.label=='经营问题').set_value('下周下雨，应该如何调整票价')
button('分析经营问题')
assert len(a.session_state['answer']['trace'])==5
button('生成月度经营报告')
assert '运行编号' in a.session_state['month_report']
from smartprice_src.platform_core import read_runs
all_runs=read_runs()
assistant_ids=set(all_runs[all_runs.kind.isin(['assistant','report'])].run_id)
assert set(next(s for s in a.selectbox if s.label=='选择运行编号').options).issubset(assistant_ids)
page('智能定价决策')
next(s for s in a.selectbox if s.label=='选择运行编号').set_value(rid).run()
next(t for t in a.text_input if t.label=='操作者姓名或称呼').set_value('页面验收员')
next(t for t in a.text_area if t.label=='审批意见').set_value('雨天方案通过演示复核')
button('提交审批记录')
assert any('已保存' in x.value for x in a.success)
(root/'reports'/'workflow_ui_validation.json').write_text(json.dumps({'status':'PASS','pricing_run_id':rid,'steps':['future_forecast','three_strategy_pricing','assistant_5_tools','monthly_report','approval_saved']},ensure_ascii=False,indent=2),encoding='utf-8')
print('Workflow UI PASS',rid)
