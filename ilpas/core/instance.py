from typing import Dict, Generic, Literal, Optional, TypeVar, cast, overload

from pydantic import BaseModel, ValidationError, create_model
from pydantic.fields import FieldInfo

from .integration import Integration
from .models.base_model_extras import (
    DEFAULT_SENSITIVE,
    DEFAULT_SUPPLIER,
    DEFAULT_TRIGGER_CALLBACK,
)
from .models.errors import BadDataError, IlpasValueError
from .models.types import ConfigurationSupplier, InstanceState, JsonValue, Sensitivity
from .store import Labels, Store

_T = TypeVar("_T", bound=BaseModel)


class Instance(Generic[_T]):

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

    def _get_field_sensitivity(self, field_info: FieldInfo) -> Sensitivity:
        """Check if a field is sensitive based on its FieldInfo"""
        sens_string = self._get_extra_field(
            field_info, "sensitive", str, DEFAULT_SENSITIVE
        )
        if sens_string not in ["none", "low", "high"]:
            raise ValueError(f"Invalid sensitivity {sens_string}")
        else:
            return cast(Sensitivity, sens_string)

    def _get_field_supplier(self, field_info: FieldInfo) -> ConfigurationSupplier:
        """Get the supplier for a field based on its FieldInfo"""
        supplier_string = self._get_extra_field(
            field_info, "supplier", str, DEFAULT_SUPPLIER
        )
        if supplier_string not in ["user", "admin", "callback"]:
            raise ValueError(f"Invalid supplier {supplier_string}")
        else:
            return cast(ConfigurationSupplier, supplier_string)

    def _is_field_callback_trigger(self, field_info: FieldInfo) -> bool:
        """Check if a field triggers a callback based on its FieldInfo"""
        return self._get_extra_field(
            field_info, "triggers_callback", bool, DEFAULT_TRIGGER_CALLBACK
        )

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

    def build_model(self) -> Optional[_T]:
        """Try to build the final configuration model"""
        try:
            return self.config_class(**self._config_data)
        except ValidationError as e:
            return None

    @overload
    def __init__(
        self,
        integration: Integration,
        *,
        namespace: Optional[str],
        primary_key: str,
        labels: None = None,
        temporary: Literal[False] = False,
    ) -> None: ...

    @overload
    def __init__(
        self,
        integration: Integration,
        *,
        namespace: Optional[str],
        primary_key: None = None,
        labels: Labels,
        temporary: Literal[False] = False,
    ) -> None: ...

    @overload
    def __init__(
        self,
        integration: Integration,
        *,
        namespace: None = None,
        primary_key: None = None,
        labels: None = None,
        temporary: Literal[True] = True,
    ) -> None: ...

    def __init__(
        self,
        integration: Integration[_T],
        *,
        namespace: Optional[str] = None,
        primary_key: Optional[str] = None,
        labels: Optional[Labels] = None,
        temporary: bool = False,
    ):
        self.integration = integration
        self.config_class = integration.final_config_model
        self.guid: str = integration.spec.guid
        self.namespace: Optional[str] = namespace
        self.primary_key = primary_key
        self.labels = labels
        self.temporary = temporary
        if primary_key is None and labels is None and not temporary:
            raise IlpasValueError(
                "must provide either primary_key or labels, or set temporary=True"
            )
        self._config_data: Dict[str, JsonValue] = {}
        self._state: InstanceState = "pending"
        admin_model = self.get_model("admin")
        admin_model(**integration.supplied_config)  # validate admin supplied config
        self.add_configuration("admin", self.integration.supplied_config)

    @classmethod
    async def restore_by_primary_key(
        cls,
        *,
        store: Store,
        integration: Integration,
        primary_key: str,
        namespace: Optional[str],
    ) -> "Instance":
        """Restore the configuration from the store"""
        data = await store.get_by_primary_key(
            primary_key=primary_key, namespace=namespace
        )
        labels = data["labels"]
        value = data["value"]
        result = cls(
            integration,
            primary_key=primary_key,
            namespace=namespace,
        )
        result.labels = labels
        for supplier, config in value.items():
            result.add_configuration(supplier, config)
        return result

    @classmethod
    async def restore_by_labels(
        cls,
        *,
        store: Store,
        integration: Integration,
        labels: Labels,
        namespace: Optional[str],
    ) -> "Instance":
        """Restore the configuration from the store"""
        guid = integration.spec.guid
        data = await store.get_by_labels(guid=guid, labels=labels, namespace=namespace)
        value = data["value"]
        primary_key = data["primary_key"]
        result = cls(
            integration,
            labels=labels,
            namespace=namespace,
        )
        result.primary_key = primary_key
        for supplier, config in value.items():
            result.add_configuration(supplier, config)
        return result

    @classmethod
    async def restore_by_discovery_key(
        cls,
        *,
        store: Store,
        integration: Integration,
        key_type: Literal["callback", "webhook"],
        key: str,
    ):
        full_key = f"{integration.spec.guid}:{key_type}:{key}"
        instance_ids = await store.instance_discovery(key=full_key)
        if not instance_ids:
            raise BadDataError("No instances found")
        primary_key = instance_ids[0]
        namespace = instance_ids[1]
        return await cls.restore_by_primary_key(
            store=store,
            integration=integration,
            primary_key=primary_key,
            namespace=namespace,
        )

    def _update_state(self) -> None:
        """
        Update the configuration state based on current data.
        """

        model = self.build_model()

        if model is not None:
            self._state = "healthy"
        else:
            self._state = "pending"

    def add_configuration(
        self, supplier: ConfigurationSupplier, config_data: Dict[str, JsonValue]
    ):
        model = self.get_model(supplier)
        model(**config_data)
        self._config_data.update(config_data)
        self._update_state()

    def serialize_config(
        self, supplier: ConfigurationSupplier, redact: bool = True
    ) -> Dict[str, JsonValue]:
        supplier_model = self.get_model(supplier)
        supplier_data = {}
        for field_name, field_info in supplier_model.__pydantic_fields__.items():
            sensitivity = self._get_field_sensitivity(field_info)
            if redact and sensitivity == "high":
                continue
            if field_name in self._config_data:
                supplier_data[field_name] = self._config_data[field_name]

        return supplier_data

    async def save(self, store: Store):
        if self.temporary:
            raise IlpasValueError("Cannot save temporary instance")
        user_config = self.serialize_config("user", redact=False)
        callback_config = self.serialize_config("callback", redact=False)
        # admin config is not saved to the store, it is always resupplied through code
        value: Dict[ConfigurationSupplier, Dict[str, JsonValue]] = {
            "user": user_config,
            "callback": callback_config,
        }
        if self.primary_key is not None:
            await store.put_by_primary_key(
                value=value,
                guid=self.guid,
                labels=self.labels if self.labels is not None else {},
                namespace=self.namespace,
                primary_key=self.primary_key,
            )
        elif self.labels is not None:
            await store.put_by_labels(
                value=value,
                guid=self.guid,
                labels=self.labels,
                namespace=self.namespace,
            )
        else:
            raise IlpasValueError("Instance must have primary_key or labels")

    async def delete(self, store: Store):
        """TODO"""
        pass
