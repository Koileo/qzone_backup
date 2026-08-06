import unittest

from qzone_api.utils.html_parser import clean_escaped_html, parse_callback_data, parse_feed_data


class ErrorParsingTests(unittest.TestCase):
    def test_login_error_is_preserved(self):
        raw = '_preloadCallback({"code":-3000,"message":"请先登录空间","subcode":-4001});'
        callback = parse_callback_data(clean_escaped_html(raw))
        parsed = parse_feed_data(callback)
        self.assertEqual(parsed["status"], "error")
        self.assertEqual(parsed["message"], "请先登录空间")
        self.assertEqual(parsed["data"], [])


if __name__ == "__main__":
    unittest.main()
