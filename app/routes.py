from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile

from .embeddings import Encoder
from .repository import find_matches
from .schemas import Embedded, ItemName, KstMinute, LostMatch, LostText, MapX, MapY, Matches
from .uploads import decode_image, single_image


router = APIRouter(prefix="/ai")
ImageFile = Annotated[UploadFile, Depends(single_image)]


def encoder(request: Request) -> Encoder:
    if request.app.state.encoder is None:
        raise HTTPException(503, "AI service temporarily unavailable")
    return request.app.state.encoder


def image_vector(request: Request, image: UploadFile) -> list[float]:
    with decode_image(image, request.app.state.settings) as rgb:
        return encoder(request).image(rgb)


@router.post("/embed/lost")
def embed_lost(body: LostText, request: Request) -> Embedded:
    return Embedded(embedding=encoder(request).text(body.item_name, body.description))


@router.post("/embed/found")
def embed_found(image: ImageFile, request: Request) -> Embedded:
    return Embedded(embedding=image_vector(request, image))


@router.post("/match/lost")
def match_lost(body: LostMatch, request: Request) -> Matches:
    vector = encoder(request).text(body.item_name, body.description)
    return Matches(matches=find_matches(request.app.state.settings, "FOUND", vector))


@router.post("/match/found")
def match_found(
    request: Request,
    image: ImageFile,
    item_name: Annotated[ItemName, Form()],
    found_at: Annotated[KstMinute, Form()],
    location_x: Annotated[MapX, Form()],
    location_y: Annotated[MapY, Form()],
    description: Annotated[str | None, Form()] = None,
) -> Matches:
    vector = image_vector(request, image)
    return Matches(matches=find_matches(request.app.state.settings, "LOST", vector))

