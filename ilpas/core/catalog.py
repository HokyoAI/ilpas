from typing import Annotated, Dict, List, cast

from fastapi import APIRouter, Body
from pydantic import BaseModel

from .integration import Integration


class Catalog:
    """
    Catalog of integrations.

    IMPORTANT: Claude caught this one.
    See https://stackoverflow.com/questions/78110125/how-to-dynamically-create-fastapi-routes-handlers-for-a-list-of-pydantic-models
    Helper functions must be used to create routes handlers for each integration because of scoping and closure issues.
    """

    def __init__(self):
        self._integration_registry: Dict[str, Integration] = {}

    def add_integration(
        self,
        integration: Integration,
    ):
        self._integration_registry[integration.spec.guid] = integration

    def _catalog_router(self) -> APIRouter:
        router = APIRouter(prefix="/catalog", tags=["catalog"])

        async def get_catalog():
            return [
                self._integration_registry[guid].spec.display
                for guid in self._integration_registry
            ]

        router.get("/")(get_catalog)

        def create_get_integration(current_guid):
            async def get_integration():
                return self._integration_registry[current_guid].spec.display

            return get_integration

        for guid in self._integration_registry:
            router_path = f"/{guid}"
            get_integration_handler = create_get_integration(guid)
            router.get(router_path, tags=[guid])(get_integration_handler)

        return router

    def _connect_router(self) -> APIRouter:
        router = APIRouter(prefix="/connect", tags=["connect"])

        def create_schema_handler(current_guid):
            async def get_integration_schema():
                integration = self._integration_registry[current_guid]
                return integration.user_config_model.model_json_schema()

            return get_integration_schema

        def create_connect_handler(current_guid, current_model):
            async def connect_integration(
                config: Annotated[current_model, Body()]  # type: ignore
            ):
                integration = self._integration_registry[current_guid]
                config_cast = cast(type[BaseModel], config)
                return config_cast.model_json_schema()

            return connect_integration

        for guid in self._integration_registry:
            router_path = f"/{guid}"
            user_config_model = self._integration_registry[guid].user_config_model

            schema_handler = create_schema_handler(guid)
            connect_handler = create_connect_handler(guid, user_config_model)

            router.get(router_path, tags=[guid])(schema_handler)
            router.post(router_path, tags=[guid])(connect_handler)

        return router

    def _webhook_router(self) -> APIRouter:

        router = APIRouter(prefix="/webhook", tags=["webhook"])
        return router

    def serve(self, catalog: bool = True, connect: bool = True, webhook: bool = True):
        routers: List[APIRouter] = []
        if catalog:
            routers.append(self._catalog_router())
        if connect:
            routers.append(self._connect_router())
        if webhook:
            routers.append(self._webhook_router())
        return routers
