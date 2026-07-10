import io
import math
import shutil
import struct
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.chat.routes import _ffmpeg_executable
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
        shutil.rmtree(self.upload_folder, ignore_errors=True)

        class TestConfig:
            TESTING = True
            SECRET_KEY = "test-secret"
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            MESSAGES_FILE = str(self.messages_file)
            PRIVATE_MESSAGES_FILE = str(self.private_messages_file)
            UPLOAD_FOLDER = str(self.upload_folder)
            MAX_CONTENT_LENGTH = 2 * 1024 * 1024
            FORCE_HTTPS = False
            SESSION_COOKIE_SECURE = False

        self.app = create_app(TestConfig)
        with self.app.app_context():
            alice = User(username="alice")
            alice.set_password("password1")
            bob = User(username="bob")
            bob.set_password("password2")
            db.session.add_all([alice, bob])
            db.session.commit()
            self.alice_id = alice.id
            self.bob_id = bob.id

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
        shutil.rmtree(self.upload_folder, ignore_errors=True)

    @staticmethod
    def _login(client, user_id):
        with client.session_transaction() as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True

    def _accepted_message(self):
        response = self.alice.post("/api/dm/bob/send", json={"message": "Hello"})
        self.assertEqual(response.status_code, 201)
        message_id = response.get_json()["message"]["id"]
        self.assertEqual(self.bob.post("/api/dm/alice/accept").status_code, 200)
        return message_id

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

    def test_voice_upload_is_converted_to_m4a(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(8000)
            samples = (
                int(12000 * math.sin(2 * math.pi * 440 * index / 8000))
                for index in range(4000)
            )
            wav_file.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
        audio.seek(0)

        response = self.alice.post(
            "/api/dm/bob/send",
            data={"voice": (audio, "voice.wav", "audio/wav")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 201)
        message = response.get_json()["message"]
        self.assertEqual(message["message_type"], "voice")
        self.assertTrue(message["audio_name"].endswith(".m4a"))
        output = self.upload_folder / "voice" / message["audio_name"]
        self.assertTrue(output.exists())
        self.assertGreater(output.stat().st_size, 0)

    def test_voice_conversion_prefers_system_ffmpeg(self):
        with (
            patch.dict("os.environ", {"FFMPEG_BINARY": ""}),
            patch("app.chat.routes.shutil.which", return_value="/usr/bin/ffmpeg"),
        ):
            self.assertEqual(_ffmpeg_executable(), "/usr/bin/ffmpeg")


if __name__ == "__main__":
    unittest.main()
