from pydantic import BaseModel, ConfigDict, Field
from typing import Any
import uuid
from datetime import datetime

class ConfigBase(BaseModel):
    key: str
    value: str

class ConfigUpdate(BaseModel):
    value: str

class LLMValidateRequest(BaseModel):
    provider: str
    model_name: str
    api_key: str

class FetchModelsRequest(BaseModel):
    provider: str
    api_key: str

class ModelInfo(BaseModel):
    id: str
    input_limit: int | None = None
    output_limit: int | None = None

class ConfigResponse(ConfigBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

class GlobalMonthlyUsageResponse(BaseModel):
    year_month: str
    tokens_used: int
    token_limit: int | None = None
    remaining: int | None = None
    percentage: float | None = None
    is_global_active: bool = False

class DatabaseResetRequest(BaseModel):
    confirmation: str = Field(
        default="RESET_AND_RESEED",
        description="Safety phrase. Must be exactly 'RESET_AND_RESEED' to trigger table wipe.",
        examples=["RESET_AND_RESEED"],
    )
    admin_email: str = Field(
        default="admin@mail.com",
        description="Default admin user email",
        examples=["admin@mail.com"],
    )
    admin_password: str = Field(
        default="Erhadermies@123",
        description="Default admin user password",
        examples=["Erhadermies@123"],
    )

class DatabaseResetResponse(BaseModel):
    status: str
    message: str
    details: dict[str, Any]


