"""FastAPI メインアプリケーション (app.py)

将棋対局WebアプリケーションのバックエンドAPIおよびフロントエンド配信を提供します。
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import config
from .database import (
    init_db,
    get_matches,
    get_match_by_id,
    get_moves_by_match
)
from .ai_service import SUPPORTED_PLAYERS
from .match_runner import match_runner

app = FastAPI(title="AI & JEV Shogi Arena", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


class MatchCreateRequest(BaseModel):
    sente_player: str
    gote_player: str


class ConfigUpdateRequest(BaseModel):
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    anthropic_model: Optional[str] = None
    jev_api_key: Optional[str] = None
    jev_model: Optional[str] = None
    jev_endpoint: Optional[str] = None


@app.on_event("startup")
async def startup_event():
    await init_db()


@app.get("/api/players")
async def get_players():
    """選択可能なプレイヤー一覧および各APIキーの設定状態を返します"""
    return {
        "players": [
            {
                "id": p,
                "name": p,
                "provider": (
                    "OpenAI" if "GPT" in p else
                    "Google Gemini" if "Gemini" in p else
                    "Anthropic Claude" if "Claude" in p else
                    "TypeSafe AI"
                ),
                "has_key": bool(
                    (config.OPENAI_API_KEY if "GPT" in p else
                     config.GEMINI_API_KEY if "Gemini" in p else
                     config.ANTHROPIC_API_KEY if "Claude" in p else
                     config.JEV_API_KEY)
                )
            }
            for p in SUPPORTED_PLAYERS
        ]
    }


@app.post("/api/matches")
async def create_new_match(req: MatchCreateRequest):
    """新しい将棋対戦を作成し、バックグラウンドで開始します"""
    if req.sente_player not in SUPPORTED_PLAYERS:
        raise HTTPException(status_code=400, detail=f"無効な先手プレイヤーです: {req.sente_player}")
    if req.gote_player not in SUPPORTED_PLAYERS:
        raise HTTPException(status_code=400, detail=f"無効な後手プレイヤーです: {req.gote_player}")

    try:
        match_id = await match_runner.start_match(req.sente_player, req.gote_player)
        return {
            "match_id": match_id,
            "sente": req.sente_player,
            "gote": req.gote_player,
            "status": "running"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/matches")
async def list_matches(limit: int = 50, offset: int = 0):
    """対局履歴一覧を取得します"""
    matches = await get_matches(limit=limit, offset=offset)
    return {"matches": matches}


@app.get("/api/matches/{match_id}")
async def get_match_detail(match_id: int):
    """特定の対局情報および全棋譜履歴を取得します"""
    match = await get_match_by_id(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="対局が見つかりません")
    moves = await get_moves_by_match(match_id)
    return {
        "match": match,
        "moves": moves,
        "is_running": match_runner.is_match_running(match_id)
    }


@app.post("/api/matches/{match_id}/stop")
async def stop_match(match_id: int):
    """進行中の対局を中断します"""
    success = await match_runner.stop_match(match_id)
    if not success:
        return {"message": "対局は既に終了しているか存在しません"}
    return {"message": "対局を中断しました"}

@app.post("/api/matches/{match_id}/resume")
async def resume_match(match_id: int):
    """中断済み対局を棋譜の続きから再開します"""
    try:
        await match_runner.resume_match(match_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"match_id": match_id, "status": "running"}

@app.get("/api/matches/{match_id}/events")
async def sse_events(match_id: int):
    """SSE (Server-Sent Events) によるリアルタイム指し手配信"""
    match = await get_match_by_id(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="対局が見つかりません")

    async def event_generator():
        queue = await match_runner.subscribe(match_id)
        try:
            # 接続時に初期状態を送信
            initial_moves = await get_moves_by_match(match_id)
            current_match = await get_match_by_id(match_id)
            init_payload = {
                "event": "connected",
                "data": {
                    "match": current_match,
                    "moves_count": len(initial_moves),
                    "is_running": match_runner.is_match_running(match_id)
                }
            }
            yield f"data: {json.dumps(init_payload)}\n\n"

            while True:
                # 30秒ごとにハートビート送信
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await match_runner.unsubscribe(match_id, queue)

    import json
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/config")
async def get_config_status():
    """現在の環境設定および各キーの設定有無を取得します"""
    return {
        "openai": {
            "has_key": bool(config.OPENAI_API_KEY),
            "model": config.OPENAI_MODEL,
            "base_url": config.OPENAI_BASE_URL,
        },
        "gemini": {
            "has_key": bool(config.GEMINI_API_KEY),
            "model": config.GEMINI_MODEL,
        },
        "anthropic": {
            "has_key": bool(config.ANTHROPIC_API_KEY),
            "model": config.ANTHROPIC_MODEL,
        },
        "jev": {
            "has_key": bool(config.JEV_API_KEY),
            "model": config.JEV_MODEL,
            "endpoint": config.JEV_ENDPOINT,
        }
    }


@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    """UI上から一時的にAPIキーや設定を更新します"""
    if req.openai_api_key is not None:
        config.OPENAI_API_KEY = req.openai_api_key
    if req.openai_model is not None:
        config.OPENAI_MODEL = req.openai_model

    if req.gemini_api_key is not None:
        config.GEMINI_API_KEY = req.gemini_api_key
    if req.gemini_model is not None:
        config.GEMINI_MODEL = req.gemini_model

    if req.anthropic_api_key is not None:
        config.ANTHROPIC_API_KEY = req.anthropic_api_key
    if req.anthropic_model is not None:
        config.ANTHROPIC_MODEL = req.anthropic_model

    if req.jev_api_key is not None:
        config.JEV_API_KEY = req.jev_api_key
    if req.jev_model is not None:
        config.JEV_MODEL = req.jev_model
    if req.jev_endpoint is not None:
        config.JEV_ENDPOINT = req.jev_endpoint

    return {"message": "設定を更新しました", "config": await get_config_status()}


# フロントエンド配信
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(FRONTEND_DIR / "index.html")
