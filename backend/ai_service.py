"""AI 対局サービスモジュール (ai_service.py)

各AIモデル (GPT-Luna-high, Gemini3.8flash-high, ClaudeSonnet5, JEV) との
実際のAPI通信および指し手決定ロジックを提供します。
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx

from .config import config

logger = logging.getLogger("ai_service")
logging.basicConfig(level=logging.INFO)

# モデル選択肢の識別子
PLAYER_GPT = "GPT-Luna-high"
PLAYER_GEMINI = "Gemini3.8flash-high"
PLAYER_CLAUDE = "ClaudeSonnet5"
PLAYER_JEV = "JEV"

SUPPORTED_PLAYERS = [
    PLAYER_GPT,
    PLAYER_GEMINI,
    PLAYER_CLAUDE,
    PLAYER_JEV,
]

def build_shogi_context(
    turn_name: str,
    move_number: int,
    board_text: str,
    sfen: str,
    pieces_in_hand_text: str,
    history_moves: List[Dict[str, Any]],
    legal_moves: List[Dict[str, str]]
) -> Tuple[str, Dict[str, str], str]:
    """
    LLM および JEV に渡す共通の局面情報（同等の情報）を構築します。

    :return: (state_text, criteria_dict, legal_moves_text)
    """
    # 棋譜履歴の整形
    if not history_moves:
        history_text = "開始局面（まだ指し手はありません）"
    else:
        history_lines = []
        # 直近20手を特に見やすく表示
        recent_moves = history_moves[-20:] if len(history_moves) > 20 else history_moves
        if len(history_moves) > 20:
            history_lines.append(f"... (以前の {len(history_moves) - 20} 手省略)")
        for m in recent_moves:
            m_num = m.get("move_number", 0)
            kif = m.get("kif_text", "")
            usi = m.get("usi", "")
            player = "先手" if m.get("player") == "sente" else "後手"
            history_lines.append(f"{m_num}手目: {player} {kif} ({usi})")
        history_text = "\n".join(history_lines)

    # 共通の盤面状況テキスト (state)
    state_text = f"""【対局情報】
手番: あなたの手番 ({turn_name})
手数: {move_number}手目
SFEN: {sfen}

【現在の盤面】
{board_text}

【持ち駒】
{pieces_in_hand_text}

