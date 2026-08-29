"""Base model declarations."""

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base Pydantic model configuration."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        from_attributes=True,
    )
