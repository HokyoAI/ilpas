from typing import Dict, Literal

from pydantic import BaseModel

from .types import JsonValue


class BaseConfigResponse(BaseModel):
    config: Dict[str, JsonValue]


class RedirectRequired(BaseConfigResponse):
    redirect_required: Literal[True] = True
    redirect_uri: str


class RedirectNotRequired(BaseConfigResponse):
    redirect_required: Literal[False] = False
    redirect_uri: None = None


type ConfigResponse = RedirectRequired | RedirectNotRequired
