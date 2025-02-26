from pydantic import BaseModel, Field

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
    manager = InstanceManager(CustomSlackConfig)
    # manager.add_configuration(
    #     "admin", {"api_key": "xoxb-123456789012-123456789012-123456789012"}
    # )
    print(manager.get_json_schema("admin"))
    # print(manager.build_config())
