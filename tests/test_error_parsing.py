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

    def test_feed_total_is_preserved_for_pagination(self):
        parsed = parse_feed_data(
            {
                "code": 0,
                "total": 10001,
                "msglist": [{"tid": "m1", "uin": 123, "created_time": 1, "content": "fixture"}],
            }
        )
        self.assertEqual(parsed["total"], 1)
        self.assertEqual(parsed["total_available"], 10001)


if __name__ == "__main__":
    unittest.main()
