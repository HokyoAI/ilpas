from typing import Dict, Literal, TypedDict, Union

from pydantic.types import JsonValue

type ConfigurationSupplier = Literal["admin", "user", "callback"]

type ConfigurationState = Literal["pending", "partial", "complete"]

# Type variables for generic typing
type LabelValue = Union[str, int, float, bool, None]
type Labels = Dict[str, LabelValue]
type ValueDict = Dict[ConfigurationSupplier, Dict[str, JsonValue]]


class ValueAndLabels(TypedDict):
    value: ValueDict
    labels: Labels


class SearchResult(ValueAndLabels):
    primary_key: str
