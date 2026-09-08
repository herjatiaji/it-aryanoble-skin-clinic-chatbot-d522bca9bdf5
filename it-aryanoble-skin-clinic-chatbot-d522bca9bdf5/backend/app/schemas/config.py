from pydantic import BaseModel, ConfigDict
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
