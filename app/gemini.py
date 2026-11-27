import json
import logging
from io import BytesIO
from pathlib import Path
from threading import BoundedSemaphore

from google import genai
from google.genai import types
from PIL import Image

from .config import Settings
from .schemas import CategoryCode, Classification


logger = logging.getLogger("uvicorn.error")
PROMPTS = Path(__file__).with_name("prompts")


def image_part(rgb: Image.Image) -> types.Part:
    with BytesIO() as buffer:
        # Preserve fine lettering and omit metadata inherited from the upload.
        rgb.save(buffer, format="PNG", exif=b"", icc_profile=None)
        return types.Part.from_bytes(data=buffer.getvalue(), mime_type="image/png")


class Gemini:
    def __init__(self, settings: Settings):
        self.prompts = {
            name: (PROMPTS / f"{name}_v1.txt").read_text(encoding="utf-8")
            for name in ("lost_classification", "found_classification")
        }
        self.model = settings.gemini_model
        self.slots = BoundedSemaphore(4)
        self.client = None
        key = settings.gemini_api_key
        if key and key.get_secret_value() and self.model:
            try:
                self.client = genai.Client(
                    vertexai=False, api_key=key.get_secret_value(),
                    http_options=types.HttpOptions(timeout=30_000, retry_options=types.HttpRetryOptions(attempts=2)),
                )
            except Exception as exc:
                logger.warning("Gemini initialization failed (%s); using SigLIP2 fallback", type(exc).__name__)
        if not self.client:
            logger.warning("Gemini unavailable; category defaults to OTHER")

    def close(self):
        if self.client:
            self.client.close()

    def _classify(self, task: str, contents: list) -> CategoryCode:
        if not self.client:
            return "OTHER"
        if not self.slots.acquire(blocking=False):
            logger.warning("Gemini %s skipped: concurrency limit", task)
            return "OTHER"
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self.prompts[task], response_mime_type="application/json",
                    response_json_schema=Classification.model_json_schema(),
                ),
            )
            return Classification.model_validate_json(response.text or "").category
        except Exception as exc:
            # SDK errors and validation details can contain the original input.
            logger.warning("Gemini %s failed (%s, status=%s)", task, type(exc).__name__, getattr(exc, "code", None))
            return "OTHER"
        finally:
            self.slots.release()

    def classify_lost_text(self, item_name: str, description: str) -> CategoryCode:
        text = json.dumps({"item_name": item_name, "description": description}, ensure_ascii=False)
        return self._classify("lost_classification", [text])

    def classify_found_image(self, rgb: Image.Image) -> CategoryCode:
        if not self.client:
            return "OTHER"
        return self._classify("found_classification", [image_part(rgb)])
