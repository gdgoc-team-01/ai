from unittest import IsolatedAsyncioTestCase
from unittest.mock import call, patch, sentinel

from fastapi import FastAPI

from app.main import lifespan


class EncoderStartupTests(IsolatedAsyncioTestCase):
    async def test_first_success_ends_retries(self):
        for failures in (0, 1, 2):
            with self.subTest(failures=failures):
                app = FastAPI()
                outcomes = [RuntimeError("model unavailable")] * failures + [sentinel.encoder]
                with patch("app.main.Encoder", side_effect=outcomes) as encoder, patch("app.main.sleep") as sleep:
                    async with lifespan(app):
                        self.assertIs(app.state.encoder, sentinel.encoder)
                    self.assertIsNone(app.state.encoder)
                    self.assertEqual(encoder.call_count, failures + 1)
                    self.assertEqual(sleep.await_args_list, [call(2)] * failures)

    async def test_third_failure_aborts_startup(self):
        app = FastAPI()
        error = RuntimeError("model unavailable")
        with patch("app.main.Encoder", side_effect=error) as encoder, patch("app.main.sleep") as sleep:
            with self.assertLogs("uvicorn.error", level="WARNING") as logs, self.assertRaises(RuntimeError) as raised:
                async with lifespan(app):
                    self.fail("Startup completed without an encoder")
            self.assertIs(raised.exception, error)
            self.assertEqual(encoder.call_count, 3)
            self.assertEqual(sleep.await_args_list, [call(2), call(2)])
            for attempt, record in enumerate(logs.records, start=1):
                self.assertIn(f"({attempt}/3)", record.getMessage())
            self.assertIn("aborting startup", logs.records[-1].getMessage())
