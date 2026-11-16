import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError


TEST_ENV = {
    "AUTH_USERNAME": "test-user",
    "AUTH_PASSWORD": "test-password-only",
    "AUTH_SECRET": "test-signing-key-only-" * 3,
}
with patch.dict(os.environ, TEST_ENV):
    from app import auth
    from app.config import Settings


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            auth_username="测试用户", auth_password="测试密码",
            auth_secret="test-signing-key-only-" * 3, auth_token_ttl=60,
        )
        self.mock_settings = patch.object(auth, "settings", self.settings)
        self.mock_settings.start()
        self.addCleanup(self.mock_settings.stop)

    def signed(self, payload):
        raw = auth._b64encode(payload)
        return raw + "." + auth._sign(raw)

    def test_login_and_token_round_trip(self):
        self.assertTrue(auth.verify_credentials("测试用户", "测试密码"))
        self.assertFalse(auth.verify_credentials("测试用户", "wrong"))
        self.assertEqual(auth.verify_token(auth.create_token("测试用户")["token"]), "测试用户")

    def test_credential_changes_revoke_existing_token(self):
        for field in ("auth_username", "auth_password", "auth_secret"):
            with self.subTest(field=field):
                token = auth.create_token(self.settings.auth_username)["token"]
                old = getattr(self.settings, field)
                setattr(self.settings, field, old + "changed")
                self.assertIsNone(auth.verify_token(token))
                setattr(self.settings, field, old)

    def test_expired_tampered_and_legacy_tokens_rejected(self):
        payload = {"u": self.settings.auth_username, "exp": int(time.time()) - 1,
                   "cv": auth._credential_tag()}
        self.assertIsNone(auth.verify_token(self.signed(payload)))
        payload["exp"] = int(time.time()) + 60
        del payload["cv"]
        self.assertIsNone(auth.verify_token(self.signed(payload)))
        token = auth.create_token(self.settings.auth_username)["token"]
        self.assertIsNone(auth.verify_token(token + "x"))
        self.assertIsNone(auth.verify_token(token.rsplit(".", 1)[0] + ".非ASCII"))

    def test_malformed_signed_payloads_rejected(self):
        for payload in ([], None, 42, {"exp": "bad"}, {"exp": True}, {"exp": float("inf")}):
            with self.subTest(payload=payload):
                self.assertIsNone(auth.verify_token(self.signed(payload)))

    def test_config_requires_explicit_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)
        for field, value in (("AUTH_USERNAME", "  "), ("AUTH_PASSWORD", ""),
                             ("AUTH_SECRET", "short"), ("AUTH_TOKEN_TTL", "0")):
            with self.subTest(field=field), patch.dict(os.environ, {**TEST_ENV, field: value}):
                with self.assertRaises(ValidationError) as caught:
                    Settings(_env_file=None)
                self.assertNotIn("input_value=", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
