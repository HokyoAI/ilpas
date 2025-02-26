from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ilpas.core.manager import InstanceManager, extras


# Step 1: Integration Writer creates the base integration
class SlackIntegrationConfig(BaseModel):
    """Base Slack integration configuration defined by the integration writer"""

    api_key: str = Field(
        ...,
        description="Slack API token",
        json_schema_extra=extras("admin", sensitive=True),
    )


# Step 2: Admin extends the configuration for their specific use case
class CustomSlackConfig(SlackIntegrationConfig):
    """Admin's extended Slack configuration"""

    default_channel: str = Field(..., json_schema_extra=extras("user"))
    notification_prefix: str = Field(
        default="[ALERT]", json_schema_extra=extras("user")
    )
    rate_limit: int = Field(default=100, gt=0, json_schema_extra=extras("user"))


def test():
    """This works but doesn't provide auto completion for the settings object after"""
    load_dotenv(override=True)
    manager = InstanceManager(CustomSlackConfig)

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_nested_delimiter="__")

        slack: manager.get_model("admin")  # type: ignore

    settings = Settings()  # type: ignore
