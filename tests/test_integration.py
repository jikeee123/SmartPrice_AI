import unittest,json,os
from unittest.mock import patch
from smartprice_src.tools import ask
from smartprice_src.scenario_engine import pricing_scenarios,forecast_future
from smartprice_src.platform_core import approve_run,audit_connection,read_runs
class IntegrationTests(unittest.TestCase):
    def test_end_to_end(self):
        f=forecast_future(); self.assertEqual(len(f['rows']),7)
        r=pricing_scenarios(); self.assertTrue(r['feasible'])
        approve_run(r['run_id'],'采纳','验收员','雨天演示')
        approve_run(r['run_id'],'修改','验收员','复核价格',r['prices'])
        approve_run(r['run_id'],'拒绝','验收员','保留历史')
        with audit_connection() as c:
            self.assertEqual(c.execute('select count(*) from approval_event where run_id=?',(r['run_id'],)).fetchone()[0],3)
            self.assertEqual(c.execute('select count(*) from forecast_result where run_id=?',(f['run_id'],)).fetchone()[0],42)
        self.assertIn(r['run_id'],read_runs().run_id.tolist())
    def test_tools_and_fallback(self):
        with patch('smartprice_src.tools._call_openai_compatible',return_value=(None,'外部服务失败，回退本地')):
            a=ask('下周下雨，如何调整票价')
        self.assertEqual(a['mode'],'local')
        self.assertEqual(len(a['trace']),5)
        self.assertIn('预计',a['answer'])
        self.assertEqual(ask('写首诗')['trace'],[])
    def test_empty_and_missing_month(self):
        with self.assertRaises(ValueError): ask('经营收入',start_date='2030-01-01',end_date='2030-01-02')
        from smartprice_src.tools import get_business_kpi
        from smartprice_src.ai_decision import explain_monthly_variance
        d,*_=get_business_kpi('2025-10-01','2025-10-31')
        self.assertFalse(explain_monthly_variance(d,'2025-10')['available'])
    def test_modified_then_accepted(self):
        r=pricing_scenarios()
        alternative=dict(r['prices'])
        pid=next(iter(alternative))
        alternative[pid]=next(x['price'] for x in r['candidates'] if x['product_id']==pid and x['price']!=alternative[pid])
        modified=approve_run(r['run_id'],'修改','验收员','更换价格',alternative)
        adopted=approve_run(r['run_id'],'采纳','验收员','采纳修改版')
        self.assertEqual(adopted['prices'],modified['prices'])
    def test_training_metadata(self):
        f=forecast_future()
        with audit_connection() as c:
            row=c.execute('select training_start_date,training_end_date from model_run where run_id=?',(f['run_id'],)).fetchone()
        self.assertEqual(row,('2025-01-08','2025-08-31'))
    def test_report_month_alignment(self):
        from smartprice_src.tools import generate_business_report,get_business_kpi
        from smartprice_src.ai_decision import _fmt_money
        report=generate_business_report('2025-01-01','2025-12-31','2025-10')
        _,products,_,_=get_business_kpi('2025-10-01','2025-10-31')
        for _,row in products.sort_values('net_sales_cny',ascending=False).head(5).iterrows():
            self.assertIn('| '+row['product_name']+' | '+_fmt_money(row['net_sales_cny']),report)
    def test_external_network_failure(self):
        from smartprice_src.ai_decision import _call_openai_compatible
        with patch.dict(os.environ,{'SMARTPRICE_LLM_ENDPOINT':'https://example.invalid/v1/chat/completions','SMARTPRICE_LLM_API_KEY':'test','SMARTPRICE_LLM_MODEL':'test'}),patch('urllib.request.urlopen',side_effect=OSError('offline')):
            answer,warning=_call_openai_compatible('收入',{})
            self.assertIsNone(answer); self.assertIn('回退',warning)
if __name__=='__main__': unittest.main()
