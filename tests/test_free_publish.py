import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy'))
from publish_free import choose_free_hardware,safe_message
class PublishTests(unittest.TestCase):
    def test_paid_never_selected(self):
        with self.assertRaises(RuntimeError):choose_free_hardware({'items':[{'name':'paid/cpu','resource_type':'paid'}]})
        with self.assertRaises(RuntimeError):choose_free_hardware([{'name':'platform/cpu','resource_type':'paid'}])
        self.assertEqual(choose_free_hardware({'items':[{'name':'paid/gpu'},{'name':'platform/cpu','resource_type':'free'}]}),'platform/cpu')
    def test_secret_redaction(self):
        self.assertNotIn('private-token',safe_message('error private-token','private-token'))
if __name__=='__main__':unittest.main()
