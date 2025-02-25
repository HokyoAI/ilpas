from typing import Literal

type ConfigurationSupplier = Literal["admin", "user", "callback"]

type ConfigurationState = Literal["pending", "partial", "complete"]
