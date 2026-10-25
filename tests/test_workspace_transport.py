import json
import tomllib
import unittest
from pathlib import Path
from simmah_slate_workspaces import workspace_transport, accept_selected_record


class WorkspaceTransportTests(unittest.TestCase):
    def record(self, name, snapshot):
        return dict(id=name, name=name+'.csv', title=name, data='CSV', snapshot=snapshot)

    def test_outgoing_inventory_does_not_duplicate_any_saved_snapshots(self):
        blob='saved-state'*100000
        current=self.record('current',blob)
        records={name:self.record(name,blob) for name in ['current','other','afternoon']}
        args=workspace_transport(current, records, blob)
        self.assertEqual(args['snapshot'],blob)
        self.assertNotIn('snapshot',args['current'])
        self.assertTrue(all(set(r)=={'id','name','title'} for r in args['records']))
        encoded=json.dumps(args)
        self.assertEqual(encoded.count(blob),1)
        self.assertEqual(records['other']['snapshot'],blob)

    def test_browser_only_next_slate_restores_after_server_restart(self):
        selected=self.record('afternoon','exact saved build')
        records={}
        self.assertEqual(accept_selected_record(records,{'selected':selected,'closed':'main'}),selected)
        self.assertEqual(records['afternoon']['snapshot'],'exact saved build')

    def test_metadata_cannot_overwrite_a_full_saved_record(self):
        original=self.record('main','keep original')
        records={'main':original}
        accept_selected_record(records,{'selected':{'id':'main','title':'metadata only'}})
        self.assertEqual(records['main'],original)

    def test_config_accommodates_largest_observed_legacy_message(self):
        config=tomllib.loads(Path('.streamlit/config.toml').read_text())
        self.assertGreater(config['server']['maxMessageSize']*1000000,79691056)


if __name__=='__main__':
    unittest.main()
