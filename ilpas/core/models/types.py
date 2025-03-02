from typing import Dict, Literal, Optional, TypedDict, Union

from pydantic import BaseModel
from pydantic.types import JsonValue

type ConfigurationSupplier = Literal["admin", "user", "callback"]
type Sensitivity = Literal["none", "low", "high"]
type InstanceState = Literal["pending", "healthy", "unhealthy"]

# Type variables for generic typing
type LabelValue = Union[str, int, float, bool, None]
type Labels = Dict[str, LabelValue]
type ValueDict = Dict[ConfigurationSupplier, Dict[str, JsonValue]]


class ValueAndLabels(TypedDict):
    value: ValueDict
    labels: Labels
    guid: str


class SearchResult(ValueAndLabels):
    primary_key: str


type KeyTypes = Literal["callback", "webhook"]

type AM = BaseModel
