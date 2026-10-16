import json
import unittest

from tools.probe_embedded_store import endpoint,summarize


class StoreProbeTests(unittest.TestCase):
    def test_local_endpoint_rejects_external_addresses_and_invalid_ports(self):
        self.assertEqual(endpoint(19222),'http://127.0.0.1:19222')
        for port in [0,80,65536,True,'https://example.com']:
            with self.assertRaises(ValueError):endpoint(port)

    def test_summary_does_not_expose_account_titles_tokens_or_debugger_ids(self):
        raw=[{'type':'page','url':'https://store.lotro.com/path?token=SECRET#SESSION',
              'title':'PRIVATE_ACCOUNT','id':'DEBUG_ID',
              'webSocketDebuggerUrl':'ws://127.0.0.1:19222/devtools/page/DEBUG_ID'}]
        report=summarize({'Browser':'Chrome/99','Protocol-Version':'1.3'},raw)
        self.assertTrue(report['pages'][0]['store_candidate'])
        for secret in ['SECRET','SESSION','PRIVATE_ACCOUNT','DEBUG_ID','/path']:
            self.assertNotIn(secret,json.dumps(report))

    def test_other_origins_are_not_marked_as_store_or_queried(self):
        report=summarize({},[{'type':'page','url':'https://payment.example/path'},
                              {'type':'page','url':'data:text/html,private'},
                              {'type':'service_worker','url':'https://store.lotro.com/'}])
        self.assertEqual(len(report['pages']),2)
        self.assertFalse(any(p['store_candidate'] for p in report['pages']))
        self.assertIsNone(report['pages'][1]['hostname'])
