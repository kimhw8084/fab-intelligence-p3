import unittest

from fabintel.catalog import approved_join, synthetic_catalog
from fabintel.contracts import ContractError, envelope
from tests.fixtures.mock_mcp import PermissionDenied, SyntheticFabAdapter


class ContractTests(unittest.TestCase):
    def test_refusal_requires_reason(self):
        with self.assertRaises(ContractError): envelope('p1',{},'REFUSED',[],[])
    def test_unknown_product_rejected(self):
        with self.assertRaises(ContractError): envelope('p9',{},'VALID',[])
    def test_bootstrap_cannot_fake_internal(self):
        with self.assertRaises(ContractError): envelope('p1',{},'VALID',[],mode='INTERNAL_AUTHORIZED')
    def test_no_fake_semantics(self):
        m=SyntheticFabAdapter()
        with self.assertRaises(PermissionDenied):m.semantics('SECRET_PROD_TABLE')
        self.assertFalse(m.relationships('SYN_MEASURE','SYN_PROCESS')['approved'])
    def test_bounded_reads(self):
        m=SyntheticFabAdapter()
        with self.assertRaises(ValueError):m.read_bounded('SYN_WAFER',limit=100000,rows=[1,2])
        self.assertEqual(m.read_bounded('SYN_WAFER',limit=1,rows=[1,2]),[1])
        self.assertEqual(len(m.audit),1)
    def test_catalog_scale_and_determinism(self):
        cat=synthetic_catalog(13000)
        self.assertEqual(len(cat),13000)
        self.assertEqual(cat,synthetic_catalog(13000))
        self.assertFalse(approved_join(cat[0]['id'],cat[1]['id'],'wafer_id',cat))
if __name__=='__main__':unittest.main()
