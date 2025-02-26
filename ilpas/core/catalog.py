import logging
import warnings
from enum import StrEnum
from typing import Annotated, Awaitable, Callable, Dict

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from pydantic.types import JsonValue

from .integration import Integration
from .manager import InstanceManager
from .store import Labels, Store

logger = logging.getLogger(__name__)


class Catalog:
    """
    Catalog of integrations.

    IMPORTANT: Claude caught this one.
    See https://stackoverflow.com/questions/78110125/how-to-dynamically-create-fastapi-routes-handlers-for-a-list-of-pydantic-models
    Helper functions must be used to create routes handlers for each integration because of scoping and closure issues.
    """

    def __init__(
        self,
        store: Store,
        authenticate: Callable[..., Awaitable[tuple[str, Labels] | None]],
    ):
        self.finalized: bool = False
        self._store = store
        self._authenticate = authenticate
        self._integration_registry: Dict[str, Integration] = {}

    def add_integration(
        self,
        integration: Integration,
    ):
        if self.finalized:
            raise RuntimeError("Catalog is finalized, cannot add more integrations")
        if integration.spec.guid in self._integration_registry:
            raise ValueError(f"Integration {integration.spec.guid} already exists")
        temp_manager = InstanceManager(
            integration.final_config_model, integration.spec.guid
        )
        admin_model = temp_manager.get_model("admin")
        admin_model(**integration.supplied_config)  # validate admin supplied config
        self._integration_registry[integration.spec.guid] = integration

    def finalize(self):
        if self.finalized:
            raise RuntimeError("Catalog is already finalized")
        self.finalized = True
        self._create_enabled_integrations_enum()  # order matters!
        self._create_dependency_functions()

    def _create_enabled_integrations_enum(self):
        members = {key.upper(): key for key in self._integration_registry.keys()}
        self._enabled_integrations_enum = StrEnum("EnabledIntegrations", members)

    def _create_dependency_functions(self):
        self._require_authentication_dep = (
            self._build_require_authentication_dependency()
        )
        self._validate_guid_dep = self._build_validate_guid_dependency()
        self._load_manager_dep = self._build_load_manager_dependency()
        self._temp_manager_dep = self._build_temp_manager_dependency()

    def _build_require_authentication_dependency(self):

        async def require_authentication(
            identity: Annotated[tuple[str, Labels] | None, Depends(self._authenticate)]
        ):
            if identity is None:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return identity

        return require_authentication

    def _build_validate_guid_dependency(self):
        async def validate_guid(guid: self._enabled_integrations_enum):  # type: ignore
            if guid not in self._integration_registry:
                raise HTTPException(status_code=404, detail="Integration not found")
            return guid

        return validate_guid

    def _build_load_manager_dependency(self):

        async def load_manager(
            guid: Annotated[str, Depends(self._validate_guid_dep)],
            identity: Annotated[
                tuple[str, Labels], Depends(self._require_authentication_dep)
            ],
        ):
            integration = self._integration_registry[guid]
            manager = await InstanceManager.restore_by_labels(
                store=self._store,
                config_class=integration.final_config_model,
                guid=guid,
                labels=identity[1],
                namespace=identity[0],
            )
            manager.add_configuration("admin", integration.supplied_config)
            return manager

        return load_manager

    def _build_temp_manager_dependency(self):

        async def temp_manager(guid: Annotated[str, Depends(self._validate_guid_dep)]):
            integration = self._integration_registry[guid]
            return InstanceManager(integration.final_config_model, guid)

        return temp_manager

    def _build_get_catalog_info_handler(self):
        async def get_catalog_handler():
            return [
                self._integration_registry[guid].spec.display
                for guid in self._integration_registry
            ]

        return get_catalog_handler

    def _build_get_enabled_integrations_handler(self):
        async def get_enabled_integrations():
            return list(self._integration_registry.keys())

        return get_enabled_integrations

    def _build_get_integration_info_handler(self):
        async def get_integration(
            guid: Annotated[str, Depends(self._validate_guid_dep)]
        ):
            return self._integration_registry[guid].spec.display

        return get_integration

    def _build_info_router(self) -> APIRouter:
        info_router = APIRouter(tags=["info"])

        get_catalog_info_handler = self._build_get_catalog_info_handler()
        info_router.get("/info")(get_catalog_info_handler)

        get_enabled_integrations_handler = (
            self._build_get_enabled_integrations_handler()
        )
        info_router.get("/enabled")(get_enabled_integrations_handler)

        get_integration_info_handler = self._build_get_integration_info_handler()
        info_router.get("/{guid}/info")(get_integration_info_handler)

        return info_router

    def _build_get_integration_schema_handler(self):
        """
        Uses a temporary manager to avoid loading the configuration through the _load_manager_dep dependency.
        """

        async def get_integration_schema(
            guid: Annotated[str, Depends(self._validate_guid_dep)],
            temp_manager: Annotated[InstanceManager, Depends(self._temp_manager_dep)],
        ):
            return temp_manager.get_json_schema("user")

        return get_integration_schema

    def _build_get_integration_config_handler(self):
        async def get_integration_config(
            manager: Annotated[InstanceManager, Depends(self._load_manager_dep)],
        ):
            return manager.serialize_config("user")

        return get_integration_config

    def _build_put_integration_config_handler(self):
        async def put_integration_config(
            manager: Annotated[InstanceManager, Depends(self._load_manager_dep)],
            config: Annotated[Dict[str, JsonValue], Body(embed=True)],
        ):
            try:
                manager.get_model("user")(**config)
            except ValidationError as e:
                raise RequestValidationError(e.errors())
            manager.add_configuration("user", config)
            # need some way to save the config to store

        return put_integration_config

    def _build_integration_config_callback_handler(self):
        async def integration_config_callback(
            guid: Annotated[str, Depends(self._validate_guid_dep)],
            config: Annotated[Dict[str, JsonValue], Body(embed=True)],
        ):
            integration = self._integration_registry[guid]
            try:
                integration.config_callback(config)
            except ValidationError as e:
                raise RequestValidationError(e.errors())
            # need some way to save the config to store

    def _build_connect_router(self) -> APIRouter:
        base_router = APIRouter(
            prefix="/{guid}",
            tags=["connect"],
            dependencies=[
                Depends(self._require_authentication_dep),
                Depends(self._validate_guid_dep),
            ],
        )  # base_router CANNOT have a path on /info, info is a reserved path for the info router

        schema_router = APIRouter()

        get_integration_schema_handler = self._build_get_integration_schema_handler()
        schema_router.get("/schema")(get_integration_schema_handler)

        management_router = APIRouter(dependencies=[Depends(self._load_manager_dep)])
        get_integration_config_handler = self._build_get_integration_config_handler()
        put_integration_config_handler = self._build_put_integration_config_handler()

        management_router.put("/")(put_integration_config_handler)
        management_router.get("/")(get_integration_config_handler)

        base_router.include_router(schema_router)
        base_router.include_router(management_router)
        return base_router

    def _build_webhook_router(self) -> APIRouter:

        router = APIRouter(prefix="/webhook", tags=["webhook"])
        return router

    def _build_admin_router(self) -> APIRouter:
        router = APIRouter(prefix="/admin", tags=["admin"])
        return router

    def router(
        self,
        info: bool = True,
        connect: bool = True,
        webhook: bool = True,
        admin: bool = False,
    ) -> APIRouter:
        if not self.finalized:
            raise RuntimeError("Catalog is not finalized, cannot create router")
        catalog_router = APIRouter(prefix="/catalog", tags=["catalog"])
        if info:
            catalog_router.include_router(self._build_info_router())
        if connect:
            catalog_router.include_router(self._build_connect_router())
        if webhook:
            catalog_router.include_router(self._build_webhook_router())
        if admin:
            logger.warning(
                "Admin routes are enabled. Ensure this router is properly secured."
            )
            warnings.warn(
                "Admin routes are enabled. Ensure this router is properly secured."
            )
            catalog_router.include_router(self._build_admin_router())
        return catalog_router
