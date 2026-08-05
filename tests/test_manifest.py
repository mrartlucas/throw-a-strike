import json, unittest
class ManifestTests(unittest.TestCase):
    def test_manifest_describes_playable_ten_pin(self):
        data=json.load(open('conf.json'))
        self.assertEqual(data['version'],'0.4.0')
        self.assertIn('single-player regulation 10-Pin', data['description'])
