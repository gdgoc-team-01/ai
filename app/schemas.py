from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints


def check_calendar_time(value: str) -> str:
    datetime.fromisoformat(value)
    return value


def check_coordinate(value: float) -> float:
    if round(value, 2) != value:
        raise ValueError("Use at most two decimal places")
    return value


ItemName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
KstMinute = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:00\+09:00$"),
    AfterValidator(check_calendar_time),
]
MapX = Annotated[float, Field(ge=0, le=1252, allow_inf_nan=False), AfterValidator(check_coordinate)]
MapY = Annotated[float, Field(ge=0, le=1298, allow_inf_nan=False), AfterValidator(check_coordinate)]


class Location(BaseModel):
    x: MapX
    y: MapY


class LostText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_name: ItemName
    description: Description


class LostMatch(LostText):
    last_seen_at: KstMinute
    noticed_missing_at: KstMinute
    location: Location


class Embedded(BaseModel):
    embedding: Annotated[list[float], Field(min_length=768, max_length=768)]


class Candidate(BaseModel):
    post_id: int
    score: float


class Matches(BaseModel):
    matches: list[Candidate]

