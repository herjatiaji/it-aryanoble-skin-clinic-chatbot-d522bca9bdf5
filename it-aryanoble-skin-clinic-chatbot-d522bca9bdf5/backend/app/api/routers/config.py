from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from app.core.database import get_db
from app.api.dependencies import get_current_user, RequireAccess
from app.models.user import User, UserTokenUsage
from app.models.config import AppConfig
from app.models.ingestion_usage import IngestionTokenUsage
from app.schemas.config import (
    ConfigUpdate,
    ConfigResponse,
    GlobalMonthlyUsageResponse,
    LLMValidateRequest,
    FetchModelsRequest,
    ModelInfo,
    DatabaseResetRequest,
    DatabaseResetResponse,
)
from app.services.db_seeder import (
    reset_database,
    seed_database,
    reset_and_reseed_database,
)
from app.core.security import encrypt_api_key, decrypt_api_key
from app.core.config import settings
import os
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

@router.get("/usage", response_model=GlobalMonthlyUsageResponse)
async def get_global_monthly_usage(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("configuration:read"))
):
    current_ym = datetime.now(timezone.utc).strftime("%Y-%m")

    # 1. Sum chat tokens used for current month
    stmt_user = select(func.sum(UserTokenUsage.tokens_used)).where(UserTokenUsage.year_month == current_ym)
    res_user = await db.execute(stmt_user)
    chat_tokens = res_user.scalar() or 0

    # 2. Sum ingestion tokens used for current month
    stmt_ingest = select(func.sum(IngestionTokenUsage.tokens_used)).where(IngestionTokenUsage.year_month == current_ym)
    res_ingest = await db.execute(stmt_ingest)
    ingest_tokens = res_ingest.scalar() or 0

    total_used = chat_tokens + ingest_tokens

    # 3. Check if global token limit and threshold are active
    stmt_active = select(AppConfig.value).where(AppConfig.key == "GLOBAL_TOKEN_LIMIT_ACTIVE")
    res_active = await db.execute(stmt_active)
    active_val = res_active.scalar_one_or_none()
    is_master_active = (active_val or "false").lower() == "true"

    stmt_thresh_act = select(AppConfig.value).where(AppConfig.key == "GLOBAL_THRESHOLD_ACTIVE")
    res_thresh_act = await db.execute(stmt_thresh_act)
    thresh_act_val = res_thresh_act.scalar_one_or_none()
    is_thresh_active = (thresh_act_val or "false").lower() == "true"

    if is_master_active and is_thresh_active:
        stmt_thresh = select(AppConfig.value).where(AppConfig.key == "GLOBAL_TOKEN_THRESHOLD")
        res_thresh = await db.execute(stmt_thresh)
        thresh_val = res_thresh.scalar_one_or_none()
        limit = int(thresh_val) if (thresh_val and thresh_val.isdigit()) else 1000000

        remaining = max(0, limit - total_used)
        percentage = round(min(100.0, (total_used / limit * 100)), 1) if limit > 0 else 0.0

        return GlobalMonthlyUsageResponse(
            year_month=current_ym,
            tokens_used=total_used,
            token_limit=limit,
            remaining=remaining,
            percentage=percentage,
            is_global_active=True
        )

    return GlobalMonthlyUsageResponse(
        year_month=current_ym,
        tokens_used=total_used,
        token_limit=None,
        remaining=None,
        percentage=None,
        is_global_active=False
    )

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

    # Handle updating global branch limit: reset all branch custom overrides and synchronize limit
    if key == "GLOBAL_TOKEN_LIMIT":
        try:
            val_int = int(config_in.value)
            from app.models.branch import Branch
            from sqlalchemy import update
            b_stmt = update(Branch).where(Branch.deleted_at.is_(None)).values(
                has_custom_limit=False,
                token_limit=val_int
            )
            await db.execute(b_stmt)
        except (ValueError, TypeError):
            pass

    # Handle master switch cascade
    if key == "GLOBAL_TOKEN_LIMIT_ACTIVE":
        if config_in.value.lower() == "true":
            # Master ON: Global Token Threshold is immediately active; other sub-rules remain inactive (on hold)
            t_stmt = select(AppConfig).where(AppConfig.key == "GLOBAL_THRESHOLD_ACTIVE")
            t_res = await db.execute(t_stmt)
            t_cfg = t_res.scalar_one_or_none()
            if t_cfg:
                t_cfg.value = "true"
            else:
                db.add(AppConfig(key="GLOBAL_THRESHOLD_ACTIVE", value="true"))
        elif config_in.value.lower() == "false":
            # Master OFF: Atomically deactivate all sub-rules
            sub_keys = [
                "GLOBAL_BRANCH_LIMIT_ACTIVE",
                "GLOBAL_THRESHOLD_ACTIVE",
                "GLOBAL_SPKK_LIMIT_ACTIVE",
                "GLOBAL_GP_LIMIT_ACTIVE"
            ]
            for sk in sub_keys:
                s_stmt = select(AppConfig).where(AppConfig.key == sk)
                s_res = await db.execute(s_stmt)
                s_cfg = s_res.scalar_one_or_none()
                if s_cfg:
                    s_cfg.value = "false"
                else:
                    db.add(AppConfig(key=sk, value="false"))
        
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


