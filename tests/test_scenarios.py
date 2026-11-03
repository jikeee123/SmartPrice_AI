import unittest
from smartprice_src.scenario_engine import pricing_scenarios, forecast_future, market_alerts, train_forecaster
class ScenarioTests(unittest.TestCase):
    def test_price_and_finance(self):
        r=pricing_scenarios(persist=False)
        self.assertTrue(r['feasible'])
        self.assertEqual(len(r['scenarios']),3)
        for p in r['prices'].values(): self.assertEqual(p%5,0)
        for s in r['scenarios']:
            self.assertAlmostEqual(s['total_revenue'],s['ticket_revenue']+s['package_revenue']+s['fnb_revenue']+s['merch_revenue'],places=5)
    def test_impossible(self):
        r=pricing_scenarios(capacity_rate=.001,persist=False)
        self.assertFalse(r['feasible'])
        self.assertEqual(r['prices'],{})
    def test_future(self):
        r=forecast_future(days=7,persist=False)
        self.assertEqual(len(r['rows']),7)
        self.assertTrue(all(x['lower']<=x['predicted_visitors']<=x['upper'] for x in r['rows']))
        self.assertEqual(r['rows'][1]['lag_1'],r['rows'][0]['predicted_visitors'])
        with self.assertRaises(ValueError): forecast_future(days=31,persist=False)
        with self.assertRaises(ValueError): forecast_future(start_date='2025-12-30',persist=False)
    def test_manual_constraints(self):
        with self.assertRaises(ValueError): pricing_scenarios(manual_prices={'T_ADULT':1},persist=False)
    def test_alerts(self):
        self.assertTrue(market_alerts({'weather_type':'Rainy','precipitation_mm':30}))
if __name__=='__main__': unittest.main()
