"""対局実行・進行管理モジュール (match_runner.py)

バックグラウンドで対局を1手ずつ進行し、
DBへの記録とリアルタイムイベント通知を行います。
"""

import asyncio
import json
import logging
import traceback
from typing import Any, Dict, List, Optional, Set
import shogi

from .config import config
from .database import (
    create_match,
    update_match_status,
    mark_match_running,
    record_move,
    get_match_by_id,
    get_moves_by_match
)
from .shogi_engine import (
    ShogiEngine,
    GameResult,
    IllegalMoveError
)
from .ai_service import ai_service, SUPPORTED_PLAYERS

logger = logging.getLogger("match_runner")


class MatchRunner:
    def __init__(self):
        # 進行中のタスク {match_id: Task}
        self.active_tasks: Dict[int, asyncio.Task] = {}
        # 中断フラグ {match_id: bool}
        self.stop_requested: Set[int] = set()
        # SSEなどの購読者用キュー {match_id: [asyncio.Queue]}
        self.subscribers: Dict[int, List[asyncio.Queue]] = {}

    def is_match_running(self, match_id: int) -> bool:
        task = self.active_tasks.get(match_id)
        return task is not None and not task.done()

    async def subscribe(self, match_id: int) -> asyncio.Queue:
        q = asyncio.Queue()
        if match_id not in self.subscribers:
            self.subscribers[match_id] = []
        self.subscribers[match_id].append(q)
        return q

    async def unsubscribe(self, match_id: int, q: asyncio.Queue):
        if match_id in self.subscribers:
            if q in self.subscribers[match_id]:
                self.subscribers[match_id].remove(q)
            if not self.subscribers[match_id]:
                del self.subscribers[match_id]

    async def broadcast(self, match_id: int, event_type: str, data: Dict[str, Any]):
        if match_id in self.subscribers:
            payload = json.dumps({"event": event_type, "data": data, "match_id": match_id})
            for q in list(self.subscribers[match_id]):
                try:
                    await q.put(payload)
                except Exception:
                    pass

    async def start_match(self, sente_player: str, gote_player: str) -> int:
        """新規対局を作成し、バックグラウンドで対局を開始します"""
        if sente_player not in SUPPORTED_PLAYERS:
            raise ValueError(f"未対応の先手プレイヤーです: {sente_player}")
        if gote_player not in SUPPORTED_PLAYERS:
            raise ValueError(f"未対応の後手プレイヤーです: {gote_player}")

        match_id = await create_match(sente_player, gote_player)
        task = asyncio.create_task(self._run_match_loop(match_id, sente_player, gote_player))
        self.active_tasks[match_id] = task
        return match_id

    async def resume_match(self, match_id: int) -> None:
        """中断済み対局を棋譜から復元し、同じ対局として再開します"""
        match = await get_match_by_id(match_id)
        if not match:
            raise LookupError(f"対局が見つかりません: {match_id}")
        if self.is_match_running(match_id) or match["status"] != "aborted":
            raise ValueError("中断済みの対局のみ再開できます")

        moves = await get_moves_by_match(match_id)
        engine = ShogiEngine()
        for move in moves:
            if move["move_number"] != engine.move_number:
                raise ValueError(
                    f"棋譜の手数が不連続です: {move['move_number']}手目"
                )
            try:
                engine.apply_move(move["usi"])
            except IllegalMoveError as e:
                raise ValueError(
                    f"棋譜を再現できません ({move['move_number']}手目): {e}"
                ) from e

        if not await mark_match_running(match_id):
            raise ValueError("対局状態が変更されたため再開できません")

        task = asyncio.create_task(self._run_match_loop(
            match_id,
            match["sente_player"],
            match["gote_player"],
            engine=engine,
            history_moves=moves
        ))
        self.active_tasks[match_id] = task

    async def stop_match(self, match_id: int) -> bool:
        """対局の中断をリクエストします"""
        if self.is_match_running(match_id):
            self.stop_requested.add(match_id)
            task = self.active_tasks.get(match_id)
            if task:
                task.cancel()
            await update_match_status(
                match_id=match_id,
                status="aborted",
                finish_reason="aborted_by_user"
            )
            await self.broadcast(match_id, "aborted", {"reason": "ユーザーにより対局が中断されました"})
            return True
        return False

    async def _run_match_loop(
        self,
        match_id: int,
        sente_player: str,
        gote_player: str,
        engine: Optional[ShogiEngine] = None,
        history_moves: Optional[List[Dict[str, Any]]] = None
    ):
        engine = engine or ShogiEngine()
        history_moves = history_moves or []

        logger.info(f"対局開始 [ID: {match_id}]: 先手={sente_player} vs 後手={gote_player}")
        await self.broadcast(match_id, "start", {
            "match_id": match_id,
            "sente": sente_player,
            "gote": gote_player,
            "sfen": engine.sfen
        })

        try:
            while True:
                # 中断確認
                if match_id in self.stop_requested:
                    logger.info(f"対局中断 [ID: {match_id}]")
                    break

                # 終局判定
                status = engine.get_game_status(max_moves=config.MAX_MOVES)
                if status.is_over:
                    winner_str = status.winner_str  # "sente", "gote", "draw", etc.
                    reason_str = status.reason
                    logger.info(f"対局終了 [ID: {match_id}]: 結果={winner_str}, 理由={reason_str}")
                    await update_match_status(
                        match_id=match_id,
                        status="finished",
                        winner=winner_str,
                        finish_reason=reason_str,
                        total_moves=engine.move_number - 1,
                        sfen_final=engine.sfen
                    )
                    await self.broadcast(match_id, "finished", {
                        "winner": winner_str,
                        "reason": reason_str,
                        "total_moves": engine.move_number - 1,
                        "sfen": engine.sfen
                    })
                    break

                current_color = engine.turn  # shogi.BLACK or shogi.WHITE
                current_player_name = sente_player if current_color == shogi.BLACK else gote_player
                player_role = "sente" if current_color == shogi.BLACK else "gote"
                turn_label = "先手" if current_color == shogi.BLACK else "後手"
                current_move_number = engine.move_number

                # 盤面情報収集
                board_text = engine.get_board_text()
                sfen = engine.sfen
                hand_text = engine.get_pieces_in_hand_text()
                legal_moves = engine.get_legal_moves()

                # 手番通知
                await self.broadcast(match_id, "thinking", {
                    "move_number": current_move_number,
                    "turn": player_role,
                    "player_name": current_player_name
                })

                # AI呼び出し (API呼び出し)
                try:
                    move_result = await ai_service.get_next_move(
                        player_name=current_player_name,
                        turn_name=turn_label,
                        move_number=current_move_number,
                        board_text=board_text,
                        sfen=sfen,
                        pieces_in_hand_text=hand_text,
                        history_moves=history_moves,
                        legal_moves=legal_moves
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"AI呼び出し中の予期せぬエラー: {e}", exc_info=True)
                    # 反則負けとして処理
                    loser = player_role
                    winner = "gote" if loser == "sente" else "sente"
                    await update_match_status(
                        match_id=match_id,
                        status="error",
                        winner=winner,
                        finish_reason="api_exception",
                        error_message=str(e),
                        total_moves=current_move_number - 1,
                        sfen_final=engine.sfen
                    )
                    await self.broadcast(match_id, "error", {"error": str(e), "winner": winner})
                    break

                chosen_usi = move_result.get("usi")
                reason = move_result.get("reason", "")
                raw_resp = move_result.get("raw_response")
                time_spent = move_result.get("time_spent_ms", 0)

                http_status = move_result.get("http_status")
                if http_status in (402, 429):
                    if http_status == 402:
                        finish_reason = "api_payment_required"
                        message = "LLM API が HTTP 402 を返したため対局を中断しました"
                    else:
                        finish_reason = "api_rate_limited"
                        message = "LLM API のレート制限により対局を中断しました"
                    logger.warning(f"対局中断 [ID: {match_id}]: HTTP {http_status}")
                    await update_match_status(
                        match_id=match_id,
                        status="aborted",
                        finish_reason=finish_reason,
                        error_message=message,
                        total_moves=current_move_number - 1,
                        sfen_final=engine.sfen
                    )
                    await self.broadcast(match_id, "aborted", {
                        "reason": message
                    })
                    break

                if not chosen_usi:
                    # 指し手なし（投了または詰み）
                    loser = player_role
                    winner = "gote" if loser == "sente" else "sente"
                    await update_match_status(
                        match_id=match_id,
                        status="finished",
                        winner=winner,
                        finish_reason="resignation_no_move",
                        total_moves=current_move_number - 1,
                        sfen_final=engine.sfen
                    )
                    await self.broadcast(match_id, "finished", {
                        "winner": winner,
                        "reason": f"{current_player_name} が指し手を返さなかったため投了",
                        "total_moves": current_move_number - 1,
                        "sfen": engine.sfen
                    })
                    break

                # 指し手を盤面に適用
                try:
                    applied = engine.apply_move(chosen_usi)
                except IllegalMoveError as ie:
                    logger.warning(f"反則手発生: {chosen_usi} ({ie})")
                    loser = player_role
                    winner = "gote" if loser == "sente" else "sente"
                    await update_match_status(
                        match_id=match_id,
                        status="finished",
                        winner=winner,
                        finish_reason=f"illegal_move: {ie.reason}",
                        total_moves=current_move_number,
                        sfen_final=engine.sfen
                    )
                    await self.broadcast(match_id, "finished", {
                        "winner": winner,
                        "reason": f"反則手 ({ie.reason}) により {current_player_name} の反則負け",
                        "total_moves": current_move_number,
                        "sfen": engine.sfen
                    })
                    break

                kif_text = applied["japanese"]
                sfen_after = applied["sfen"]

                # 履歴更新
                move_record = {
                    "move_number": current_move_number,
                    "player": player_role,
                    "model_name": current_player_name,
                    "usi": chosen_usi,
                    "kif_text": kif_text,
                    "sfen_after": sfen_after,
                    "board_text": engine.get_board_text(),
                    "sente_hand": engine.get_player_pieces_in_hand_text(shogi.BLACK),
                    "gote_hand": engine.get_player_pieces_in_hand_text(shogi.WHITE),
                    "ai_response": json.dumps({"reason": reason, "raw": raw_resp}, ensure_ascii=False) if raw_resp else reason,
                    "time_spent_ms": time_spent
                }
                history_moves.append(move_record)

                # DB保存
                await record_move(
                    match_id=match_id,
                    move_number=current_move_number,
                    player=player_role,
                    model_name=current_player_name,
                    usi=chosen_usi,
                    kif_text=kif_text,
                    sfen_after=sfen_after,
                    board_text=move_record["board_text"],
                    sente_hand=move_record["sente_hand"],
                    gote_hand=move_record["gote_hand"],
                    ai_response=move_record["ai_response"],
                    time_spent_ms=time_spent
                )

                # リアルタイム通知
                await self.broadcast(match_id, "move", {
                    "move": move_record,
                    "summary": engine.get_state_summary(max_moves=config.MAX_MOVES)
                })

                # APIレートリミット対策で少し待機 (0.3秒)
                await asyncio.sleep(0.3)

        except asyncio.CancelledError:
            logger.info(f"対局タスクがキャンセルされました [ID: {match_id}]")
        except Exception as e:
            logger.error(f"対局ループ中の致命的エラー [ID: {match_id}]: {e}", exc_info=True)
            await update_match_status(
                match_id=match_id,
                status="error",
                error_message=str(e),
                total_moves=engine.move_number - 1,
                sfen_final=engine.sfen
            )
            await self.broadcast(match_id, "error", {"error": str(e)})
        finally:
            if match_id in self.active_tasks:
                del self.active_tasks[match_id]
            if match_id in self.stop_requested:
                self.stop_requested.remove(match_id)

match_runner = MatchRunner()
