from dataclasses import dataclass


@dataclass
class Endpoint:
    name: str
    url: str
    method: str
    headers: dict
    body: dict
