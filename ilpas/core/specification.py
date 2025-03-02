from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Generic, Optional, TypeVar

from fastapi import Request, Response
from pydantic import BaseModel

_A = TypeVar("_A", bound=BaseModel)
_U = TypeVar("_U", bound=BaseModel)
_PUA = TypeVar("_PUA", bound=BaseModel)
_C = TypeVar("_C", bound=BaseModel)
_PCA = TypeVar("_PCA", bound=BaseModel)


class NoConfig(BaseModel):
    model_config = {"extra": "forbid"}


class AnyConfig(BaseModel):
    model_config = {"extra": "allow"}


@dataclass
class Display:
    name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None


class Callback(Generic[_A, _U, _PUA, _C, _PCA], ABC):
    callback_config_model: type[_C]

    @abstractmethod
    @classmethod
    async def uri(
        cls, admin_config: _A, user_config: _U, post_user_admin_config: _PUA
    ) -> str: ...

    @abstractmethod
    @classmethod
    async def key(
        cls, admin_config: _A, user_config: _U, post_user_admin_config: _PUA
    ) -> str: ...

    @abstractmethod
    @classmethod
    async def process(
        cls,
        admin_config: _A,
        user_config: _U,
        post_user_admin_config: _PUA,
        query_params: Dict[str, str],
    ) -> _C: ...

    @abstractmethod
    @classmethod
    async def post_callback_admin_config(
        cls,
        admin_config: _A,
        user_config: _U,
        post_user_admin_config: _PUA,
        callback_config: _C,
    ) -> _PCA: ...


@dataclass
class Endpoint:
    name: str
    url: str
    method: str
    headers: dict
    body: dict


@dataclass
class WebhookEvent:
    uid: str
    respond: Optional[Callable[[Request], Awaitable[Response]]]


class Webhook(Generic[_A, _U, _PUA, _C, _PCA], ABC):
    verify: Callable[
        [Request, _A, _U, _PUA, _C, _PCA], Awaitable[bool]
    ]  # returns True if webhook is valid
    router: Callable[
        [Request, _A, _U, _PUA, _C, _PCA], Awaitable[WebhookEvent]
    ]  # returns webhook event

    @abstractmethod
    @classmethod
    async def identify(cls, request: Request) -> Optional[str]:
        """Returns instance discovery key of the instance that the webhook is for, or None if not instance specific"""
        ...


class Specification(Generic[_A, _U, _PUA, _C, _PCA], ABC):
    """
    Abstract base class for specifications.
    Subclasses must define all required class attributes.
    Specifications are never instantiated.
    All of their properties are class properties and methods are class methods.
    These are simply convenient ways to group related models and functions.
    """

    guid: str
    display: Display
    admin_config_model: type[_A]
    user_config_model: type[_U]
    callback: Optional[Callback[_A, _U, _PUA, _C, _PCA]]
    endpoints: Dict[str, Endpoint]
    health_check: Optional[Endpoint]
    maintenance: Optional[Endpoint]
    webhook: Optional[Webhook]

    @abstractmethod
    @classmethod
    async def post_user_admin_config(
        cls, admin_config: _A, user_config: _U
    ) -> _PUA: ...