【これまでの棋譜履歴】
{history_text}"""

    # JEV用の criteria 辞書 (USI -> 日本語説明)
    criteria_dict = {}
    legal_lines = []
    for m in legal_moves:
        usi = m["usi"]
        ja = m.get("japanese", usi)
        display = m.get("display", f"{usi} ({ja})")
        criteria_dict[usi] = display
        legal_lines.append(f"- {usi}: {ja}")

    legal_moves_text = "\n".join(legal_lines)
    return state_text, criteria_dict, legal_moves_text


class AIService:
    def __init__(self):
        self.timeout = config.MOVE_TIMEOUT_SECONDS

    async def get_next_move(
        self,
        player_name: str,
        turn_name: str,
        move_number: int,
        board_text: str,
        sfen: str,
        pieces_in_hand_text: str,
        history_moves: List[Dict[str, Any]],
        legal_moves: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        指定されたプレイヤー (GPT-Luna-high, Gemini3.8flash-high, ClaudeSonnet5, JEV)
        のAPIを呼び出して次の指し手を決定します。
        """
        start_time = time.time()
        legal_usi_set = {m["usi"] for m in legal_moves}

        if not legal_moves:
            return {
                "usi": None,
                "error": "指せる合法手がありません（詰みまたは投了）",
                "time_spent_ms": 0,
                "raw_response": None
            }

        state_text, criteria_dict, legal_moves_text = build_shogi_context(
            turn_name=turn_name,
            move_number=move_number,
            board_text=board_text,
            sfen=sfen,
            pieces_in_hand_text=pieces_in_hand_text,
            history_moves=history_moves,
            legal_moves=legal_moves
        )

        result_usi = None
        raw_response = None
        error_msg = None
        http_status = None
        reason = ""

        try:
            if player_name == PLAYER_JEV:
                result_usi, reason, raw_response = await self._call_jev(state_text, criteria_dict, legal_moves)
            elif player_name == PLAYER_GPT:
                result_usi, reason, raw_response = await self._call_openai(state_text, legal_moves_text, legal_moves)
            elif player_name == PLAYER_GEMINI:
                result_usi, reason, raw_response = await self._call_gemini(state_text, legal_moves_text, legal_moves)
            elif player_name == PLAYER_CLAUDE:
                result_usi, reason, raw_response = await self._call_claude(state_text, legal_moves_text, legal_moves)
            else:
                raise ValueError(f"未対応のプレイヤーです: {player_name}")

        except Exception as e:
            if isinstance(e, httpx.HTTPStatusError):
                http_status = e.response.status_code
                error_detail = e.response.text[:1000]
                logger.error(
                    f"API呼び出し失敗 ({player_name}): HTTP {http_status}: "
                    f"{error_detail}"
                )
            else:
                logger.error(f"API呼び出し失敗 ({player_name}): {e}", exc_info=True)
            error_msg = str(e)

        time_spent_ms = int((time.time() - start_time) * 1000)

        # 合法手チェック
        if result_usi not in legal_usi_set:
            logger.warning(f"{player_name} returned non-legal move: {result_usi}. Fallback to first legal move.")
            fallback_usi = legal_moves[0]["usi"]
            return {
                "usi": fallback_usi,
                "is_legal": False,
                "original_usi": result_usi,
                "reason": reason or f"APIエラーまたは非合法手のためフォールバック ({error_msg or '選択不能'})",
                "time_spent_ms": time_spent_ms,
                "raw_response": raw_response,
                "error": error_msg,
                "http_status": http_status
            }

        return {
            "usi": result_usi,
            "is_legal": True,
            "reason": reason,
            "time_spent_ms": time_spent_ms,
            "raw_response": raw_response,
            "error": None,
            "http_status": None
        }

    # -------------------------------------------------------------------------
    # JEV (TypeSafe AI) 呼び出し
    # -------------------------------------------------------------------------
    async def _call_jev(
        self,
        state_text: str,
        criteria_dict: Dict[str, str],
        legal_moves: List[Dict[str, str]]
    ) -> Tuple[str, str, Any]:
        """
        TypeSafe AI JEV API (https://api.typesafe.ai/v1/systemone) 呼び出し
        JEVの仕様に従い、state と choice 型の criteria を送信します。
        """
        api_key = config.JEV_API_KEY
        endpoint = config.JEV_ENDPOINT
        # jevtypesafeai.com の場合: /api/v1/decide が正しいパス
        # api.typesafe.ai の場合: /v1/systemone が正しいパス（公式アカウント時）
        # JEV_ENDPOINT に適切なURLが設定されている前提

        if not api_key:
            raise ValueError("JEV_API_KEY (または TYPESAFE_API_KEY) が環境変数に設定されていません。")

        # jevtypesafeai.com の /api/v1/decide は 'model' フィールドが不要
        # api.typesafe.ai の /v1/systemone は 'model' フィールドが必要
        is_typesafe_official = "api.typesafe.ai" in endpoint
        payload: dict = {
            "state": state_text,
            "questions": {
                "next_move": {
                    "type": "choice",
                    "instructions": "あなたは将棋の対局を行うAIプレイヤーです。現在の局面において最善と思われる合法手を1つ選択してください。",
                    "criteria": criteria_dict
                }
            }
        }
        if is_typesafe_official:
            payload["model"] = config.JEV_MODEL

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        answers = data.get("answers", {})
        next_move_ans = answers.get("next_move", {})
        choice = next_move_ans.get("choice")

        if not choice:
            raise ValueError(f"JEV APIのレスポンスに choice が見つかりませんでした: {data}")

        confidence = next_move_ans.get("confidence", 0.0)
        probs = next_move_ans.get("probabilities", {})
        reason = f"JEV choice: {choice} (confidence: {confidence:.2f})"
        if probs:
            top3 = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]
            reason += f" | top3: {', '.join(f'{k}={v:.2f}' for k,v in top3)}"
        return str(choice), reason, data

    # -------------------------------------------------------------------------
    # OpenAI (GPT-Luna-high) 呼び出し
    # -------------------------------------------------------------------------
    async def _call_openai(
        self,
        state_text: str,
        legal_moves_text: str,
        legal_moves: List[Dict[str, str]]
    ) -> Tuple[str, str, Any]:
        """OpenAI Chat Completions API 呼び出し"""
        api_key = config.OPENAI_API_KEY
        if not api_key:
            raise ValueError("OPENAI_API_KEY が環境変数に設定されていません。")

        model = config.OPENAI_MODEL
        url = f"{config.OPENAI_BASE_URL.rstrip('/')}/chat/completions"

        system_prompt = (
            "あなたはプロ棋士レベルの将棋AIです。\n"
            "現在の局面状況と【合法手リスト】が与えられます。\n"
            "必ず【合法手リスト】に記載されているUSI文字列の中から最善手を1手選び、\n"
            '以下のJSON形式のみで回答してください:\n'
            '{"move": "<選んだUSI文字列>", "reason": "<選んだ理由>"}'
        )

        user_content = (
            f"{state_text}\n\n"
            f"【合法手リスト】\n{legal_moves_text}\n\n"
            "上記の合法手の中から最善の1手を選び、JSONで回答してください。"
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "developer", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "response_format": {"type": "json_object"}
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        chosen_usi = parsed.get("move", "").strip()
        reason = parsed.get("reason", "")
        return chosen_usi, reason, data

    # -------------------------------------------------------------------------
    # Gemini (Gemini3.8flash-high) 呼び出し
    # -------------------------------------------------------------------------
    async def _call_gemini(
        self,
        state_text: str,
        legal_moves_text: str,
        legal_moves: List[Dict[str, str]]
    ) -> Tuple[str, str, Any]:
        """Google Gemini API 呼び出し"""
        api_key = config.GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY が環境変数に設定されていません。")

        model = config.GEMINI_MODEL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        prompt = (
            "あなたはプロ棋士レベルの将棋AIです。\n"
            "以下の局面情報と【合法手リスト】に基づき、最善の合法手を1つ選択してください。\n"
            "必ず【合法手リスト】に記載されたUSI文字列から選び、JSON形式のみで回答してください。\n\n"
            f"{state_text}\n\n"
            f"【合法手リスト】\n{legal_moves_text}\n\n"
            '形式: {"move": "<選んだUSI文字列>", "reason": "<選んだ理由>"}'
        )

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2
            }
        }

        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        text_out = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text_out)
        chosen_usi = parsed.get("move", "").strip()
        reason = parsed.get("reason", "")
        return chosen_usi, reason, data

    # -------------------------------------------------------------------------
    # Claude (ClaudeSonnet5) 呼び出し
    # -------------------------------------------------------------------------
    async def _call_claude(
        self,
        state_text: str,
        legal_moves_text: str,
        legal_moves: List[Dict[str, str]]
    ) -> Tuple[str, str, Any]:
        """Anthropic Claude API 呼び出し"""
        api_key = config.ANTHROPIC_API_KEY
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY が環境変数に設定されていません。")

        model = config.ANTHROPIC_MODEL
        url = "https://api.anthropic.com/v1/messages"

        system_prompt = (
            "あなたはプロ棋士レベルの将棋AIです。\n"
            "現在の局面状況と【合法手リスト】が与えられます。\n"
            "必ず【合法手リスト】に記載されているUSI文字列の中から最善手を1手選び、\n"
            '余計な解説を挟まず以下のJSONフォーマットのみを出力してください:\n'
            '{"move": "<選んだUSI文字列>", "reason": "<選んだ理由>"}'
        )

        user_content = (
            f"{state_text}\n\n"
            f"【合法手リスト】\n{legal_moves_text}\n\n"
            "上記の合法手の中から最善の1手を選び、JSONで回答してください。"
        )

        payload = {
            "model": model,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_content}
            ]
        }

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data["content"][0]["text"]
        # JSON部分を抽出
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
        else:
            parsed = json.loads(content)

        chosen_usi = parsed.get("move", "").strip()
        reason = parsed.get("reason", "")
        return chosen_usi, reason, data

ai_service = AIService()
