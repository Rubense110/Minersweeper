import copy
import os
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from flask import Flask
from api.petri_routes import bp
from model_exploration.bpmn import _convert_model_graph


class BpmnImageTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(bp)
        self.client = app.test_client()
        self.model = {
            'places': [{'id': 'p0'}, {'id': 'p1'}, {'id': 'p2'}],
            'transitions': [{'id': 't0', 'label': 'Review application', 'invisible': False},
                            {'id': 't1', 'label': 'Hidden routing', 'invisible': True}],
            'arcs': [{'source': 'p0', 'target': 't0'}, {'source': 't0', 'target': 'p1'},
                     {'source': 'p1', 'target': 't1'}, {'source': 't1', 'target': 'p2'}],
            'initial_marking': [{'place_id': 'p0', 'tokens': 1}],
            'final_marking': [{'place_id': 'p2', 'tokens': 1}],
            'final_markings': [[{'place_id': 'p1', 'tokens': 1}], [{'place_id': 'p2', 'tokens': 1}]],
        }

    def test_svg_image_preserves_task_and_hides_invisible_routing(self):
        original = copy.deepcopy(self.model)
        with mock.patch('model_exploration.bpmn._convert_model_graph', wraps=_convert_model_graph) as convert:
            response = self.client.post('/bpmn/render?format=svg', json=self.model)
        self.assertEqual(200, response.status_code, response.data)
        self.assertEqual('image/svg+xml', response.mimetype)
        root = ET.fromstring(response.data)
        text = ''.join(root.itertext())
        self.assertIn('Review application', text)
        self.assertNotIn('Hidden routing', text)
        self.assertEqual(self.model['initial_marking'], convert.call_args.args[0]['initial_marking'])
        self.assertEqual(self.model['final_marking'], convert.call_args.args[0]['final_marking'])
        self.assertEqual(original, self.model)
        self.assertEqual('no-store', response.headers['Cache-Control'])

    def test_png_is_an_actual_image(self):
        response = self.client.post('/bpmn/render?format=png', json=self.model)
        self.assertEqual(200, response.status_code)
        self.assertEqual('image/png', response.mimetype)
        self.assertTrue(response.data.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_rejects_unsupported_format_and_empty_net(self):
        self.assertEqual(400, self.client.post('/bpmn/render?format=pdf', json=self.model).status_code)
        self.assertEqual(400, self.client.post('/bpmn/render', json={}).status_code)


if __name__ == '__main__':
    unittest.main()
