from dataclasses import dataclass
from typing import Dict, Generic, TypeVar

from pydantic import BaseModel

from .display import Display
from .endpoint import Endpoint
from .webhook import Webhook

_AC = TypeVar("_AC", bound=BaseModel)


@dataclass
class Specification(Generic[_AC]):
    guid: str
    display: Display
    endpoints: Dict[str, Endpoint]
    webhooks: Dict[str, Webhook]
    admin_config_model: type[_AC]


@dataclass
class Integration(Generic[_AC]):
    spec: Specification[_AC]
    admin_config: _AC
    user_config_model: type[BaseModel]