@router.get("/system-logs")
async def get_system_logs(
    lines: int = 300,
    level: Optional[str] = None,
    search: Optional[str] = None,
    raw: bool = False,
    current_admin: User = Depends(RequireAccess("configuration:read"))
):
    """
    Retrieve live backend logs from in-memory ring buffer and rotating file.
    Supports filtering by level (INFO, DEBUG, ERROR, WARNING) and keyword search.
    If raw=True, returns text/plain for direct browser or terminal viewing.
    Protected by RBAC (requires configuration:read access).
    """
    from app.core.logger import get_recent_logs
    from fastapi.responses import PlainTextResponse
    
    clamped_lines = min(max(10, lines), 3000)
    log_lines = get_recent_logs(lines=clamped_lines, level=level, search=search)
    
    if raw:
        return PlainTextResponse("\n".join(log_lines))
        
    return {
        "count": len(log_lines),
        "requested_lines": clamped_lines,
        "level_filter": level,
        "search_filter": search,
        "logs": log_lines
    }


@router.get("/system-logs/ui")
async def get_system_logs_ui(
    current_admin: User = Depends(RequireAccess("configuration:read"))
):
    """
    Renders an interactive, real-time, Dozzle-style Web Log Viewer with:
    - Dark mode terminal theme
    - Colorized log levels (INFO, WARN, ERROR, DEBUG)
    - Live auto-polling stream (every 1.5s)
    - Instant client-side search & level filtering
    - Auto-scroll & pause controls
    Protected by RBAC (requires configuration:read access).
    """
    from fastapi.responses import HTMLResponse

    html_content = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Arya Noble - Backend Live Logs</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: #0d1117;
            color: #c9d1d9;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
            font-size: 13px;
            line-height: 1.5;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        /* Top Navigation / Toolbar */
        header {
            background-color: #161b22;
            border-bottom: 1px solid #30363d;
            padding: 10px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
            z-index: 10;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 600;
            color: #f0f6fc;
            font-size: 14px;
        }
        .badge {
            background: #238636;
            color: #fff;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
        }
        .controls {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }
        input, select, button {
            background-color: #21262d;
            border: 1px solid #30363d;
            color: #c9d1d9;
            padding: 5px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-family: inherit;
            outline: none;
        }
        input:focus, select:focus {
            border-color: #58a6ff;
        }
        input[type="text"] {
            width: 220px;
        }
        button {
            cursor: pointer;
            transition: background 0.15s ease;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }
        button:hover {
            background-color: #30363d;
        }
        button.active {
            background-color: #1f6feb;
            border-color: #388bfd;
            color: #fff;
        }
        .btn-danger {
            color: #f85149;
        }
        .btn-danger:hover {
            background-color: #b62324;
            color: #fff;
        }
        /* Logs Terminal Container */
        #log-container {
            flex: 1;
            overflow-y: auto;
            padding: 12px 16px;
            background-color: #0d1117;
            scroll-behavior: smooth;
        }
        .log-row {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            padding: 2px 4px;
            border-radius: 3px;
            white-space: pre-wrap;
            word-break: break-all;
        }
        .log-row:hover {
            background-color: #161b22;
        }
        .log-num {
            color: #484f58;
            user-select: none;
            min-width: 40px;
            text-align: right;
            font-size: 11px;
            padding-top: 1px;
        }
        .log-time {
            color: #8b949e;
            min-width: 145px;
        }
        .level-tag {
            padding: 1px 6px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            min-width: 54px;
            text-align: center;
            display: inline-block;
        }
        .level-INFO { background-color: rgba(56, 139, 253, 0.15); color: #58a6ff; }
        .level-ERROR { background-color: rgba(248, 81, 73, 0.2); color: #ff7b72; font-weight: 700; }
        .level-WARNING, .level-WARN { background-color: rgba(210, 153, 34, 0.2); color: #d29922; }
        .level-DEBUG { background-color: rgba(139, 148, 158, 0.15); color: #8b949e; }
        .level-SUCCESS { background-color: rgba(46, 160, 67, 0.2); color: #3fb950; }
        .log-msg {
            flex: 1;
            color: #e6edf3;
        }
        .log-msg.error-msg {
            color: #ff7b72;
        }
        .log-module {
            color: #79c0ff;
        }
        /* Footer Status Bar */
        footer {
            background-color: #161b22;
            border-top: 1px solid #30363d;
            padding: 4px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 11px;
            color: #8b949e;
        }
        .live-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: #238636;
            display: inline-block;
            margin-right: 6px;
            animation: pulse 2s infinite;
        }
        .paused-dot {
            background-color: #d29922;
            animation: none;
        }
        @keyframes pulse {
            0% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.9); }
            100% { opacity: 1; transform: scale(1); }
        }
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <span>⚡ Arya Noble Backend Logs</span>
            <span class="badge">Live</span>
        </div>
        <div class="controls">
            <input type="text" id="searchInput" placeholder="Filter logs (regex supported)..." oninput="applyFilter()">
            
            <select id="levelSelect" onchange="applyFilter()">
                <option value="ALL">All Levels</option>
                <option value="ERROR">Errors Only</option>
                <option value="WARNING">Warnings & Errors</option>
                <option value="INFO">Info, Warn, Error</option>
                <option value="DEBUG">Debug / All</option>
            </select>

            <select id="linesSelect" onchange="fetchLogs()">
                <option value="100">100 lines</option>
                <option value="300" selected>300 lines</option>
                <option value="500">500 lines</option>
                <option value="1000">1000 lines</option>
                <option value="2000">2000 lines</option>
            </select>

            <button id="autoscrollBtn" class="active" onclick="toggleAutoScroll()">
                <span>⬇ Auto-Scroll</span>
            </button>

            <button id="liveBtn" class="active" onclick="toggleLive()">
                <span>⏸ Live (1.5s)</span>
            </button>

            <button onclick="fetchLogs()">🔄 Refresh</button>
            <button class="btn-danger" onclick="clearScreen()">🗑 Clear</button>
        </div>
    </header>

    <div id="log-container"></div>

    <footer>
        <div>
            <span id="liveIndicator" class="live-dot"></span>
            <span id="statusText">Streaming real-time logs</span>
        </div>
        <div>
            Total Rendered: <strong id="logCount" style="color: #58a6ff;">0</strong> lines
        </div>
    </footer>

    <script>
        let rawLogLines = [];
        let autoScroll = true;
        let isLive = true;
        let pollInterval = null;

        async function fetchLogs() {
            const lines = document.getElementById('linesSelect').value;
            try {
                const resp = await fetch(`/api/config/system-logs?lines=${lines}`);
                if (!resp.ok) {
                    if (resp.status === 401 || resp.status === 403) {
                        document.getElementById('statusText').innerText = "Auth required (please login or set token)";
                    }
                    return;
                }
                const data = await resp.json();
                rawLogLines = data.logs || [];
                renderLogs();
            } catch (err) {
                console.error("Failed to fetch logs", err);
            }
        }

        function parseLogLine(line) {
            // Standard Loguru format: 2026-08-24 02:58:34 | INFO     | module:func:line - message
            const parts = line.split(" | ");
            if (parts.length >= 3) {
                const timestamp = parts[0].trim();
                const level = parts[1].trim();
                const rest = parts.slice(2).join(" | ");
                const hyphenIdx = rest.indexOf(" - ");
                
                let module = "";
                let msg = rest;
                if (hyphenIdx !== -1) {
                    module = rest.substring(0, hyphenIdx).trim();
                    msg = rest.substring(hyphenIdx + 3);
                }
                return { timestamp, level, module, msg, raw: line };
            }
            return { timestamp: "", level: "INFO", module: "", msg: line, raw: line };
        }

        function renderLogs() {
            const container = document.getElementById('log-container');
            const searchVal = document.getElementById('searchInput').value.trim().toLowerCase();
            const levelVal = document.getElementById('levelSelect').value;

            let filtered = rawLogLines;

            if (levelVal === "ERROR") {
                filtered = filtered.filter(l => l.includes("| ERROR"));
            } else if (levelVal === "WARNING") {
                filtered = filtered.filter(l => l.includes("| WARNING") || l.includes("| ERROR"));
            } else if (levelVal === "INFO") {
                filtered = filtered.filter(l => !l.includes("| DEBUG"));
            }

            if (searchVal) {
                try {
                    const regex = new RegExp(searchVal, 'i');
                    filtered = filtered.filter(l => regex.test(l));
                } catch (e) {
                    filtered = filtered.filter(l => l.toLowerCase().includes(searchVal));
                }
            }

            document.getElementById('logCount').innerText = filtered.length;

            let html = "";
            filtered.forEach((line, idx) => {
                const p = parseLogLine(line);
                const isErr = p.level === "ERROR" || p.raw.toLowerCase().includes("traceback") || p.raw.toLowerCase().includes("exception");
                const levelClass = isErr ? "level-ERROR" : `level-${p.level || 'INFO'}`;
                
                html += `
                <div class="log-row">
                    <div class="log-num">${idx + 1}</div>
                    ${p.timestamp ? `<div class="log-time">${p.timestamp}</div>` : ''}
                    <div class="level-tag ${levelClass}">${p.level || 'LOG'}</div>
                    ${p.module ? `<div class="log-module">[${p.module}]</div>` : ''}
                    <div class="log-msg ${isErr ? 'error-msg' : ''}">${escapeHtml(p.msg)}</div>
                </div>`;
            });

            container.innerHTML = html || `<div style="color: #8b949e; text-align: center; margin-top: 40px;">No logs match current filter.</div>`;

            if (autoScroll) {
                container.scrollTop = container.scrollHeight;
            }
        }

        function applyFilter() {
            renderLogs();
        }

        function toggleAutoScroll() {
            autoScroll = !autoScroll;
            const btn = document.getElementById('autoscrollBtn');
            btn.classList.toggle('active', autoScroll);
        }

        function toggleLive() {
            isLive = !isLive;
            const btn = document.getElementById('liveBtn');
            const dot = document.getElementById('liveIndicator');
            const statusText = document.getElementById('statusText');

            if (isLive) {
                btn.classList.add('active');
                btn.innerHTML = '<span>⏸ Live (1.5s)</span>';
                dot.className = 'live-dot';
                statusText.innerText = 'Streaming real-time logs';
                startPolling();
            } else {
                btn.classList.remove('active');
                btn.innerHTML = '<span>▶ Resume Stream</span>';
                dot.className = 'live-dot paused-dot';
                statusText.innerText = 'Stream paused';
                stopPolling();
            }
        }

        function startPolling() {
            stopPolling();
            pollInterval = setInterval(fetchLogs, 1500);
        }

        function stopPolling() {
            if (pollInterval) clearInterval(pollInterval);
        }

        function clearScreen() {
            rawLogLines = [];
            renderLogs();
        }

        function escapeHtml(str) {
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }

        // Initialize on load
        fetchLogs();
        startPolling();
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)



@router.get("/system-diagnostics")
async def run_system_diagnostics(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("configuration:read"))
):
    """
    Runs automated container-internal network, database, and storage diagnostics
    to detect root causes of ingestion or RAG pipeline failures.
    Secured via configuration:read RBAC permission.
    """

    import socket
    import time
    from sqlalchemy import text
    
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {},
        "egress_connectivity": {},
        "storage": {},
        "dns": {}
    }
    
    # 1. Database Check
    try:
        t0 = time.time()
        await db.execute(text("SELECT 1"))
        results["database"] = {
            "status": "HEALTHY",
            "latency_ms": round((time.time() - t0) * 1000, 2)
        }
    except Exception as db_err:
        results["database"] = {
            "status": "FAILED",
            "error": str(db_err)
        }
        
    # 2. DNS & Outbound Egress Check
    test_endpoints = [
        ("api.openai.com", "https://api.openai.com/v1/models"),
        ("generativelanguage.googleapis.com", "https://generativelanguage.googleapis.com"),
        ("huggingface.co", "https://huggingface.co")
    ]
    
    for host, url in test_endpoints:
        # DNS test
        try:
            ip = socket.gethostbyname(host)
            results["dns"][host] = {"resolved": True, "ip": ip}
        except Exception as dns_err:
            results["dns"][host] = {"resolved": False, "error": str(dns_err)}
            
        # HTTPS Egress test (2 second timeout)
        try:
            t0 = time.time()
            req = urllib.request.Request(url, headers={"User-Agent": "Backend-Diagnostics/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                results["egress_connectivity"][host] = {
                    "reachable": True,
                    "http_status": resp.status,
                    "latency_ms": round((time.time() - t0) * 1000, 2)
                }
        except urllib.error.HTTPError as http_err:
            # 401 or 404 still means network connectivity to the server succeeded!
            results["egress_connectivity"][host] = {
                "reachable": True,
                "http_status": http_err.code,
                "note": "Reachable (HTTP error response expected without auth)",
                "latency_ms": round((time.time() - t0) * 1000, 2)
            }
        except Exception as net_err:
            results["egress_connectivity"][host] = {
                "reachable": False,
                "error": str(net_err),
                "diagnosis": "Outbound internet access is BLOCKED or missing NAT gateway on this pod."
            }

    # 3. Storage write permissions
    storage_dirs = ["data/temp", "data/pending", "data/output", "logs"]
    for d in storage_dirs:
        try:
            os.makedirs(d, exist_ok=True)
            test_file = os.path.join(d, ".write_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            results["storage"][d] = {"writable": True}
        except Exception as s_err:
            results["storage"][d] = {"writable": False, "error": str(s_err)}
            
    return results


async def _verify_database_maintenance_auth(
    request: Request,
    x_admin_secret: Optional[str] = Header(None, alias="X-Admin-Secret"),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Verifies caller is authorized to perform database maintenance operations:
    1. Caller provides matching X-Admin-Secret header (for initial setup/bootstrap or CI/CD).
    2. OR authenticated staff user has configuration:write permission.
    """
    if x_admin_secret and x_admin_secret == settings.SECRET_KEY:
        return

    try:
        current_user = await get_current_user(request, db)
        guard = RequireAccess("configuration:write")
        await guard(current_user=current_user, db=db)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Admin access ('configuration:write') or valid 'X-Admin-Secret' header required.",
        )


@router.post("/db/reset-and-reseed", response_model=DatabaseResetResponse)
@router.post("/db/reset", response_model=DatabaseResetResponse)
async def endpoint_reset_and_reseed_db(
    req: DatabaseResetRequest,
    request: Request,
    x_admin_secret: Optional[str] = Header(None, alias="X-Admin-Secret"),
    db: AsyncSession = Depends(get_db),
):
    """
    Safely resets (truncates all tables with CASCADE) and reseeds default data:
    - Access permissions
    - System roles (ADMIN, FUNCTIONAL)
    - Default admin account (customizable via payload)
    - Initial medical categories
    - Baseline AppConfig keys

    Safety requirements:
    1. req.confirmation must equal "RESET_AND_RESEED"
    2. If in production, requires matching X-Admin-Secret header
    3. Caller must have configuration:write access or valid X-Admin-Secret
    """
    await _verify_database_maintenance_auth(request, x_admin_secret, db)

    if req.confirmation != "RESET_AND_RESEED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Safety confirmation failed. 'confirmation' field must be exactly 'RESET_AND_RESEED'.",
        )

    # Extra production guard: in production, require explicit secret authorization
    is_prod = str(settings.ENVIRONMENT).lower() in ("production", "prod")
    if is_prod and (not x_admin_secret or x_admin_secret != settings.SECRET_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Database reset is blocked in production unless authenticated via valid X-Admin-Secret header.",
        )

    result = await reset_and_reseed_database(
        session=db,
        admin_email=req.admin_email,
        admin_password=req.admin_password,
    )

    return DatabaseResetResponse(
        status="success",
        message="Database has been successfully reset and reseeded.",
        details=result,
    )


@router.post("/db/reseed", response_model=DatabaseResetResponse)
async def endpoint_reseed_db(
    request: Request,
    reset: bool = False,
    admin_email: str = "admin@mail.com",
    admin_password: str = "Erhadermies@123",
    x_admin_secret: Optional[str] = Header(None, alias="X-Admin-Secret"),
    db: AsyncSession = Depends(get_db),
):
    """
    Seeds baseline accesses, roles, admin user, categories, and config.
    - If reset=True: Truncates all tables first before reseeding.
    - If reset=False: Idempotently seeds missing records without deleting data.
    """
    await _verify_database_maintenance_auth(request, x_admin_secret, db)

    if reset:
        # Extra production guard: in production, require explicit secret authorization
        is_prod = str(settings.ENVIRONMENT).lower() in ("production", "prod")
        if is_prod and (not x_admin_secret or x_admin_secret != settings.SECRET_KEY):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Database reset is blocked in production unless authenticated via valid X-Admin-Secret header.",
            )

        result = await reset_and_reseed_database(
            session=db,
            admin_email=admin_email,
            admin_password=admin_password,
        )
        return DatabaseResetResponse(
            status="success",
            message="Database has been successfully reset and reseeded.",
            details=result,
        )

    result = await seed_database(
        session=db,
        admin_email=admin_email,
        admin_password=admin_password,
    )

    return DatabaseResetResponse(
        status="success",
        message="Database has been idempotently seeded with default baseline data.",
        details=result,
    )

