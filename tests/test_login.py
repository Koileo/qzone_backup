import asyncio
import unittest

from qzone_api.login import QzoneLogin


class FakeQrHandler:
    async def generate_qrcode(self):
        return "fixture-signature"


class SlowCookieHandler:
    async def get_cookies(self, qrsig):
        await asyncio.sleep(1)
        return None


class LoginTests(unittest.TestCase):
    def test_qr_wait_honors_timeout(self):
        login = QzoneLogin()
        login.qr_handler = FakeQrHandler()
        login.cookie_handler = SlowCookieHandler()
        result = asyncio.run(login.login(timeout=0.01))
        self.assertEqual(result["code"], -2)
        self.assertIn("0.01", result["msg"])


if __name__ == "__main__":
    unittest.main()
