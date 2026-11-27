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


@router.post("/embed/lost")
def embed_lost(body: LostText, request: Request) -> Embedded:
    vector = encoder(request).text(body.item_name, body.description)
    category = request.app.state.gemini.classify_lost_text(body.item_name, body.description)
    return Embedded(embedding=vector, category=category)


@router.post("/embed/found")
def embed_found(image: ImageFile, request: Request) -> Embedded:
    with decode_image(image, request.app.state.settings) as rgb:
        vector = encoder(request).image(rgb)
        category = request.app.state.gemini.classify_found_image(rgb)
    return Embedded(embedding=vector, category=category)


@router.post("/match/lost")
def match_lost(body: LostMatch, request: Request) -> Matches:
    item = embed_lost(body, request)
    return Matches(matches=find_matches(
        request.app.state.settings, "FOUND", item.embedding, item.category,
        x=body.location.x, y=body.location.y,
        last_seen_at=body.last_seen_at, noticed_missing_at=body.noticed_missing_at,
    ))


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
    item = embed_found(image, request)
    return Matches(matches=find_matches(
        request.app.state.settings, "LOST", item.embedding, item.category,
        x=location_x, y=location_y, found_at=found_at,
    ))
