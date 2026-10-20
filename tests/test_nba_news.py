import unittest
from unittest.mock import Mock, patch
import requests
import simmah_nba_news as news


class NewsTests(unittest.TestCase):
    def tearDown(self):
        news._account.clear()
        news._posts.clear()

    def test_lookup_posts_and_shared_cache(self):
        lookup = Mock(status_code=200)
        lookup.json.return_value = {'data': {'id': '123'}}
        posts = Mock(status_code=200)
        posts.json.return_value = {'data': [{'id': '456', 'text': 'Player ruled out',
                                           'created_at': '2026-10-20T14:00:00Z'}]}
        with patch.object(news.requests, 'get', side_effect=[lookup, posts]) as get:
            account = news._account('fingerprint', 'private-token')
            result = news._posts('fingerprint', account, 'private-token')
            self.assertEqual(news._posts('fingerprint', account, 'private-token'), result)
            self.assertEqual(get.call_count, 2)
            self.assertEqual(result['posts'][0]['id'], '456')
            self.assertEqual(get.call_args.kwargs['params']['max_results'], 10)
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            self.assertNotIn('private-token', str(result))

    def test_errors_never_expose_credentials_or_response_body(self):
        for status in (401, 402, 403, 429, 500):
            response = Mock(status_code=status, text='private-token')
            with patch.object(news.requests, 'get', return_value=response):
                with self.assertRaises(news.NewsUnavailable) as caught:
                    news._get('users/123/tweets', 'private-token')
                self.assertNotIn('private-token', str(caught.exception))
        with patch.object(news.requests, 'get', side_effect=requests.Timeout('private-token')):
            with self.assertRaises(news.NewsUnavailable) as caught:
                news._get('users/123/tweets', 'private-token')
            self.assertNotIn('private-token', str(caught.exception))

    def test_partial_error_is_not_reported_as_success(self):
        response = Mock(status_code=200)
        response.json.return_value = {'errors': [{'detail': 'private-token'}]}
        with patch.object(news.requests, 'get', return_value=response):
            with self.assertRaises(news.NewsUnavailable):
                news._get('users/123/tweets', 'private-token')
