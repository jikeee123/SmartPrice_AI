import unittest,tempfile,sys,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy/modelscope'))
from cloud_storage import initialize_storage
class CloudStorageTests(unittest.TestCase):
    def test_seed_and_preserve(self):
        with tempfile.TemporaryDirectory() as d:
            seed=Path(d)/'seed.db'
            with sqlite3.connect(seed) as c:c.execute('create table record(value text)')
            c.close()
            target=initialize_storage(seed,Path(d)/'runtime')
            with sqlite3.connect(target) as c:c.execute("insert into record values('keep')")
            c.close()
            self.assertEqual(initialize_storage(seed,Path(d)/'runtime'),target)
            with sqlite3.connect(target) as c:self.assertEqual(c.execute('select value from record').fetchone()[0],'keep')
            c.close()
if __name__=='__main__':unittest.main()
