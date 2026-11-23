from threading import Lock

import torch
from PIL import Image
from torch.nn.functional import normalize
from transformers import AutoModel, AutoProcessor


MODEL_ID = "google/siglip2-base-patch16-224"


def load_encoder():
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModel.from_pretrained(MODEL_ID, dtype=torch.float32)
    return model.to("cpu").eval(), processor


class Encoder:
    def __init__(self):
        self.model, self.processor = load_encoder()
        self.max_length = self.model.config.text_config.max_position_embeddings
        self.lock = Lock()

    @staticmethod
    def _unit_vector(features) -> list[float]:
        if not isinstance(features, torch.Tensor):
            features = features.pooler_output
        features = features.float()
        if features.shape != (1, 768) or not torch.isfinite(features).all():
            raise ValueError("Invalid SigLIP2 embedding")
        if features.norm() == 0:
            raise ValueError("Zero SigLIP2 embedding")
        return normalize(features, dim=1)[0].tolist()

    @torch.inference_mode()
    def text(self, item_name: str, description: str) -> list[float]:
        query = f"{item_name.strip()} {description.strip()}".lower()
        with self.lock:
            inputs = self.processor(
                text=[query],
                padding="max_length",
                max_length=self.max_length,
                truncation=True,
                return_tensors="pt",
            )
            return self._unit_vector(self.model.get_text_features(**inputs))

    @torch.inference_mode()
    def image(self, image: Image.Image) -> list[float]:
        with self.lock:
            inputs = self.processor(images=[image], return_tensors="pt")
            return self._unit_vector(self.model.get_image_features(**inputs))

