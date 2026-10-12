import os
from typing import Optional
from dotenv import load_dotenv

# .env ファイルをロード
load_dotenv()

class Config:
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # Gemini
    # 注意: 'gemini-3.8-flash-high' は存在しない。正しくは 'gemini-3.8-flash'
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    # TypeSafe AI JEV
    # jv_live_ プレフィックスのキーは jevtypesafeai.com/api/v1/decide エンドポイントで使用
    # 公式 api.typesafe.ai アカウントのキーは https://api.typesafe.ai/v1/systemone で使用
    JEV_API_KEY: str = os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY", "")
    JEV_MODEL: str = os.getenv("JEV_MODEL", "jev-latest")
    JEV_ENDPOINT: str = os.getenv("JEV_ENDPOINT", "https://jevtypesafeai.com/api/v1/decide")

    # アプリケーション設定
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "shogi_matches.db")
    MAX_MOVES: int = int(os.getenv("MAX_MOVES", "256"))
    MOVE_TIMEOUT_SECONDS: int = int(os.getenv("MOVE_TIMEOUT_SECONDS", "60"))

config = Config()
