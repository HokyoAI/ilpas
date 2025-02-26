from dataclasses import dataclass
from typing import Dict, Generic, Optional, TypeVar

from pydantic import BaseModel
from pydantic.types import JsonValue

from .specification import Specification

_T = TypeVar("_T", bound=BaseModel)


@dataclass
class Integration(Generic[_T]):
    spec: Specification[_T]
    final_config_model: type[_T]
    supplied_config: Dict[str, JsonValue]
