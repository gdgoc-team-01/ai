from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator


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

    @model_validator(mode="after")
    def validate_interval(self):
        if self.last_seen_at > self.noticed_missing_at:
            raise ValueError("last_seen_at must not be later than noticed_missing_at")
        return self


CategoryCode = Literal[
    "WALLET", "EARPHONES", "BAG", "UMBRELLA", "CARD", "COSMETICS",
    "ELECTRONICS", "KEY", "ACCESSORY", "CLOTHING", "OTHER",
]


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: CategoryCode


class Embedded(Classification):
    embedding: Annotated[list[float], Field(min_length=768, max_length=768)]


class Candidate(BaseModel):
    post_id: int
    score: float


class Matches(BaseModel):
    matches: list[Candidate]

