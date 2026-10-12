"""APIおよび統合テストスクリプト (test_arena_integration.py)"""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from backend.app import app
from backend.database import init_db, get_matches, create_match, record_move, get_match_by_id, get_moves_by_match
from backend.shogi_engine import ShogiEngine
from backend.ai_service import AIService, build_shogi_context, PLAYER_GPT
from backend.match_runner import MatchRunner

class TestIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ["DATABASE_PATH"] = ":memory:"
        await init_db()

    async def test_database_and_moves(self):
        match_id = await create_match("JEV", "Gemini3.8flash-high")
        self.assertIsNotNone(match_id)

        engine = ShogiEngine()
        applied = engine.apply_move("7g7f")

        await record_move(
            match_id=match_id,
            move_number=1,
            player="sente",
            model_name="JEV",
            usi="7g7f",
            kif_text=applied["japanese"],
            sfen_after=applied["sfen"],
            board_text=engine.get_board_text(),
            sente_hand=engine.get_pieces_in_hand_text(),
            gote_hand="",
            ai_response='{"reason": "角道を開ける", "choice": "7g7f"}',
            time_spent_ms=120
        )

        match = await get_match_by_id(match_id)
        self.assertEqual(match["sente_player"], "JEV")
        self.assertEqual(match["gote_player"], "Gemini3.8flash-high")
        self.assertEqual(match["total_moves"], 1)

        moves = await get_moves_by_match(match_id)
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0]["usi"], "7g7f")
        self.assertIn("７六歩", moves[0]["kif_text"])

    def test_shogi_context_formatting(self):
        engine = ShogiEngine()
        state_text, criteria_dict, legal_moves_text = build_shogi_context(
            turn_name="先手",
            move_number=1,
            board_text=engine.get_board_text(),
            sfen=engine.sfen,
            pieces_in_hand_text=engine.get_pieces_in_hand_text(),
            history_moves=[],
            legal_moves=engine.get_legal_moves()
        )
        self.assertIn("手番: あなたの手番 (先手)", state_text)
        self.assertIn("7g7f", criteria_dict)
        self.assertIn("7g7f", legal_moves_text)

    async def test_openai_call_uses_configured_model_and_chat_completions(self):
        service = AIService()
        response = unittest.mock.Mock()
        response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"move": "7g7f", "reason": "歩を進める"}'
                }
            }]
        }
        client = unittest.mock.AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        engine = ShogiEngine()

        with (
            patch("backend.ai_service.config.OPENAI_API_KEY", "test-key"),
            patch("backend.ai_service.config.OPENAI_MODEL", "gpt-6-luna"),
            patch("backend.ai_service.config.OPENAI_BASE_URL", "https://api.openai.com/v1"),
            patch("backend.ai_service.httpx.AsyncClient", return_value=client),
        ):
            usi, reason, _ = await service._call_openai(
                engine.get_board_text(),
                "7g7f",
                engine.get_legal_moves()
            )

        self.assertEqual(usi, "7g7f")
        self.assertEqual(reason, "歩を進める")
        client.post.assert_awaited_once()
        args, kwargs = client.post.await_args
        self.assertEqual(args[0], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(kwargs["json"]["model"], "gpt-6-luna")
        self.assertEqual(kwargs["json"]["messages"][0]["role"], "developer")
        self.assertNotIn("temperature", kwargs["json"])
        self.assertEqual(
            kwargs["json"]["response_format"],
            {"type": "json_object"}
        )

    async def test_claude_call_omits_deprecated_temperature(self):
        service = AIService()
        response = unittest.mock.Mock()
        response.json.return_value = {
            "content": [{
                "type": "text",
                "text": '{"move": "7g7f", "reason": "歩を進める"}'
            }]
        }
        client = unittest.mock.AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        engine = ShogiEngine()

        with (
            patch("backend.ai_service.config.ANTHROPIC_API_KEY", "test-key"),
            patch("backend.ai_service.config.ANTHROPIC_MODEL", "claude-sonnet-5"),
            patch("backend.ai_service.httpx.AsyncClient", return_value=client),
        ):
            usi, reason, _ = await service._call_claude(
                engine.get_board_text(),
                "7g7f",
                engine.get_legal_moves()
            )

        self.assertEqual(usi, "7g7f")
        self.assertEqual(reason, "歩を進める")
        client.post.assert_awaited_once()
        args, kwargs = client.post.await_args
        self.assertEqual(args[0], "https://api.anthropic.com/v1/messages")
        self.assertEqual(kwargs["json"]["model"], "claude-sonnet-5")
        self.assertNotIn("temperature", kwargs["json"])

    async def test_llm_http_429_is_preserved_in_move_result(self):
        service = AIService()
        request = httpx.Request("POST", "https://example.com")
        response = httpx.Response(429, request=request)
        service._call_openai = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "rate limited", request=request, response=response
            )
        )
        engine = ShogiEngine()

        result = await service.get_next_move(
            player_name=PLAYER_GPT,
            turn_name="先手",
            move_number=1,
            board_text=engine.get_board_text(),
            sfen=engine.sfen,
            pieces_in_hand_text=engine.get_pieces_in_hand_text(),
            history_moves=[],
            legal_moves=engine.get_legal_moves()
        )

        self.assertEqual(result["http_status"], 429)

    async def test_llm_http_402_is_preserved_in_move_result(self):
        service = AIService()
        request = httpx.Request("POST", "https://example.com")
        response = httpx.Response(402, request=request)
        service._call_openai = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "payment required", request=request, response=response
            )
        )
        engine = ShogiEngine()

        result = await service.get_next_move(
            player_name=PLAYER_GPT,
            turn_name="先手",
            move_number=1,
            board_text=engine.get_board_text(),
            sfen=engine.sfen,
            pieces_in_hand_text=engine.get_pieces_in_hand_text(),
            history_moves=[],
            legal_moves=engine.get_legal_moves()
        )

        self.assertEqual(result["http_status"], 402)

    async def test_match_aborts_when_llm_returns_http_429(self):
        runner = MatchRunner()
        runner.broadcast = AsyncMock()
        move_result = {
            "usi": "7g7f",
            "http_status": 429,
            "time_spent_ms": 1
        }

        with (
            patch("backend.match_runner.ai_service.get_next_move", new=AsyncMock(return_value=move_result)),
            patch("backend.match_runner.update_match_status", new=AsyncMock()) as update_status,
            patch("backend.match_runner.record_move", new=AsyncMock()) as record_move_mock,
        ):
            await runner._run_match_loop(98765, "GPT-Luna-high", "JEV")

        update_status.assert_awaited_once()
        self.assertEqual(update_status.await_args.kwargs["status"], "aborted")
        self.assertEqual(update_status.await_args.kwargs["finish_reason"], "api_rate_limited")
        record_move_mock.assert_not_awaited()
        runner.broadcast.assert_any_await(
            98765,
            "aborted",
            {"reason": "LLM API のレート制限により対局を中断しました"}
        )

    async def test_match_aborts_when_llm_returns_http_402(self):
        runner = MatchRunner()
        runner.broadcast = AsyncMock()
        move_result = {
            "usi": "7g7f",
            "http_status": 402,
            "time_spent_ms": 1
        }

        with (
            patch("backend.match_runner.ai_service.get_next_move", new=AsyncMock(return_value=move_result)),
            patch("backend.match_runner.update_match_status", new=AsyncMock()) as update_status,
            patch("backend.match_runner.record_move", new=AsyncMock()) as record_move_mock,
        ):
            await runner._run_match_loop(98766, "GPT-Luna-high", "JEV")

        update_status.assert_awaited_once()
        self.assertEqual(update_status.await_args.kwargs["status"], "aborted")
        self.assertEqual(update_status.await_args.kwargs["finish_reason"], "api_payment_required")
        record_move_mock.assert_not_awaited()
        runner.broadcast.assert_any_await(
            98766,
            "aborted",
            {"reason": "LLM API が HTTP 402 を返したため対局を中断しました"}
        )

    async def test_resume_restores_saved_position_and_move_history(self):
        runner = MatchRunner()
        saved_move = {
            "move_number": 1,
            "player": "sente",
            "model_name": "GPT-Luna-high",
            "usi": "7g7f",
            "kif_text": "▲７六歩",
        }

        with (
            patch("backend.match_runner.get_match_by_id", new=AsyncMock(return_value={
                "status": "aborted",
                "sente_player": "GPT-Luna-high",
                "gote_player": "JEV",
            })),
            patch("backend.match_runner.get_moves_by_match", new=AsyncMock(return_value=[saved_move])),
            patch("backend.match_runner.mark_match_running", new=AsyncMock(return_value=True)),
            patch.object(runner, "_run_match_loop", new=AsyncMock()) as run_loop,
        ):
            await runner.resume_match(123)
            await runner.active_tasks[123]

        args = run_loop.await_args
        self.assertEqual(args.kwargs["engine"].move_number, 2)
        expected_engine = ShogiEngine()
        expected_engine.apply_move("7g7f")
        self.assertEqual(args.kwargs["engine"].sfen, expected_engine.sfen)
        self.assertEqual(args.kwargs["history_moves"], [saved_move])

if __name__ == "__main__":
    unittest.main()
