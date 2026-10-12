"""将棋エンジンの包括的な単体テスト (test_shogi_engine.py)"""

import unittest
import shogi
from backend.shogi_engine import (
    ShogiEngine,
    GameResult,
    IllegalMoveError,
    format_board_text,
    format_pieces_in_hand,
    move_to_japanese,
    get_legal_moves,
    check_game_status,
    calculate_jishogi_points,
)


class TestShogiEngine(unittest.TestCase):
    """ShogiEngine の基本動作および各種判定のテスト"""

    def setUp(self):
        self.engine = ShogiEngine()

    def test_initial_state(self):
        """初期局面の確認"""
        self.assertEqual(
            self.engine.sfen,
            "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"
        )
        self.assertEqual(self.engine.turn, shogi.BLACK)
        self.assertEqual(self.engine.turn_name, "先手")
        self.assertEqual(self.engine.move_number, 1)
        self.assertFalse(self.engine.is_check)

        # 持ち駒表示の確認
        self.assertEqual(self.engine.get_player_pieces_in_hand_text(shogi.BLACK), "なし")
        self.assertEqual(self.engine.get_player_pieces_in_hand_text(shogi.WHITE), "なし")
        self.assertEqual(self.engine.get_pieces_in_hand_text(), "先手: なし\n後手: なし")

        # 盤面テキストの確認
        board_text = self.engine.get_board_text()
        self.assertIn("▲歩", board_text)
        self.assertIn("△歩", board_text)
        self.assertIn("・", board_text)
        self.assertIn("９", board_text)
        self.assertIn("一", board_text)

        # 終局判定
        status = self.engine.get_game_status()
        self.assertFalse(status.is_over)
        self.assertEqual(status.result, GameResult.IN_PROGRESS)

    def test_legal_moves_and_japanese_notation(self):
        """合法手の生成と日本語表記の正確性確認"""
        moves = self.engine.get_legal_moves()
        self.assertEqual(len(moves), 30)

        # 7g7f (▲７六歩) が含まれるか
        move_7g7f = next((m for m in moves if m["usi"] == "7g7f"), None)
        self.assertIsNotNone(move_7g7f)
        self.assertEqual(move_7g7f["japanese"], "▲７六歩")
        self.assertEqual(move_7g7f["display"], "7g7f (▲７六歩)")

    def test_moves_progression_and_promotion(self):
        """指し手の進行、角交換、成り・不成の表記テスト"""
        # 1. 7g7f (▲７六歩)
        res1 = self.engine.apply_move("7g7f")
        self.assertEqual(res1["japanese"], "▲７六歩")
        self.assertEqual(self.engine.turn_name, "後手")
        self.assertEqual(self.engine.move_number, 2)

        # 2. 3c3d (△３四歩)
        res2 = self.engine.apply_move("3c3d")
        self.assertEqual(res2["japanese"], "△３四歩")
        self.assertEqual(self.engine.turn_name, "先手")
        self.assertEqual(self.engine.move_number, 3)

        # 角成と角不成のチェック
        moves = self.engine.get_legal_moves()
        m_prom = next((m for m in moves if m["usi"] == "8h2b+"), None)
        m_unprom = next((m for m in moves if m["usi"] == "8h2b"), None)
        self.assertIsNotNone(m_prom)
        self.assertIsNotNone(m_unprom)
        self.assertEqual(m_prom["japanese"], "▲２二角成")
        self.assertEqual(m_unprom["japanese"], "▲２二角不成")

        # 3. 8h2b+ (▲２二角成)
        res3 = self.engine.apply_move("8h2b+")
        self.assertEqual(res3["japanese"], "▲２二角成")
        # 先手の持ち駒に「角1」
        self.assertEqual(self.engine.get_player_pieces_in_hand_text(shogi.BLACK), "角1")

        # 4. 3a2b (△２二同銀)
        res4 = self.engine.apply_move("3a2b")
        self.assertEqual(res4["japanese"], "△２二銀")
        # 後手の持ち駒に「馬(角)1」
        self.assertEqual(self.engine.get_player_pieces_in_hand_text(shogi.WHITE), "角1")

        # 5. 駒打ちテスト B*4e (▲４五角打)
        res5 = self.engine.apply_move("B*4e")
        self.assertEqual(res5["japanese"], "▲４五角打")
        self.assertEqual(self.engine.get_player_pieces_in_hand_text(shogi.BLACK), "なし")

    def test_illegal_move_detection(self):
        """反則手・非合法手の検出テスト"""
        # 移動元に駒がない
        with self.assertRaises(IllegalMoveError) as ctx:
            self.engine.apply_move("5e5d")
        self.assertIn("移動元", str(ctx.exception))

        # 相手の駒を動かそうとする
        with self.assertRaises(IllegalMoveError) as ctx:
            self.engine.apply_move("3c3d")
        self.assertIn("相手の駒", str(ctx.exception))

        # 利きのない移動
        with self.assertRaises(IllegalMoveError) as ctx:
            self.engine.apply_move("7g7e")
        self.assertIn("利きではない", str(ctx.exception))

        # 持ち駒にない駒を打とうとする
        with self.assertRaises(IllegalMoveError) as ctx:
            self.engine.apply_move("P*5e")
        self.assertIn("持ち駒に「歩」がありません", str(ctx.exception))

        # 二歩の反則テスト
        # 先手の手番で歩を持たせる
        self.engine.board.add_piece_into_hand(shogi.PAWN, shogi.BLACK)
        with self.assertRaises(IllegalMoveError) as ctx:
            self.engine.apply_move("P*7f")  # 7筋には既に7gに歩がある
        self.assertIn("二歩", str(ctx.exception))

        # 行き所のない駒の反則テスト (1aの香車を取り除き、香車を持って1aに打つ)
        self.engine.board.remove_piece_at(shogi.A1)
        self.engine.board.add_piece_into_hand(shogi.LANCE, shogi.BLACK)
        with self.assertRaises(IllegalMoveError) as ctx:
            self.engine.apply_move("L*1a")  # 空きマスの1段目への香車打ち
        self.assertIn("行き所のない駒", str(ctx.exception))

        # 王手放置の反則テスト
        check_sfen = "4k4/9/9/9/9/9/9/4r4/4K4 b 9P9p 1"
        check_engine = ShogiEngine(check_sfen)
        self.assertTrue(check_engine.is_check)
        with self.assertRaises(IllegalMoveError) as ctx:
            check_engine.apply_move("P*1e")  # 王手を無視して無関係なマスに打つ
        self.assertIn("王手放置", str(ctx.exception))

    def test_checkmate(self):
        """1手詰め局面での詰み判定テスト"""
        # 5aに玉、5bに金、5cに銀 (紐が付いている詰み局面)
        mate_sfen = "4k4/4G4/4S4/9/9/9/9/9/4K4 w 2r2b3g3s4n4l18p 2"
        engine_mate = ShogiEngine(mate_sfen)
        status = engine_mate.get_game_status()
        self.assertTrue(status.is_over)
        self.assertEqual(status.result, GameResult.CHECKMATE)
        self.assertEqual(status.winner, shogi.BLACK)
        self.assertEqual(status.winner_str, "先手")
        self.assertIn("詰み", status.reason)

    def test_fourfold_repetition(self):
        """千日手判定テスト"""
        moves = [
            "2h3h", "8b7b",
            "3h2h", "7b8b",
            "2h3h", "8b7b",
            "3h2h", "7b8b",
            "2h3h", "8b7b",
            "3h2h", "7b8b",
        ]
        for m in moves:
            self.engine.apply_move(m)

        status = self.engine.get_game_status()
        self.assertTrue(status.is_over)
        self.assertEqual(status.result, GameResult.FOURFOLD_REPETITION)
        self.assertIsNone(status.winner)
        self.assertIn("千日手", status.reason)

    def test_max_moves_limit(self):
        """最大手数到達による引き分けテスト"""
        self.engine.apply_move("7g7f")
        self.engine.apply_move("3c3d")
        status = self.engine.get_game_status(max_moves=2)
        self.assertTrue(status.is_over)
        self.assertEqual(status.result, GameResult.MAX_MOVES)
        self.assertIn("最大手数", status.reason)

    def test_jishogi_points(self):
        """持将棋点数計算テスト"""
        points = self.engine.calculate_points()
        # 初期配置は大駒2枚(10点) + 小駒17枚(17点) = 27点
        self.assertEqual(points["black"]["total"], 27)
        self.assertEqual(points["white"]["total"], 27)
        self.assertEqual(points["black"]["camp"], 0)
        self.assertEqual(points["white"]["camp"], 0)

    def test_jishogi_entered_king(self):
        """相入玉による持将棋成立テスト"""
        # 先手玉が5a(1段目)、後手玉が5i(9段目)、それぞれ持ち駒により28点所持
        sfen = "4K4/9/9/9/9/9/9/9/4k4 b 2R2B4G4S2r2b4g4s 1"
        engine = ShogiEngine(sfen)
        status = engine.get_game_status()
        self.assertTrue(status.is_over)
        self.assertEqual(status.result, GameResult.JISHOGI)
        self.assertIn("持将棋", status.reason)

    def test_state_summary(self):
        """エンジンの全体状態サマリーの取得テスト"""
        summary = self.engine.get_state_summary()
        self.assertIn("sfen", summary)
        self.assertIn("turn_name", summary)
        self.assertIn("board_text", summary)
        self.assertIn("pieces_in_hand", summary)
        self.assertIn("legal_moves", summary)
        self.assertIn("is_game_over", summary)
        self.assertEqual(summary["legal_moves_count"], 30)


if __name__ == "__main__":
    unittest.main()
