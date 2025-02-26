from copy import deepcopy
from typing import Dict, Generic, Literal, Optional, Type, TypeVar, cast, overload

from pydantic import BaseModel, ValidationError, create_model
from pydantic.fields import FieldInfo
from pydantic.types import JsonValue

from .models.errors import BadDataError, IlpasValueError
from .models.types import ConfigurationState, ConfigurationSupplier
from .store import Labels, Store

DEFAULT_SUPPLIER: ConfigurationSupplier = "user"
DEFAULT_SENSITIVE: bool = False


class NoConfig(BaseModel):
    model_config = {"extra": "forbid"}


def extras(
    supplier: ConfigurationSupplier = DEFAULT_SUPPLIER,
    sensitive: bool = DEFAULT_SENSITIVE,
) -> Dict[str, JsonValue]:
    return {"supplier": supplier, "sensitive": sensitive}


_T = TypeVar("_T", bound=BaseModel)


class InstanceManager(Generic[_T]):

    def _is_field_required(self, field_info: FieldInfo) -> bool:
        """Check if a field is required based on its FieldInfo"""
        return field_info.is_required()

    def _get_extra_field[
        T
    ](
        self, field_info: FieldInfo, field_name: str, field_type: type[T], default: T
    ) -> T:
        if not field_info.json_schema_extra:
            return default
        if isinstance(field_info.json_schema_extra, dict):
            value = field_info.json_schema_extra.get(field_name, None)
            if value is None:
                return default
            elif isinstance(value, field_type):
                return value
            else:
                raise ValueError(
                    f"field {field_info.title} json_schema_extra.{field_name} must be a {field_type}"
                )
        else:
            raise ValueError(
                f"field {field_info.title} json_schema_extra must be a dict, callable is not supported"
            )

    def _is_field_sensitive(self, field_info: FieldInfo) -> bool:
        """Check if a field is sensitive based on its FieldInfo"""
        return self._get_extra_field(field_info, "sensitive", bool, DEFAULT_SENSITIVE)

    def _get_field_supplier(self, field_info: FieldInfo) -> ConfigurationSupplier:
        """Get the supplier for a field based on its FieldInfo"""
        supplier_string = self._get_extra_field(
            field_info, "supplier", str, DEFAULT_SUPPLIER
        )
        if supplier_string not in ["user", "admin", "callback"]:
            raise ValueError(f"Invalid supplier {supplier_string}")
        else:
            return cast(ConfigurationSupplier, supplier_string)

    @overload
    def __init__(
        self,
        config_class: Type[_T],
        guid: str,
        *,
        namespace: Optional[str],
        primary_key: str,
        labels: None = None,
        temporary: Literal[False] = False,
    ) -> None: ...

    @overload
    def __init__(
        self,
        config_class: Type[_T],
        guid: str,
        *,
        namespace: Optional[str],
        primary_key: None = None,
        labels: Labels,
        temporary: Literal[False] = False,
    ) -> None: ...

    @overload
    def __init__(
        self,
        config_class: Type[_T],
        guid: str,
        *,
        namespace: None = None,
        primary_key: None = None,
        labels: None = None,
        temporary: Literal[True] = True,
    ) -> None: ...

    def __init__(
        self,
        config_class: Type[_T],
        guid: str,
        *,
        namespace: Optional[str] = None,
        primary_key: Optional[str] = None,
        labels: Optional[Labels] = None,
        temporary: bool = False,
    ):
        self.config_class = config_class
        self.guid: str = guid
        self.namespace: Optional[str] = namespace
        self.primary_key = primary_key
        self.labels = labels
        self.temporary = temporary
        if primary_key is None and labels is None and not temporary:
            raise IlpasValueError(
                "must provide either primary_key or labels, or set temporary=True"
            )
        self._config_data: Dict[str, JsonValue] = {}
        self._state: ConfigurationState = "pending"

    @staticmethod
    def _add_guid_to_labels_copy(guid: str, labels: Labels):
        result = deepcopy(labels)
        result["guid"] = guid
        return result

    @staticmethod
    def _remove_guid_from_labels_copy(labels: Labels):
        result = deepcopy(labels)
        if "guid" not in result:
            raise BadDataError("Expected to find guid in labels but did not")
        result.pop("guid")
        return result

    @classmethod
    async def restore_by_primary_key(
        cls,
        store: Store,
        config_class: type[_T],
        guid: str,
        primary_key: str,
        namespace: Optional[str],
    ) -> "InstanceManager":
        """Restore the configuration from the store"""
        data = await store.get_by_primary_key(primary_key, namespace)
        all_labels = data["labels"]
        original_labels = cls._remove_guid_from_labels_copy(
            all_labels
        )  # guid should be stored in the labels
        value = data["value"]
        result = cls(
            config_class,
            guid=guid,
            primary_key=primary_key,
            namespace=namespace,
        )
        result.labels = original_labels
        for supplier, config in value.items():
            result.add_configuration(supplier, config)
        return result

    @classmethod
    async def restore_by_labels(
        cls,
        store: Store,
        config_class: type[_T],
        guid: str,
        labels: Labels,
        namespace: Optional[str],
    ) -> "InstanceManager":
        """Restore the configuration from the store"""
        all_labels = cls._add_guid_to_labels_copy(
            guid, labels
        )  # guid should be stored in the labels
        data = await store.get_by_labels(all_labels, namespace)
        value = data["value"]
        primary_key = data["primary_key"]
        result = cls(
            config_class,
            guid=guid,
            labels=labels,
            namespace=namespace,
        )
        result.primary_key = primary_key
        for supplier, config in value.items():
            result.add_configuration(supplier, config)
        return result

    def get_model(self, supplier: ConfigurationSupplier) -> type[BaseModel]:
        """Generate a Pydantic model for fields from a specific source"""
        field_defs = {}

        for field_name, field_info in self.config_class.__pydantic_fields__.items():
            field_supplier = self._get_field_supplier(field_info)
            if field_supplier != supplier:
                continue
            else:
                field_defs[field_name] = (field_info.annotation, field_info)

        title = f"{self.config_class.__name__}[{supplier}]"

        DynamicModel = create_model(title, **field_defs)
        return DynamicModel

    def get_json_schema(self, supplier: ConfigurationSupplier) -> Dict[str, JsonValue]:
        """Generate JSON schema for fields from a specific source"""

        return self.get_model(supplier=supplier).model_json_schema()

    def serialize_config(self, supplier: ConfigurationSupplier) -> Dict[str, JsonValue]:
        supplier_model = self.get_model(supplier)
        supplier_data = {
            field_name: self._config_data[field_name]
            for field_name in supplier_model.__pydantic_fields__.keys()
            if field_name in self._config_data
        }
        return supplier_data

    def build_model(self) -> Optional[_T]:
        """Try to build the final configuration model"""
        try:
            return self.config_class(**self._config_data)
        except ValidationError as e:
            return None

    def _update_state(self) -> None:
        """Update the configuration state based on requirements and provided data"""

        model = self.build_model()

        if model is not None:
            self._state = "complete"
        elif len(self._config_data) > 0:
            self._state = "partial"
        else:
            self._state = "pending"

    def add_configuration(
        self, supplier: ConfigurationSupplier, config_data: Dict[str, JsonValue]
    ):
        model = self.get_model(supplier)
        model(**config_data)
        self._config_data.update(config_data)
        self._update_state()

    async def _persist_state_by_primary_key(
        self, store: Store, primary_key: str, namespace: Optional[str]
    ):
        pass
