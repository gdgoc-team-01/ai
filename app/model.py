import torch
from transformers import AutoModel, AutoProcessor


MODEL_ID = "google/siglip2-base-patch16-224"


def load_encoder():
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModel.from_pretrained(MODEL_ID, dtype=torch.float32)
    return model.to("cpu").eval(), processor

