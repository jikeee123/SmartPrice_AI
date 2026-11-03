import unittest, tempfile, sqlite3, shutil
from pathlib import Path
from smartprice_src.platform_core import validate_platform, price_grid, route_question, save_run, approve_run, read_runs, audit_connection

class PlatformTests(unittest.TestCase):
    def test_data(self):
        self.assertEqual(validate_platform(), [])
    def test_corrupt_data_blocks_model(self):
        import gc
        from smartprice_src.data_access import DB_PATH
        from smartprice_src.platform_core import require_valid
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'corrupt.db'
            shutil.copyfile(DB_PATH,target)
            with audit_connection(target) as c:
                c.execute("update fact_ticket_sales set net_sales_cny=-1 where date='2025-01-01'")
            self.assertTrue(validate_platform(target))
            with self.assertRaises(ValueError): require_valid(target)
            gc.collect()
    def test_grid(self):
        self.assertEqual(price_grid(200, 180, 225, .1), [180,185,190,195,200,205,210,215,220])
        with self.assertRaises(ValueError): price_grid(200, 230, 240, .1)
    def test_routes(self):
        self.assertIn('forecast_demand', route_question('下周下雨客流如何'))
        self.assertIn('compare_scenarios', route_question('雨天如何调整票价'))
        self.assertEqual(route_question('写一首诗'), [])
    def test_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/'test.db'
            rid=save_run('test', {'x':1}, {'ok':True}, db)
            approve_run(rid, '拒绝', '测试员', '容量不足', None, db)
            self.assertEqual(read_runs(db).iloc[0]['run_id'], rid)
            with audit_connection(db) as c:
                self.assertEqual(c.execute('select count(*) from approval_event').fetchone()[0], 1)
            with self.assertRaises(ValueError): approve_run(rid,'采纳','','',None,db)

if __name__=='__main__': unittest.main()
