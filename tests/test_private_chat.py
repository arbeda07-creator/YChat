import io
import json
import shutil
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import create_app
from app.config import ProductionConfig
from app.chat.storage import get_messages, save_message
from app.models import Message
from app.migrations.import_json_messages import import_json_messages
from app.security import clear_rate_limit, rate_limit
from app.extensions import db
from app.models import User


class PrivateChatTestCase(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parent
        self.messages_file = root / "test-messages.json"
        self.private_messages_file = root / "test-private-messages.json"
        self.upload_folder = root / "test-uploads"
        self.messages_file.unlink(missing_ok=True)
        self.private_messages_file.unlink(missing_ok=True)
        self.messages_file.with_name(f"{self.messages_file.name}.bak").unlink(missing_ok=True)
        self.private_messages_file.with_name(f"{self.private_messages_file.name}.bak").unlink(missing_ok=True)
        shutil.rmtree(self.upload_folder, ignore_errors=True)

        class TestConfig:
            TESTING = True
            SECRET_KEY = "test-secret"
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            MESSAGES_FILE = str(self.messages_file)
            PRIVATE_MESSAGES_FILE = str(self.private_messages_file)
            UPLOAD_FOLDER = str(self.upload_folder)
            MAX_CONTENT_LENGTH = 9 * 1024 * 1024
            MAX_PROFILE_IMAGE_BYTES = 8 * 1024 * 1024
            FORCE_HTTPS = False
            SESSION_COOKIE_SECURE = False
            RATELIMIT_STORAGE_URI = "memory://"

        self.app = create_app(TestConfig)
        with self.app.app_context():
            alice = User(username="alice")
            alice.set_password("password1")
            bob = User(username="bob")
            bob.set_password("password2")
            charlie = User(username="charlie")
            charlie.set_password("password3")
            legacy_mixed_case = User(username="LegacyUser")
            legacy_mixed_case.set_password("OldPassword123")
            db.session.add_all([alice, bob, charlie, legacy_mixed_case])
            db.session.commit()
            self.alice_id = alice.id
            self.bob_id = bob.id
            self.charlie_id = charlie.id

        self.alice = self.app.test_client()
        self.bob = self.app.test_client()
        self._login(self.alice, self.alice_id)
        self._login(self.bob, self.bob_id)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.messages_file.unlink(missing_ok=True)
        self.private_messages_file.unlink(missing_ok=True)
        self.messages_file.with_name(f"{self.messages_file.name}.bak").unlink(missing_ok=True)
        self.private_messages_file.with_name(f"{self.private_messages_file.name}.bak").unlink(missing_ok=True)
        shutil.rmtree(self.upload_folder, ignore_errors=True)

    @staticmethod
    def _login(client, user_id):
        with client.session_transaction() as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True
            session["_csrf_token"] = "test-csrf-token"
            session["last_seen"] = int(__import__("time").time())
        client.environ_base["HTTP_X_CSRF_TOKEN"] = "test-csrf-token"

    def _accepted_message(self):
        response = self.alice.post("/api/dm/bob/send", json={"message": "Hello"})
        self.assertEqual(response.status_code, 201)
        message_id = response.get_json()["message"]["id"]
        self.assertEqual(self.bob.post("/api/dm/alice/accept").status_code, 200)
        return message_id

    def test_mobile_sized_profile_image_can_be_uploaded(self):
        image_bytes = b"\x89PNG\r\n\x1a\n" + (b"\0" * (3 * 1024 * 1024))
        response = self.alice.post(
            "/auth/profile",
            data={
                "csrf_token": "test-csrf-token",
                "profile_image": (io.BytesIO(image_bytes), "camera-photo.png"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            user = db.session.get(User, self.alice_id)
            self.assertTrue(user.profile_image.endswith(".png"))
            self.assertTrue((self.upload_folder / user.profile_image).is_file())

    def test_read_receipt_changes_after_recipient_opens_chat(self):
        self._accepted_message()

        before = self.alice.get("/api/dm/bob/messages").get_json()["messages"][0]
        self.assertFalse(before["is_read"])

        self.assertEqual(self.bob.get("/api/dm/alice/messages").status_code, 200)

        after = self.alice.get("/api/dm/bob/messages").get_json()["messages"][0]
        self.assertTrue(after["is_read"])

    def test_only_sender_can_delete_private_message(self):
        message_id = self._accepted_message()

        response = self.bob.delete(f"/api/dm/alice/messages/{message_id}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            len(self.alice.get("/api/dm/bob/messages").get_json()["messages"]),
            1,
        )

        response = self.alice.delete(f"/api/dm/bob/messages/{message_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.alice.get("/api/dm/bob/messages").get_json()["messages"],
            [],
        )

    def test_voice_upload_is_saved_without_conversion(self):
        audio_bytes = b"\x1aE\xdf\xa3" + (b"\0" * 512)
        audio = io.BytesIO(audio_bytes)

        response = self.alice.post(
            "/api/dm/bob/send",
            data={"voice": (audio, "voice.webm", "audio/webm")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 201)
        message = response.get_json()["message"]
        self.assertEqual(message["message_type"], "voice")
        self.assertTrue(message["audio_name"].endswith(".webm"))
        output = self.upload_folder / "voice" / message["audio_name"]
        self.assertTrue(output.exists())
        self.assertEqual(output.stat().st_size, len(audio_bytes))
        stored_messages = self.alice.get("/api/dm/bob/messages").get_json()["messages"]
        self.assertEqual(len(stored_messages), 1)
        self.assertEqual(stored_messages[0]["audio_name"], message["audio_name"])

    def test_unauthenticated_private_access_is_rejected(self):
        client = self.app.test_client()
        self.assertEqual(client.get("/api/dm/bob/messages").status_code, 302)

    def test_third_user_cannot_read_another_conversation(self):
        self._accepted_message()
        charlie = self.app.test_client()
        self._login(charlie, self.charlie_id)
        response = charlie.get("/api/dm/alice/messages")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["messages"], [])

    def test_csrf_is_required_for_state_changes(self):
        client = self.app.test_client()
        self._login(client, self.alice_id)
        client.environ_base.pop("HTTP_X_CSRF_TOKEN")
        self.assertEqual(client.post("/api/dm/bob/send", json={"message": "no"}).status_code, 400)

    def test_sender_identity_cannot_be_spoofed(self):
        response = self.alice.post(
            "/api/dm/bob/send",
            json={"message": "hello", "sender": "bob", "user_id": self.bob_id},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["message"]["username"], "alice")

    def test_message_xss_is_returned_as_data_not_markup(self):
        payload = '<img src=x onerror="alert(1)">'
        response = self.alice.post("/api/dm/bob/send", json={"message": payload})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["message"]["message"], payload)
        page = self.alice.get("/dm/bob")
        self.assertNotIn(payload.encode(), page.data)

    def test_sql_injection_like_username_does_not_bypass_lookup(self):
        response = self.alice.get("/api/dm/%27%20OR%201=1--/messages")
        self.assertEqual(response.status_code, 404)

    def test_oversized_message_is_rejected(self):
        response = self.alice.post("/api/dm/bob/send", json={"message": "x" * 2001})
        self.assertEqual(response.status_code, 400)

    def test_invalid_audio_signature_is_rejected(self):
        response = self.alice.post(
            "/api/dm/bob/send",
            data={"voice": (io.BytesIO(b"not audio"), "voice.webm", "audio/webm")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)

    def test_logout_revokes_session(self):
        response = self.alice.post("/auth/logout")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.alice.get("/api/dm/bob/messages").status_code, 302)

    def test_expired_session_is_rejected(self):
        with self.alice.session_transaction() as session:
            session["last_seen"] = 0
        self.assertEqual(self.alice.get("/api/dm/bob/messages").status_code, 401)

    def test_security_headers_are_present(self):
        response = self.alice.get("/")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_production_cookie_configuration_is_secure(self):
        self.assertTrue(ProductionConfig.SESSION_COOKIE_SECURE)
        self.assertTrue(ProductionConfig.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(ProductionConfig.SESSION_COOKIE_SAMESITE, "Lax")

    def test_repeated_failed_logins_are_rate_limited(self):
        client = self.app.test_client()
        client.get("/auth/login")
        with client.session_transaction() as session:
            token = session["_csrf_token"]
        statuses = [
            client.post("/auth/login", data={"username": "nobody", "password": "wrong", "csrf_token": token}).status_code
            for _ in range(6)
        ]
        self.assertEqual(statuses[-1], 429)

    def test_existing_mixed_case_username_can_still_log_in(self):
        client = self.app.test_client()
        client.get("/auth/login")
        with client.session_transaction() as session:
            token = session["_csrf_token"]
        response = client.post(
            "/auth/login",
            data={"username": "legacyuser", "password": "OldPassword123", "csrf_token": token},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_rate_limit_counter_is_atomic_across_concurrent_callers(self):
        key = "concurrent-shared-key"
        with self.app.app_context():
            clear_rate_limit("concurrency", key)

        def attempt(_index):
            with self.app.app_context():
                return rate_limit("concurrency", key, 10, 60)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(24)))
        self.assertEqual(sum(results), 10)

    def test_messages_persist_and_retrieve_from_database(self):
        with self.app.app_context():
            created = save_message("alice", "database-backed")
            db.session.remove()
            restored = get_messages()
            row = db.session.get(Message, created["id"])
            self.assertEqual(restored[-1]["message"], "database-backed")
            self.assertEqual(row.room, "public")
            self.assertEqual(row.sender, "alice")

    def test_legacy_json_import_is_idempotent_and_backed_up(self):
        self.messages_file.write_text(json.dumps([
            {"id": 7, "username": "alice", "message": "legacy public", "time": "2026-01-01T00:00:00+00:00"}
        ]), encoding="utf-8")
        self.private_messages_file.write_text(json.dumps([
            {"id": 9, "sender": "alice", "receiver": "bob", "message": "legacy dm", "status": "accepted", "read_by": ["alice"]}
        ]), encoding="utf-8")
        with self.app.app_context():
            first_count, backups = import_json_messages()
            second_count, _ = import_json_messages()
            self.assertEqual(first_count, 2)
            self.assertEqual(second_count, 0)
            self.assertEqual(Message.query.filter(Message.legacy_source.isnot(None)).count(), 2)
        self.assertEqual(len(backups), 2)
        self.assertTrue(self.messages_file.with_name(f"{self.messages_file.name}.bak").exists())
        self.assertTrue(self.private_messages_file.with_name(f"{self.private_messages_file.name}.bak").exists())


if __name__ == "__main__":
    unittest.main()
