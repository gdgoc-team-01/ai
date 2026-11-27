import json
import os
from io import BytesIO
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch

import httpx
import psycopg
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr

from app.config import Settings
from app.gemini import Gemini
from app.main import app
from app.schemas import Candidate


LOST = {"item_name": "지갑", "description": "JW 각인", "last_seen_at": "2026-11-24T12:00:00+09:00",
        "noticed_missing_at": "2026-11-24T13:00:00+09:00", "location": {"x": 10, "y": 20}}
FOUND = {"item_name": "습득물", "found_at": "2026-11-24T13:00:00+09:00", "location_x": 10, "location_y": 20}
VECTOR = [1.0] + [0.0] * 767


def png():
    with BytesIO() as buf, Image.new("RGB", (2, 2), "red") as im:
        im.save(buf, "PNG")
        return buf.getvalue()


def json_reply(**fields):
    return Mock(text=json.dumps(fields))


class MatchingTests(TestCase):
    def setUp(self):
        settings = Settings(_env_file=None, gemini_api_key=SecretStr("test"), gemini_model="gemini-3.6-flash",
                            max_image_bytes=1024, allowed_image_formats={"PNG"})
        self.enterContext(patch("app.main.Settings", return_value=settings))
        sdk = self.enterContext(patch("app.gemini.genai.Client")).return_value
        self.generate = sdk.models.generate_content
        encoder = self.enterContext(patch("app.main.Encoder")).return_value
        encoder.text.return_value = encoder.image.return_value = VECTOR
        self.find = self.enterContext(patch("app.routes.find_matches"))
        self.rows = [
            Candidate(post_id=i, score=1-i/30) for i in range(1, 21)
        ]
        self.find.return_value = self.rows
        self.client = self.enterContext(TestClient(app))

    def found(self, action):
        return self.client.post("/ai/" + action + "/found", data=FOUND if action == "match" else {},
                                files={"image": ("sample.png", png(), "image/png")})

    def check_order(self, response, order):
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"matches": [
            {"post_id": i, "score": self.rows[i-1].score} for i in order
        ]})

    def test_matching_calls_only_the_input_classifier(self):
        self.generate.return_value = json_reply(category="WALLET")
        self.check_order(self.client.post("/ai/match/lost", json=LOST), range(1, 21))
        self.assertEqual(self.find.call_args.args[1:], ("FOUND", VECTOR, "WALLET"))
        self.assertEqual(self.find.call_args.kwargs, dict(x=10, y=20, last_seen_at=LOST["last_seen_at"],
                                                         noticed_missing_at=LOST["noticed_missing_at"]))
        self.check_order(self.found("match"), range(1, 21))
        self.assertEqual(self.find.call_args.args[1:], ("LOST", VECTOR, "WALLET"))
        self.assertEqual(self.find.call_args.kwargs, dict(x=10, y=20, found_at=FOUND["found_at"]))
        self.assertEqual(self.generate.call_count, 2)

    def test_classification_failure_and_empty_matches(self):
        self.find.return_value = []
        self.generate.side_effect = [RuntimeError(), json_reply(category="UNKNOWN")]
        for response in (self.client.post("/ai/match/lost", json=LOST), self.found("match")):
            self.assertEqual(response.json(), {"matches": []})
        for call in self.find.call_args_list:
            self.assertEqual(call.args[-1], "OTHER")

    def test_embedding_response_and_separate_prompts(self):
        self.generate.side_effect = [json_reply(category="WALLET"), json_reply(category="BAG")]
        body = {k: LOST[k] for k in ("item_name", "description")}
        self.assertEqual(self.client.post("/ai/embed/lost", json=body).json(),
                         {"embedding": VECTOR, "category": "WALLET"})
        self.assertEqual(self.found("embed").json(), {"embedding": VECTOR, "category": "BAG"})
        for call, task in zip(self.generate.call_args_list, ("lost_classification", "found_classification"), strict=True):
            self.assertEqual(call.kwargs["model"], "gemini-3.6-flash")
            self.assertEqual(call.kwargs["config"].system_instruction, app.state.gemini.prompts[task])

    def test_db_failure_is_service_unavailable(self):
        self.find.side_effect = psycopg.OperationalError()
        self.generate.return_value = json_reply(category="WALLET")
        response = self.client.post("/ai/match/lost", json=LOST)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "AI service temporarily unavailable"})

    def test_invalid_inputs_before_analysis(self):
        invalid = dict(LOST, noticed_missing_at="2026-11-23T12:00:00+09:00")
        self.assertEqual(self.client.post("/ai/match/lost", json=invalid).status_code, 422)
        for data, status in [(b"bad", 415), (bytes(1025), 413)]:
            result = self.client.post("/ai/match/found", data=FOUND, files={"image": ("bad.png", data)})
            self.assertEqual(result.status_code, status)
        self.generate.assert_not_called()
        self.find.assert_not_called()

    def test_saturated_gemini_keeps_embedding(self):
        ai = app.state.gemini
        for _ in range(4):
            self.assertTrue(ai.slots.acquire(blocking=False))
            self.addCleanup(ai.slots.release)
        response = self.client.post("/ai/embed/lost", json={"item_name": "지갑", "description": "검은색"})
        self.assertEqual(response.json(), {"embedding": VECTOR, "category": "OTHER"})
        self.generate.assert_not_called()


class GeminiRequestTests(TestCase):
    def test_sdk_serializes_both_inputs(self):
        ai = Gemini(Settings(_env_file=None, gemini_api_key=SecretStr("test")))
        self.addCleanup(ai.close)
        payloads = []

        def reply(request, **kwargs):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, request=request, json={"candidates": [
                {"content": {"role": "model", "parts": [{"text": '{"category":"BAG"}'}]}}
            ]})

        with patch("httpx.Client.send", side_effect=reply), Image.new("RGB", (4, 4)) as rgb:
            self.assertEqual(ai.classify_lost_text("가방", "검은색"), "BAG")
            self.assertEqual(ai.classify_found_image(rgb), "BAG")
        for payload, task in zip(payloads, ("lost_classification", "found_classification"), strict=True):
            self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], ai.prompts[task])
            schema = payload["generationConfig"]["responseJsonSchema"]
            self.assertEqual(set(schema["properties"]), {"category"})
            self.assertEqual(len(schema["properties"]["category"]["enum"]), 11)
        self.assertEqual(payloads[1]["contents"][0]["parts"][0]["inlineData"]["mimeType"], "image/png")


@skipUnless(os.getenv("RUN_GEMINI_LIVE") == "1", "Set RUN_GEMINI_LIVE=1 for real Gemini calls")
class GeminiLiveTests(TestCase):
    def test_synthetic_inputs(self):
        ai = Gemini(Settings())
        self.addCleanup(ai.close)
        self.assertIsNotNone(ai.client)
        self.assertEqual(ai.classify_lost_text("검은색 지갑", "JW 각인"), "WALLET")
        with Image.new("RGB", (32, 32), "white") as rgb:
            self.assertEqual(ai.classify_found_image(rgb), "OTHER")
