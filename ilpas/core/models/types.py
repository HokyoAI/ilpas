from typing import Dict, Literal, NotRequired, Optional, TypedDict, Union

from pydantic import BaseModel
from pydantic.types import JsonValue

type ConfigurationSupplier = Literal["admin", "user", "callback", "state"]
type Sensitivity = Literal["none", "low", "high"]
type InstanceState = Literal["pending", "healthy", "unhealthy"]

# Type variables for generic typing
type LabelValue = Union[str, int, float, bool, None]
type Labels = Dict[str, LabelValue]
type ValueDict = Dict[ConfigurationSupplier, Dict[str, JsonValue]]


class HashDict(TypedDict):
    hash: str


class HashedValueDict(TypedDict):
    admin: HashDict
    user: Dict[str, JsonValue]
    callback: NotRequired[Dict[str, JsonValue]]
    state: NotRequired[Dict[str, JsonValue]]


class StoreModel(TypedDict):
    encrypted_value: bytes
    labels: Labels
    guid: str


class ValueAndLabels(TypedDict):
    value: HashedValueDict
    labels: Labels
    guid: str


class SearchResult(ValueAndLabels):
    primary_key: str


type KeyTypes = Literal["callback", "webhook"]

type AM = BaseModel


class InstanceConfig[_U: AM, _A: AM, _C: AM, _S: AM](TypedDict):
    admin: _A
    user: _U
    callback: Optional[_C]
    state: Optional[_S]
