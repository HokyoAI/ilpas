from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ilpas.core.catalog import Catalog
from ilpas.core.instance import Instance, Labels
from ilpas.core.integration import Integration, Specification
from ilpas.core.models.callback import Callback
from ilpas.core.models.display import Display
from ilpas.dx.helpers import extras
from ilpas.dx.in_memory_store import InMemoryStore


# Step 1: Integration Writer creates the base integration
class SlackIntegrationConfig(BaseModel):
    """Base Slack integration configuration defined by the integration writer"""

    api_key: str = Field(
        ...,
        description="Slack API token",
        json_schema_extra=extras("admin", sensitive=True),
    )


Slack = Specification(
    guid="slack_latest",
    display=Display(
        name="Slack",
        description="Slack integration",
        logo_url="https://slack.com/favicon.ico",
    ),
    config_model=SlackIntegrationConfig,
    callback=None,
    health_check=None,
    endpoints={},
    webhooks={},
)

SlackV2 = Specification(
    guid="slack_v2",
    display=Display(
        name="Slack V2",
        description="Slack integration V2",
        logo_url="https://slack.com/favicon.ico",
    ),
    config_model=SlackIntegrationConfig,
    callback=Callback(),
    health_check=None,
    endpoints={},
    webhooks={},
)


# Step 2: Admin extends the configuration for their specific use case
class CustomSlackConfig(SlackIntegrationConfig):
    """Admin's extended Slack configuration"""

    default_channel: str = Field(..., json_schema_extra=extras("user"))
    notification_prefix: str = Field(
        default="[ALERT]", json_schema_extra=extras("user")
    )
    rate_limit: int = Field(default=100, gt=0, json_schema_extra=extras("user"))


slack = Integration(
    spec=Slack,
    final_config_model=CustomSlackConfig,
    supplied_config={"api_key": "xoxb-123456789012-123456789012-123456789012"},
)


def test_json_schema():
    temp_instance = Instance(slack, temporary=True)
    assert temp_instance.get_json_schema("admin") == {
        "properties": {
            "api_key": {
                "description": "Slack API token",
                "sensitive": True,
                "supplier": "admin",
                "title": "Api Key",
                "triggers_callback": False,
                "type": "string",
            },
        },
        "required": [
            "api_key",
        ],
        "title": "CustomSlackConfig[admin]",
        "type": "object",
    }


def test_settings():
    """This works but doesn't provide auto completion for the settings object after"""
    load_dotenv(override=True)
    temp_instance = Instance(slack, temporary=True)

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_nested_delimiter="__")

        slack: temp_instance.get_model("admin")  # type: ignore

    settings = Settings()  # type: ignore
