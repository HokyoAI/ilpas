import asyncio
from abc import ABC, abstractmethod
from typing import List, Literal

from hatchet_sdk import Hatchet

from .models.types import AM


class Event[_P: AM](ABC):
    spec_owner: str
    name: str
    event_type: Literal["status", "polling", "webhook", "custom", "generic"]
    payload_model: type[_P]

    payload: _P
    full_name: str

    def __init__(self, payload: _P):
        self.payload: _P = payload
        self.full_name: str = f"{self.spec_owner}.{self.event_type}.{self.name}"


class Listener(ABC):

    @abstractmethod
    async def dispatch(self, event: Event): ...


class Hub:

    def __init__(self):
        self._listeners: List[Listener] = []

    def register(self, listener: Listener):
        """
        Register a listener for a tied event or all events.
        Can be used as a decorator or direct function call.
        """
        self._listeners.append(listener)

    async def dispatch(self, event: Event):
        """Fanout event to all listeners."""
        calls = []
        for listener in self._listeners:
            calls.append(listener.dispatch(event))

        return await asyncio.gather(*calls)


class HatchetListener(Listener):

    def __init__(self, hatchet: Hatchet):
        self.hatchet = hatchet

    async def dispatch[_T: AM](self, event: Event[_T]):

        self.hatchet.admin.run_workflow(event.full_name, event.payload.model_dump())
