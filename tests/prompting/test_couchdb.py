import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
from azathoth.prompting.couchdb import CouchDB

class TestCouchDB(unittest.TestCase):
    @patch('azathoth.prompting.couchdb.requests.Session')
    def test_create_document(self, mock_session):
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "id": "test_id"}
        mock_session.return_value.request.return_value = mock_response

        couchdb = CouchDB("http://example.com", "test_db")
        result = couchdb.create_document({"test": "data"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["id"], "test_id")
        mock_session.return_value.request.assert_called_once_with('POST', 'http://example.com/test_db/', json={"test": "data"})

if __name__ == '__main__':
    unittest.main()
