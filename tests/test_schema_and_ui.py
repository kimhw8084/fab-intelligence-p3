import json
import unittest
from pathlib import Path


class SourceContractTests(unittest.TestCase):
 def test_schema_files_identify_version(self):
  root=Path(__file__).resolve().parent.parent
  for name in ('evidence.v1.schema.json','product-manifest.v1.schema.json'):
   doc=json.loads((root/'contracts'/name).read_text())
   self.assertIn('1.0.0',doc['$id'])
 def test_manifest_declares_candidate_not_release_ready(self):
  root=Path(__file__).resolve().parent.parent
  manifest=json.loads((root/'product.json').read_text())
  self.assertEqual(manifest['release_state'],'CANDIDATE')
  self.assertEqual(manifest['contract_version'],'1.0.0')
  self.assertIn('python-stdlib-3.10+',manifest['dependencies'])
 def test_no_remote_frontend_assets(self):
  root=Path(__file__).resolve().parent.parent
  self.assertFalse((root/'ui'/'index.html').exists())
  self.assertFalse((root/'fabintel'/'web.py').exists())
  panel=(root/'products'/'p3'/'ui'/'P3Panel.tsx').read_text()
  self.assertIn('data-product-id="p3"',panel)
  self.assertIn('renderWaferMap',panel)
  self.assertIn('No analysis result is available',panel)
  manifest=json.loads((root/'product.json').read_text())
  self.assertNotIn('local_ui',manifest['entrypoints'])
