"""将棋エンジンモジュール (shogi_engine.py)

python-shogi ライブラリをラップし、以下の機能を提供します：
- 盤面状況から SFEN 文字列の生成
- 視覚的なテキスト盤面表現 (9x9のマス目、▲/△/・ 表記)
- 持ち駒の日本語表記 (例: 「先手: 歩2 銀1」「後手: なし」)
- 手番、手数の取得
- 合法手一覧 (USI文字列および日本語表記)
- USIによる指し手適用および反則手の詳細検知
- 終局判定 (詰み、王手放置・二歩・打ち歩詰め等の反則、千日手、持将棋、最大手数判定)
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import shogi

# ---------------------------------------------------------------------------
# 定数定義
# ---------------------------------------------------------------------------

# 筋（File）の全角数字
KANJI_FILES: Dict[int, str] = {
    1: "１", 2: "２", 3: "３", 4: "４", 5: "５",
    6: "６", 7: "７", 8: "８", 9: "９"
}

# 段（Rank）の漢数字
KANJI_RANKS: Dict[int, str] = {
    1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
    6: "六", 7: "七", 8: "八", 9: "九"
}

# 駒の種類と日本語表記 (標準/詳細表記)
PIECE_NAMES: Dict[int, str] = {
    shogi.PAWN: "歩",
    shogi.LANCE: "香",
    shogi.KNIGHT: "桂",
    shogi.SILVER: "銀",
    shogi.GOLD: "金",
    shogi.BISHOP: "角",
    shogi.ROOK: "飛",
    shogi.KING: "玉",
    shogi.PROM_PAWN: "と",
    shogi.PROM_LANCE: "成香",
    shogi.PROM_KNIGHT: "成桂",
    shogi.PROM_SILVER: "成銀",
    shogi.PROM_BISHOP: "馬",
    shogi.PROM_ROOK: "竜",
}

# 盤面表示用の1文字略称 (全角幅揃え用)
PIECE_NAMES_COMPACT: Dict[int, str] = {
    shogi.PAWN: "歩",
    shogi.LANCE: "香",
    shogi.KNIGHT: "桂",
    shogi.SILVER: "銀",
    shogi.GOLD: "金",
    shogi.BISHOP: "角",
    shogi.ROOK: "飛",
    shogi.KING: "玉",
    shogi.PROM_PAWN: "と",
    shogi.PROM_LANCE: "杏",
    shogi.PROM_KNIGHT: "圭",
    shogi.PROM_SILVER: "全",
    shogi.PROM_BISHOP: "馬",
    shogi.PROM_ROOK: "竜",
}

# 成ることができる駒種
PROMOTABLE_PIECES = {
    shogi.PAWN,
    shogi.LANCE,
    shogi.KNIGHT,
    shogi.SILVER,
    shogi.BISHOP,
    shogi.ROOK,
}

# 持ち駒の表示順 (飛, 角, 金, 銀, 桂, 香, 歩)
HAND_PIECE_ORDER = [
    shogi.ROOK,
    shogi.BISHOP,
    shogi.GOLD,
    shogi.SILVER,
    shogi.KNIGHT,
    shogi.LANCE,
    shogi.PAWN,
]

# 持将棋・点数計算用の駒点数 (大駒5点、小駒1点、玉0点)
PIECE_POINTS: Dict[int, int] = {
    shogi.PAWN: 1,
    shogi.LANCE: 1,
    shogi.KNIGHT: 1,
    shogi.SILVER: 1,
    shogi.GOLD: 1,
    shogi.BISHOP: 5,
    shogi.ROOK: 5,
    shogi.KING: 0,
    shogi.PROM_PAWN: 1,
    shogi.PROM_LANCE: 1,
    shogi.PROM_KNIGHT: 1,
    shogi.PROM_SILVER: 1,
    shogi.PROM_BISHOP: 5,
    shogi.PROM_ROOK: 5,
}


# ---------------------------------------------------------------------------
# 例外クラス
# ---------------------------------------------------------------------------

class ShogiEngineError(Exception):
    """将棋エンジンの基底例外クラス"""
    pass


class IllegalMoveError(ShogiEngineError):
    """非合法手や反則手が指定された場合の例外"""
    def __init__(self, usi: str, reason: str):
        self.usi = usi
        self.reason = reason
        super().__init__(f"反則手または非合法手です [{usi}]: {reason}")


# ---------------------------------------------------------------------------
# 終局判定結果クラス
# ---------------------------------------------------------------------------

class GameResult(str, Enum):
    """対局結果の種別"""
    IN_PROGRESS = "in_progress"                   # 対局中
    CHECKMATE = "checkmate"                       # 詰み
    STALEMATE = "stalemate"                       # ステイルメイト (合法手なし)
    FOURFOLD_REPETITION = "fourfold_repetition"   # 千日手 (引き分け)
    PERPETUAL_CHECK = "perpetual_check"           # 連続王手の千日手 (反則負け)
    JISHOGI = "jishogi"                           # 持将棋 (合意または点数規定)
    MAX_MOVES = "max_moves"                       # 最大手数到達 (引き分け)
    ILLEGAL_MOVE = "illegal_move"                 # 反則負け


@dataclass
class GameStatus:
    """終局判定の詳細情報"""
    is_over: bool
    result: GameResult
    winner: Optional[int]              # shogi.BLACK(0), shogi.WHITE(1), または None(引き分け/対局中)
    winner_str: Optional[str]          # "先手", "後手", または None
    reason: str                        # 判定理由の日本語説明


# ---------------------------------------------------------------------------
# ユーティリティ関数
# ---------------------------------------------------------------------------

def get_east_asian_width(s: str) -> int:
    """全角・半角を考慮した文字列の表示幅を計算します"""
    w = 0
    for ch in s:
        status = unicodedata.east_asian_width(ch)
        w += 2 if status in ("F", "W", "A") else 1
    return w


def pad_cell(text: str, target_width: int = 6) -> str:
    """指定幅になるよう左右均等に半角スペースでパディングします"""
    w = get_east_asian_width(text)
    pad = max(0, target_width - w)
    left = pad // 2
    right = pad - left
    return (" " * left) + text + (" " * right)


def square_to_japanese(sq: int) -> str:
    """マス目のインデックス (0..80) を日本語座標文字列 (例: '７六') に変換します"""
    file_num = 9 - (sq % 9)
    rank_num = (sq // 9) + 1
    return f"{KANJI_FILES[file_num]}{KANJI_RANKS[rank_num]}"


def is_enemy_camp(sq: int, turn: int) -> bool:
    """指定マスがその手番にとって敵陣 (先手なら1〜3段目、後手なら7〜9段目) かどうかを判定します"""
    rank_num = (sq // 9) + 1
    if turn == shogi.BLACK:
        return rank_num <= 3
    else:
        return rank_num >= 7


def format_turn(turn: int) -> str:
    """手番を「先手」または「後手」に変換します"""
    return "先手" if turn == shogi.BLACK else "後手"


def format_pieces_in_hand_single(board: shogi.Board, color: int) -> str:
    """
    指定した側の持ち駒を日本語文字列で整形します。
    例: 「歩2 銀1」「なし」
    """
    hand = board.pieces_in_hand[color]
    parts: List[str] = []
    for piece_type in HAND_PIECE_ORDER:
        count = hand.get(piece_type, 0)
        if count > 0:
            name = PIECE_NAMES.get(piece_type, "")
            parts.append(f"{name}{count}")
    return " ".join(parts) if parts else "なし"


def format_pieces_in_hand(board: shogi.Board) -> str:
    """
    先手・後手双方の持ち駒を日本語表記で返します。
    例:
      先手: 歩2 銀1
      後手: なし
    """
    black_hand = format_pieces_in_hand_single(board, shogi.BLACK)
    white_hand = format_pieces_in_hand_single(board, shogi.WHITE)
    return f"先手: {black_hand}\n後手: {white_hand}"


def move_to_japanese(board: shogi.Board, move: shogi.Move) -> str:
    """
    指し手 (shogi.Move) を日本語表記に変換します。
    例:
      ▲７六歩
      ▲５五歩打
      ▲２二角成
      ▲２二角不成
      △３四歩
    """
    turn_mark = "▲" if board.turn == shogi.BLACK else "△"
    to_sq_str = square_to_japanese(move.to_square)

    if move.from_square is None:
        # 持ち駒を打つ場合
        piece_type = move.drop_piece_type
        piece_name = PIECE_NAMES.get(piece_type, "")
        return f"{turn_mark}{to_sq_str}{piece_name}打"
    else:
        # 盤上の駒を移動する場合
        piece = board.piece_at(move.from_square)
        if piece is None:
            return f"{turn_mark}{to_sq_str}不明"

        piece_name = PIECE_NAMES.get(piece.piece_type, "")

        if move.promotion:
            return f"{turn_mark}{to_sq_str}{piece_name}成"
        else:
            # 成れる駒で敵陣が絡む移動だが不成を選択した場合
            if piece.piece_type in PROMOTABLE_PIECES:
                can_promote = (
                    is_enemy_camp(move.from_square, board.turn) or
                    is_enemy_camp(move.to_square, board.turn)
                )
                if can_promote:
                    return f"{turn_mark}{to_sq_str}{piece_name}不成"
            return f"{turn_mark}{to_sq_str}{piece_name}"


def format_board_text(board: shogi.Board, style: str = "detailed", show_labels: bool = True) -> str:
    """
    9x9の盤面を視覚的なテキスト形式で生成します。
    各マス: 先手「▲歩」, 後手「△歩」, 空き「・」
    成銀なども等幅フォントで崩れないよう全角幅で均等配置します。

    :param board: python-shogi の Board インスタンス
    :param style: "detailed" (「成銀」など2文字表記、全角3文字幅揃え)
                  または "compact" (「全」など1文字略称、全角2文字幅揃え)
    :param show_labels: 筋・段のラベルおよび枠線を表示するかどうか
    """
    name_map = PIECE_NAMES if style == "detailed" else PIECE_NAMES_COMPACT
    cell_width = 6 if style == "detailed" else 4
    empty_cell = "・"

    rows: List[str] = []
    col_labels = "  ９    ８    ７    ６    ５    ４    ３    ２    １" if style == "detailed" else "  ９  ８  ７  ６  ５  ４  ３  ２  １"
    separator = "+" + ("-" * ((cell_width + 1) * 9 - 1)) + "+"

    if show_labels:
        rows.append(col_labels)
        rows.append(separator)

    for row_idx in range(9):
        cell_strs: List[str] = []
        for col_idx in range(9):
            # 9a(0), 8a(1), ..., 1a(8) の順
            sq = row_idx * 9 + col_idx
            piece = board.piece_at(sq)
            if piece is None:
                cell_text = pad_cell(empty_cell, cell_width)
            else:
                mark = "▲" if piece.color == shogi.BLACK else "△"
                pname = name_map.get(piece.piece_type, "")
                cell_text = pad_cell(f"{mark}{pname}", cell_width)
            cell_strs.append(cell_text)

        row_content = "|" + "|".join(cell_strs) + "|"
        if show_labels:
            rank_label = " " + KANJI_RANKS[row_idx + 1]
            rows.append(row_content + rank_label)
        else:
            rows.append(row_content)

    if show_labels:
        rows.append(separator)

    return "\n".join(rows)


def get_legal_moves(board: shogi.Board) -> List[Dict[str, str]]:
    """
    現在の局面の合法手一覧を生成します。
    各要素は辞書:
      {
        "usi": "7g7f",
        "japanese": "▲７六歩",
        "display": "7g7f (▲７六歩)"
      }
    """
    moves = []
    for move in board.legal_moves:
        usi = move.usi()
        ja = move_to_japanese(board, move)
        moves.append({
            "usi": usi,
            "japanese": ja,
            "display": f"{usi} ({ja})"
        })
    return moves


def calculate_jishogi_points(board: shogi.Board) -> Dict[str, Dict[str, int]]:
    """
    持将棋・入玉判定のための点数を計算します。
    - 大駒 (飛・竜・角・馬): 5点
    - 小駒 (金・銀・桂・香・歩・と・杏・圭・全): 1点
    - 玉: 0点

    返り値:
      {
        "black": {"total": 全駒点数, "camp": 敵陣内駒+持ち駒点数, "in_camp_pieces": 敵陣内駒数},
        "white": {"total": 全駒点数, "camp": 敵陣内駒+持ち駒点数, "in_camp_pieces": 敵陣内駒数}
      }
    """
    black_total = 0
    white_total = 0
    black_camp = 0
    white_camp = 0
    black_in_camp_pieces = 0
    white_in_camp_pieces = 0

    # 盤上の駒
    for sq in range(81):
        p = board.piece_at(sq)
        if p is None:
            continue
        pts = PIECE_POINTS.get(p.piece_type, 0)
        rank = (sq // 9) + 1
        if p.color == shogi.BLACK:
            black_total += pts
            if rank <= 3:
                black_camp += pts
                if p.piece_type != shogi.KING:
                    black_in_camp_pieces += 1
        else:
            white_total += pts
            if rank >= 7:
                white_camp += pts
                if p.piece_type != shogi.KING:
                    white_in_camp_pieces += 1

    # 持ち駒
    for pt, count in board.pieces_in_hand[shogi.BLACK].items():
        pts = PIECE_POINTS.get(pt, 0) * count
        black_total += pts
        black_camp += pts

    for pt, count in board.pieces_in_hand[shogi.WHITE].items():
        pts = PIECE_POINTS.get(pt, 0) * count
        white_total += pts
        white_camp += pts

    return {
        "black": {
            "total": black_total,
            "camp": black_camp,
            "in_camp_pieces": black_in_camp_pieces,
        },
        "white": {
            "total": white_total,
            "camp": white_camp,
            "in_camp_pieces": white_in_camp_pieces,
        }
    }


def is_perpetual_check_repetition(board: shogi.Board) -> Optional[int]:
    """
    千日手が発生している局面において、連続王手によるものかを判定します。
    連続王手を行っていたプレイヤーの color (shogi.BLACK or shogi.WHITE) を返し、
    そうでなければ None を返します。
    """
    if not board.is_fourfold_repetition():
        return None

    # 直近の連続王手サイクルを履歴から調査
    current_hash = board.zobrist_hash()
    matched_indices = []
    move_list = list(board.move_stack)
    
    # 局面履歴を一時的に巻き戻しながらハッシュ一致箇所を調査
    reconstructed_board = shogi.Board()
    hashes = [reconstructed_board.zobrist_hash()]
    for m in move_list:
        reconstructed_board.push(m)
        hashes.append(reconstructed_board.zobrist_hash())

    # 現在のハッシュと一致する過去のインデックスを収集
    for idx, h in enumerate(hashes):
        if h == current_hash:
            matched_indices.append(idx)

    if len(matched_indices) < 2:
        return None

    # 直前の同局面からの区間における王手状況を確認
    last_loop_start = matched_indices[-2]
    loop_moves = move_list[last_loop_start:]
    if not loop_moves:
        return None

    # 検証用盤面を再現
    test_board = shogi.Board()
    for m in move_list[:last_loop_start]:
        test_board.push(m)

    black_all_checks = True
    white_all_checks = True
    black_moves_count = 0
    white_moves_count = 0

    for m in loop_moves:
        turn = test_board.turn
        test_board.push(m)
        gives_check = test_board.is_check()

        if turn == shogi.BLACK:
            black_moves_count += 1
            if not gives_check:
                black_all_checks = False
        else:
            white_moves_count += 1
            if not gives_check:
                white_all_checks = False

    if black_all_checks and black_moves_count > 0:
        return shogi.BLACK
    if white_all_checks and white_moves_count > 0:
        return shogi.WHITE

    return None


def check_game_status(
    board: shogi.Board,
    max_moves: int = 256,
    jishogi_rule: str = "24_point"
) -> GameStatus:
    """
    盤面の終局状態（詰み、千日手、持将棋、最大手数判定など）を総合判定します。

    :param board: python-shogi の Board インスタンス
    :param max_moves: 引き分けとする最大手数 (デフォルト: 256)
    :param jishogi_rule: 持将棋判定ルール ("24_point" または "27_point")
    """
    current_turn = board.turn
    opponent_turn = 1 - current_turn
    current_turn_str = format_turn(current_turn)
    opponent_turn_str = format_turn(opponent_turn)

    # 1. 詰み判定
    if board.is_checkmate():
        return GameStatus(
            is_over=True,
            result=GameResult.CHECKMATE,
            winner=opponent_turn,
            winner_str=opponent_turn_str,
            reason=f"{current_turn_str}の玉が詰みました（{opponent_turn_str}の勝ち）"
        )

    # 2. ステイルメイト (合法手なし・王手ではない)
    if board.is_stalemate():
        return GameStatus(
            is_over=True,
            result=GameResult.STALEMATE,
            winner=opponent_turn,
            winner_str=opponent_turn_str,
            reason=f"{current_turn_str}に合法手がありません（{opponent_turn_str}の勝ち）"
        )

    # 3. 千日手および連続王手の千日手判定
    if board.is_fourfold_repetition():
        perpetual_player = is_perpetual_check_repetition(board)
        if perpetual_player is not None:
            winner = 1 - perpetual_player
            loser_str = format_turn(perpetual_player)
            winner_str = format_turn(winner)
            return GameStatus(
                is_over=True,
                result=GameResult.PERPETUAL_CHECK,
                winner=winner,
                winner_str=winner_str,
                reason=f"連続王手の千日手による反則負けです（{loser_str}の反則負け、{winner_str}の勝ち）"
            )
        else:
            return GameStatus(
                is_over=True,
                result=GameResult.FOURFOLD_REPETITION,
                winner=None,
                winner_str=None,
                reason="同一局面が4回現れたため、千日手により引き分けです"
            )

    # 4. 最大手数判定
    move_count = len(board.move_stack)
    if move_count >= max_moves:
        return GameStatus(
            is_over=True,
            result=GameResult.MAX_MOVES,
            winner=None,
            winner_str=None,
            reason=f"規定の最大手数（{max_moves}手）に到達したため、引き分けです"
        )

    # 5. 持将棋（相入玉）判定
    # 先手玉が1〜3段目、後手玉が7〜9段目に入玉しているか
    black_king_sq = board.king_squares[shogi.BLACK]
    white_king_sq = board.king_squares[shogi.WHITE]
    if black_king_sq is not None and white_king_sq is not None:
        black_entered = (black_king_sq // 9) + 1 <= 3
        white_entered = (white_king_sq // 9) + 1 >= 7

        if black_entered and white_entered:
            points = calculate_jishogi_points(board)
            b_pts = points["black"]["camp"]
            w_pts = points["white"]["camp"]

            if jishogi_rule == "24_point":
                if b_pts >= 24 and w_pts >= 24:
                    return GameStatus(
                        is_over=True,
                        result=GameResult.JISHOGI,
                        winner=None,
                        winner_str=None,
                        reason=f"相入玉により双方が24点以上（先手: {b_pts}点, 後手: {w_pts}点）に達したため、持将棋（引き分け）です"
                    )
            elif jishogi_rule == "27_point":
                if b_pts >= 28 and w_pts >= 28:
                    return GameStatus(
                        is_over=True,
                        result=GameResult.JISHOGI,
                        winner=None,
                        winner_str=None,
                        reason=f"相入玉により双方が28点以上（先手: {b_pts}点, 後手: {w_pts}点）に達したため、持将棋（引き分け）です"
                    )

    # 対局継続中
    return GameStatus(
        is_over=False,
        result=GameResult.IN_PROGRESS,
        winner=None,
        winner_str=None,
        reason=f"対局中（{current_turn_str}の手番）"
    )


def diagnose_illegal_move(board: shogi.Board, move: shogi.Move) -> str:
    """
    指定された指し手が合法手でない理由（反則内容）を診断して日本語で返します。
    """
    turn = board.turn
    turn_str = format_turn(turn)

    if move.from_square is None:
        # 持ち駒を打つ手
        piece_type = move.drop_piece_type
        pname = PIECE_NAMES.get(piece_type, "駒")

        # 1. 持ち駒を持っているか
        if board.pieces_in_hand[turn].get(piece_type, 0) <= 0:
            return f"{turn_str}の持ち駒に「{pname}」がありません"

        # 2. 既に駒が存在するマスへの駒打ち
        if board.piece_at(move.to_square) is not None:
            return f"指定されたマス（{square_to_japanese(move.to_square)}）には既に駒が存在します"

        # 3. 二歩の反則
        if piece_type == shogi.PAWN and bool(board.is_double_pawn(move.to_square, piece_type)):
            return "同一の筋に既に歩が存在するため、二歩の反則です"

        # 4. 行き所のない駒
        rank = (move.to_square // 9) + 1
        if turn == shogi.BLACK:
            if piece_type in (shogi.PAWN, shogi.LANCE) and rank == 1:
                return "1段目に歩・香を打つことはできません（行き所のない駒）"
            if piece_type == shogi.KNIGHT and rank <= 2:
                return "1・2段目に桂馬を打つことはできません（行き所のない駒）"
        else:
            if piece_type in (shogi.PAWN, shogi.LANCE) and rank == 9:
                return "9段目に歩・香を打つことはできません（行き所のない駒）"
            if piece_type == shogi.KNIGHT and rank >= 8:
                return "8・9段目に桂馬を打つことはできません（行き所のない駒）"

        # 5. 自殺手 / 打ち歩詰め
        if board.is_suicide_or_check_by_dropping_pawn(move):
            # 打ち歩詰めかどうかを判定
            board.push(move)
            was_drop_pawn_mate = board.was_check_by_dropping_pawn(move)
            was_suicide = board.was_suicide()
            board.pop()
            if was_drop_pawn_mate:
                return "打ち歩詰めの反則です"
            if was_suicide:
                return "王手放置または自玉を王手に晒す手（自殺手）です"

        return "不正な駒打ちです"

    else:
        # 盤上の駒の移動
        piece = board.piece_at(move.from_square)
        if piece is None:
            return f"移動元（{square_to_japanese(move.from_square)}）に駒が存在しません"

        if piece.color != turn:
            return f"相手の駒（{square_to_japanese(move.from_square)}の駒）を動かすことはできません"

        pname = PIECE_NAMES.get(piece.piece_type, "駒")
        dest_piece = board.piece_at(move.to_square)
        if dest_piece is not None and dest_piece.color == turn:
            return f"味方の駒が存在するマス（{square_to_japanese(move.to_square)}）には移動できません"

        # 成りに関する反則
        if move.promotion:
            if piece.piece_type not in PROMOTABLE_PIECES:
                return f"「{pname}」は成ることができない駒です"
            can_promote = (
                is_enemy_camp(move.from_square, turn) or
                is_enemy_camp(move.to_square, turn)
            )
            if not can_promote:
                return "敵陣に関係しない移動で成ることはできません"

        # 行き所のない駒
        if not move.promotion:
            rank = (move.to_square // 9) + 1
            if turn == shogi.BLACK:
                if piece.piece_type in (shogi.PAWN, shogi.LANCE) and rank == 1:
                    return "1段目の歩・香は成らなければなりません（行き所のない駒）"
                if piece.piece_type == shogi.KNIGHT and rank <= 2:
                    return "1・2段目の桂馬は成らなければなりません（行き所のない駒）"
            else:
                if piece.piece_type in (shogi.PAWN, shogi.LANCE) and rank == 9:
                    return "9段目の歩・香は成らなければなりません（行き所のない駒）"
                if piece.piece_type == shogi.KNIGHT and rank >= 8:
                    return "8・9段目の桂馬は成らなければなりません（行き所のない駒）"

        # 自殺手・王手放置
        if board.is_suicide_or_check_by_dropping_pawn(move):
            return "王手放置または自玉を王手に晒す手（自殺手）です"

        return f"「{pname}」の利きではないマスへの移動です"


def apply_move_to_board(board: shogi.Board, usi: str) -> shogi.Move:
    """
    USI文字列で指定された手を盤面に適用します。
    非合法手や反則手の場合は IllegalMoveError を送出します。

    :param board: python-shogi の Board インスタンス
    :param usi: USI形式の着手文字列 (例: '7g7f', '8h2b+', 'P*5e')
    :return: 適用された shogi.Move オブジェクト
    """
    try:
        move = shogi.Move.from_usi(usi)
    except Exception as e:
        raise IllegalMoveError(usi, f"USI文字列の解析に失敗しました: {e}")

    # 合法手判定
    if move not in board.legal_moves:
        reason = diagnose_illegal_move(board, move)
        raise IllegalMoveError(usi, reason)

    board.push(move)
    return move


# ---------------------------------------------------------------------------
# 将棋エンジンクラス
# ---------------------------------------------------------------------------

class ShogiEngine:
    """
    将棋の盤面管理、合法手生成、着手適用、終局判定を統括するエンジンクラスです。
    """

    def __init__(self, sfen: Optional[str] = None):
        """
        エンジンを初期化します。
        :param sfen: 初期SFEN文字列。Noneの場合は通常の平手初期局面となります。
        """
        self.board = shogi.Board(sfen) if sfen else shogi.Board()

    def reset(self, sfen: Optional[str] = None) -> None:
        """盤面をリセットします"""
        if sfen:
            self.board = shogi.Board(sfen)
        else:
            self.board.reset()

    # --- 状態取得プロパティ ---

    @property
    def sfen(self) -> str:
        """現在の局面のSFEN文字列を返します"""
        return self.board.sfen()

    @property
    def turn(self) -> int:
        """手番 (shogi.BLACK=0 または shogi.WHITE=1) を返します"""
        return self.board.turn

    @property
    def turn_name(self) -> str:
        """手番の日本語表記（「先手」または「後手」）を返します"""
        return format_turn(self.board.turn)

    @property
    def move_number(self) -> int:
        """現在の通算手数（1手目始まり）を返します"""
        return self.board.move_number

    @property
    def is_check(self) -> bool:
        """現在王手がかかっているかを返します"""
        return self.board.is_check()

    # --- 盤面・持ち駒のテキスト生成 ---

    def get_board_text(self, style: str = "detailed", show_labels: bool = True) -> str:
        """
        視覚的なテキスト盤面（9×9のマス目、▲/△/・表記）を生成します。
        :param style: "detailed" (成銀等2文字表記) または "compact" (全等1文字略称)
        :param show_labels: 筋・段のラベルや罫線を表示するか
        """
        return format_board_text(self.board, style=style, show_labels=show_labels)

    def get_pieces_in_hand_text(self) -> str:
        """
        持ち駒の日本語表記を返します。
        例:
          先手: 歩2 銀1
          後手: なし
        """
        return format_pieces_in_hand(self.board)

    def get_player_pieces_in_hand_text(self, color: int) -> str:
        """特定プレイヤー（先手または後手）の持ち駒表記を返します"""
        return format_pieces_in_hand_single(self.board, color)

    # --- 合法手一覧 ---

    def get_legal_moves(self) -> List[Dict[str, str]]:
        """
        現在の局面のすべての合法手を取得します。
        各要素: {"usi": "7g7f", "japanese": "▲７六歩", "display": "7g7f (▲７六歩)"}
        """
        return get_legal_moves(self.board)

    def get_legal_usi_list(self) -> List[str]:
        """合法手のUSI文字列リストを返します"""
        return [m.usi() for m in self.board.legal_moves]

    def move_to_japanese(self, move_or_usi: Union[shogi.Move, str]) -> str:
        """指定された指し手（MoveまたはUSI）の日本語表記を返します"""
        if isinstance(move_or_usi, str):
            move = shogi.Move.from_usi(move_or_usi)
        else:
            move = move_or_usi
        return move_to_japanese(self.board, move)

    # --- 指し手適用 ---

    def apply_move(self, usi: str) -> Dict[str, Any]:
        """
        指定された指し手 (USI) を適用します。
        非合法手や反則手の場合は IllegalMoveError を送出します。

        :param usi: USI着手文字列 (例: '7g7f')
        :return: 適用された手の情報 (usi, japanese, move_number, sfen)
        """
        ja = self.move_to_japanese(usi)
        applied_move = apply_move_to_board(self.board, usi)
        return {
            "usi": usi,
            "japanese": ja,
            "move_number": self.board.move_number,
            "sfen": self.board.sfen()
        }

    def undo_move(self) -> Optional[shogi.Move]:
        """1手巻き戻します。巻き戻した手を返します。履歴がない場合はNoneを返します"""
        if self.board.move_stack:
            return self.board.pop()
        return None

    # --- 終局判定 ---

    def get_game_status(self, max_moves: int = 256, jishogi_rule: str = "24_point") -> GameStatus:
        """
        現在の局面の終局状態を判定します。
        詰み、ステイルメイト、千日手、連続王手の千日手、持将棋、最大手数を判定します。
        """
        return check_game_status(self.board, max_moves=max_moves, jishogi_rule=jishogi_rule)

    def calculate_points(self) -> Dict[str, Dict[str, int]]:
        """入玉・持将棋計算用の点数を返します"""
        return calculate_jishogi_points(self.board)

    # --- 状態サマリー ---

    def get_state_summary(self, max_moves: int = 256) -> Dict[str, Any]:
        """
        現在のエンジンの全状態をまとめた辞書を返します。
        APIレスポンスやフロントエンドとのデータ通信に便利です。
        """
        status = self.get_game_status(max_moves=max_moves)
        legal_moves = self.get_legal_moves()
        return {
            "sfen": self.sfen,
            "turn": self.turn,
            "turn_name": self.turn_name,
            "move_number": self.move_number,
            "is_check": self.is_check,
            "pieces_in_hand": {
                "black": self.get_player_pieces_in_hand_text(shogi.BLACK),
                "white": self.get_player_pieces_in_hand_text(shogi.WHITE),
                "formatted": self.get_pieces_in_hand_text(),
            },
            "board_text": self.get_board_text(),
            "legal_moves_count": len(legal_moves),
            "legal_moves": legal_moves,
            "is_game_over": status.is_over,
            "game_result": status.result.value,
            "game_reason": status.reason,
            "winner": status.winner_str,
        }
