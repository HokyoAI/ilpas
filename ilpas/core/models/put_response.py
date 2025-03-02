from typing import Dict, Literal

from pydantic import BaseModel

from .types import JsonValue


class BasePutResponse(BaseModel):
    config: Dict[str, JsonValue]


class RedirectRequired(BasePutResponse):
    redirect_required: Literal[True] = True
    redirect_uri: str


class RedirectNotRequired(BasePutResponse):
    redirect_required: Literal[False] = False
    redirect_uri: None = None


type PutResponse = RedirectRequired | RedirectNotRequired
