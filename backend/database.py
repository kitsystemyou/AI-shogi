import aiosqlite
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from .config import config

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sente_player TEXT NOT NULL,
    gote_player TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    winner TEXT,
    finish_reason TEXT,
    total_moves INTEGER NOT NULL DEFAULT 0,
    sfen_final TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    move_number INTEGER NOT NULL,
    player TEXT NOT NULL,
    model_name TEXT NOT NULL,
    usi TEXT NOT NULL,
    kif_text TEXT NOT NULL,
    sfen_after TEXT NOT NULL,
    board_text TEXT,
    sente_hand TEXT,
    gote_hand TEXT,
    ai_response TEXT,
    time_spent_ms INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE
);
"""

async def init_db():
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()

async def create_match(sente_player: str, gote_player: str) -> int:
    now = datetime.now().isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO matches (sente_player, gote_player, status, total_moves, created_at, updated_at)
            VALUES (?, ?, 'running', 0, ?, ?)
            """,
            (sente_player, gote_player, now, now)
        )
        await db.commit()
        return cursor.lastrowid

async def update_match_status(
    match_id: int,
    status: str,
    winner: Optional[str] = None,
    finish_reason: Optional[str] = None,
    total_moves: Optional[int] = None,
    sfen_final: Optional[str] = None,
    error_message: Optional[str] = None
):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        fields = ["status = ?", "updated_at = ?"]
        params = [status, now]

        if winner is not None:
            fields.append("winner = ?")
            params.append(winner)
        if finish_reason is not None:
            fields.append("finish_reason = ?")
            params.append(finish_reason)
        if total_moves is not None:
            fields.append("total_moves = ?")
            params.append(total_moves)
        if sfen_final is not None:
            fields.append("sfen_final = ?")
            params.append(sfen_final)
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)

        params.append(match_id)
        query = f"UPDATE matches SET {', '.join(fields)} WHERE id = ?"
        await db.execute(query, params)
        await db.commit()

async def mark_match_running(match_id: int) -> bool:
    """中断済み対局を再開状態にし、以前の終了情報をクリアします"""
    now = datetime.now().isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE matches
            SET status = 'running', winner = NULL, finish_reason = NULL,
                error_message = NULL, updated_at = ?
            WHERE id = ? AND status = 'aborted'
            """,
            (now, match_id)
        )
        await db.commit()
        return cursor.rowcount == 1

async def record_move(
    match_id: int,
    move_number: int,
    player: str,
    model_name: str,
    usi: str,
    kif_text: str,
    sfen_after: str,
    board_text: str = "",
    sente_hand: str = "",
    gote_hand: str = "",
    ai_response: str = "",
    time_spent_ms: int = 0
):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO moves (
                match_id, move_number, player, model_name, usi, kif_text,
                sfen_after, board_text, sente_hand, gote_hand, ai_response,
                time_spent_ms, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id, move_number, player, model_name, usi, kif_text,
                sfen_after, board_text, sente_hand, gote_hand, ai_response,
                time_spent_ms, now
            )
        )
        await db.execute(
            "UPDATE matches SET total_moves = ?, updated_at = ? WHERE id = ?",
            (move_number, now, match_id)
        )
        await db.commit()

async def get_matches(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM matches ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            (limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_match_by_id(match_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM matches WHERE id = ?",
            (match_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)

async def get_moves_by_match(match_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM moves WHERE match_id = ? ORDER BY move_number ASC",
            (match_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
