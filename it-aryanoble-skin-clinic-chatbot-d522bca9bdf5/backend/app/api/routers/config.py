from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.database import get_db
from app.api.dependencies import get_current_user, RequireAccess
from app.models.user import User
from app.models.config import AppConfig
from app.schemas.config import ConfigUpdate, ConfigResponse, LLMValidateRequest, FetchModelsRequest, ModelInfo
from app.core.security import encrypt_api_key, decrypt_api_key
import urllib.request
import urllib.error
import json

def mask_api_key(key_value: str) -> str:
    if not key_value or len(key_value) < 10:
        return "***"
    return f"{key_value[:7]}...{key_value[-4:]}"

async def _resolve_api_key(api_key: str, db: AsyncSession) -> str:
    if "***" in api_key or "..." in api_key:
        stmt = select(AppConfig).where(AppConfig.key == "LLM_API_KEY")
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()
        if config:
            return decrypt_api_key(config.value)
    return api_key

router = APIRouter(prefix="/config", tags=["config"])

@router.get("/", response_model=List[ConfigResponse])
async def list_config(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("configuration:read"))
):
    stmt = select(AppConfig)
    result = await db.execute(stmt)
    configs = result.scalars().all()
    
    # Mask API key in response
    for config in configs:
        if config.key == "LLM_API_KEY":
            decrypted = decrypt_api_key(config.value)
            config.value = mask_api_key(decrypted)
            
    return configs

@router.put("/{key}", response_model=ConfigResponse)
async def update_config(
    key: str,
    config_in: ConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("configuration:write"))
):
    stmt = select(AppConfig).where(AppConfig.key == key)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    
    if key == "LLM_API_KEY":
        if "***" in config_in.value or "..." in config_in.value:
            # Ignore masked key updates to prevent accidental overrides
            # We still return the masked version
            if config:
                decrypted = decrypt_api_key(config.value)
                config.value = mask_api_key(decrypted)
            return config
        config_in.value = encrypt_api_key(config_in.value)

    if not config:
        # Create it if it doesn't exist
        config = AppConfig(key=key, value=config_in.value)
        db.add(config)
    else:
        config.value = config_in.value
        
    await db.commit()
    await db.refresh(config)
    
    # Mask API key in response
    if key == "LLM_API_KEY":
        decrypted = decrypt_api_key(config.value)
        config.value = mask_api_key(decrypted)
        
    return config

@router.post("/validate-llm")
async def validate_llm(
    req: LLMValidateRequest, 
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("configuration:write"))
):
    provider = req.provider.lower()
    actual_api_key = await _resolve_api_key(req.api_key, db)
    
    try:
        if provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{req.model_name}?key={actual_api_key}"
            req_obj = urllib.request.Request(url)
            with urllib.request.urlopen(req_obj, timeout=5) as response:
                if response.status != 200:
                    raise HTTPException(status_code=400, detail="Invalid API Key or Model for Gemini")
        elif provider in ["openai", "deepseek", "ollama"]:
            from app.rag.services.factory import AdapterFactory
            resolved_base_url = AdapterFactory._resolve_provider_base_url(provider)
            
            if provider == "openai":
                url = "https://api.openai.com/v1/models"
            elif provider == "deepseek":
                url = "https://api.deepseek.com/models"
            elif resolved_base_url:
                url = f"{resolved_base_url.rstrip('/')}/models"
            else:
                url = "https://api.openai.com/v1/models"
                
            headers = {"Authorization": f"Bearer {actual_api_key}"}
            req_obj = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req_obj, timeout=5) as response:
                if response.status != 200:
                    raise HTTPException(status_code=400, detail=f"Invalid API Key for {provider}")
                
                res_data = json.loads(response.read().decode())
                models = [m["id"] for m in res_data.get("data", [])]
                if req.model_name and models and req.model_name not in models:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Model '{req.model_name}' not found. Valid models include: {', '.join(models[:3])}..."
                    )
        else:
            raise HTTPException(status_code=400, detail="Unknown provider")
            
        return {"status": "ok", "message": "API Key and Model validated successfully."}


    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise HTTPException(status_code=400, detail="Invalid API Key")
        elif e.code == 404 and provider == "gemini":
            raise HTTPException(status_code=400, detail=f"Model '{req.model_name}' not found for Gemini")
        raise HTTPException(status_code=400, detail=f"Validation failed: HTTP {e.code} - {e.reason}")
    except urllib.error.URLError as e:
        raise HTTPException(status_code=400, detail=f"Network error during validation: {e.reason}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Validation failed: {str(e)}")

@router.post("/fetch-models", response_model=List[ModelInfo])
async def fetch_models(
    req: FetchModelsRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("configuration:write"))
):
    provider = req.provider.lower()
    actual_api_key = await _resolve_api_key(req.api_key, db)
    
    try:
        models = []
        if provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={actual_api_key}"
            req_obj = urllib.request.Request(url)
            with urllib.request.urlopen(req_obj, timeout=5) as response:
                if response.status != 200:
                    raise HTTPException(status_code=400, detail="Invalid API Key for Gemini")
                res_data = json.loads(response.read().decode())
                for m in res_data.get("models", []):
                    # Only include models that support standard text generation
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" not in methods:
                        continue
                        
                    # Gemini model names start with 'models/' so we strip it for simplicity
                    model_id = m.get("name", "").replace("models/", "")
                    
                    # Strictly filter for only gemini base models (exclude nano/experimental/bison)
                    if not model_id.startswith("gemini-"):
                        continue
                    
                    # Exclude vision models if strictly text only
                    if "vision" in model_id:
                        continue
                        
                    models.append(ModelInfo(
                        id=model_id,
                        input_limit=m.get("inputTokenLimit"),
                        output_limit=m.get("outputTokenLimit")
                    ))
        elif provider in ["openai", "deepseek", "ollama"]:
            from app.rag.services.factory import AdapterFactory
            resolved_base_url = AdapterFactory._resolve_provider_base_url(provider)
            
            if provider == "openai":
                url = "https://api.openai.com/v1/models"
            elif provider == "deepseek":
                url = "https://api.deepseek.com/models"
            elif resolved_base_url:
                url = f"{resolved_base_url.rstrip('/')}/models"
            else:
                url = "https://api.openai.com/v1/models"
                
            headers = {"Authorization": f"Bearer {actual_api_key}"}
            req_obj = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req_obj, timeout=5) as response:
                if response.status != 200:
                    raise HTTPException(status_code=400, detail=f"Invalid API Key for {provider}")
                res_data = json.loads(response.read().decode())
                excluded_keywords = [
                    "tts", "whisper", "dall-e", "embedding", "babbage", 
                    "davinci", "ada", "curie", "vision", "audio", "realtime"
                ]
                
                for m in res_data.get("data", []):
                    model_id = m.get("id")
                    
                    if provider == "openai":
                        # Exclude non-text/legacy models dynamically
                        if any(keyword in model_id.lower() for keyword in excluded_keywords):
                            continue
                            
                    if provider == "deepseek":
                        # Deepseek models are mostly text, but just in case
                        if "embedding" in model_id.lower():
                            continue
                            
                    models.append(ModelInfo(id=model_id))
        else:
            raise HTTPException(status_code=400, detail="Unknown provider")
            
        return models

    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise HTTPException(status_code=400, detail="Invalid API Key")
        raise HTTPException(status_code=400, detail=f"Failed to fetch models: HTTP {e.code} - {e.reason}")
    except urllib.error.URLError as e:
        raise HTTPException(status_code=400, detail=f"Network error: {e.reason}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch models: {str(e)}")

