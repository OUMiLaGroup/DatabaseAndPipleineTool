from pathlib import Path
import sys
import unittest
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'shared'))
from utilities.download_errors import MissingRouteRecordingsError, describe_download_failure


class DownloadErrorTests(unittest.TestCase):
    def test_missing_recordings_has_actionable_message(self):
        result = describe_download_failure(MissingRouteRecordingsError('internal details'))
        self.assertEqual(result['code'], 'recordings_unavailable')
        self.assertIn('upload', result['message'])

    def test_authentication_and_access_are_distinct_and_do_not_expose_secrets(self):
        for status, code in [(401, 'authentication_failed'), (403, 'access_denied'), (404, 'route_not_found'), (500, 'comma_service_error')]:
            request = httpx.Request('GET', 'https://example.com?secret=private', headers={'Authorization': 'JWT private'})
            error = httpx.HTTPStatusError('private', request=request, response=httpx.Response(status, request=request))
            result = describe_download_failure(error)
            self.assertEqual(result['code'], code)
            self.assertNotIn('private', str(result))

    def test_network_and_processing_failures_have_safe_messages(self):
        self.assertEqual(describe_download_failure(httpx.ConnectError('private'))['code'], 'connection_failed')
        self.assertEqual(describe_download_failure(RuntimeError('private'))['code'], 'processing_failed')


if __name__ == '__main__':
    unittest.main()
