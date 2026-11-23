import unittest
from fabintel.project import describe, analyze
class SpecializedTests(unittest.TestCase):
 def test_edge_center_fixed(self):
  self.assertEqual(describe([{'x':0,'y':0,'value':10},{'x':1,'y':0,'value':12},{'x':-1,'y':0,'value':12}],1)['edge_minus_center'],2)
 def test_no_fabricated_unobserved_region(self):
  data={'coordinates_verified':True,'geometry':{'radius':1,'origin':{'x':0,'y':0},'orientation_deg':0,'coordinate_system':'wafer_xy_v1','coordinate_unit':'mm'},'measurement':{'metric':'thickness','unit':'nm','modality':'continuous'},'points':[{'x':1,'y':0,'value':10},{'x':-1,'y':0,'value':11},{'x':0,'y':1,'value':12}]}
  result=analyze(data)
  self.assertEqual(result['status'],'PARTIAL')
  fingerprint=result['artifacts'][0]['result']['fingerprint']
  self.assertEqual(fingerprint['edge_center']['status'],'INCONCLUSIVE')
  self.assertEqual(fingerprint['regions']['center']['count'],0)
  self.assertEqual(sum(row['count'] for row in fingerprint['radial_profile']),3)
