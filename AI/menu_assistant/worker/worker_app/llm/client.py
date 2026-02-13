from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types


@dataclass
class GeminiClientConfig:
    model: str = "gemini-2.5-flash"
    api_key_env: str = "GEMINI_API_KEY"
    temperature: float = 0.2
    top_p: float = 0.95
    top_k: int = 20
    response_mime_type: str = "application/json"


def _find_dotenv(start: Path, max_up: int = 8) -> Optional[Path]:
    """
    Search upward from `start` for a `.env` file.
    This makes the client robust to different working directories.
    """
    cur = start
    for _ in range(max_up + 1):
        candidate = cur / ".env"
        if candidate.exists() and candidate.is_file():
            return candidate
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


class Gemini25FlashClient:
    """
    Gemini 2.5 Flash client.
    - Robust .env loading (search upward from this file's directory)
    - Reads GEMINI_API_KEY from .env / environment
    - Calls google-genai SDK with response_mime_type=application/json
    """

    def __init__(
        self,
        config: Optional[GeminiClientConfig] = None,
        dotenv_path: Optional[str] = None,
        max_dotenv_up: int = 8,
    ) -> None:
        self.config = config or GeminiClientConfig()

        # 1) Load .env robustly
        # If dotenv_path is explicitly given, use it.
        # Otherwise, search upward from the directory containing this client.py.
        if dotenv_path:
            dp = Path(dotenv_path)
            if not dp.exists():
                raise FileNotFoundError(f"dotenv_path not found: {dp}")
            load_dotenv(dotenv_path=str(dp), override=False)
        else:
            here = Path(__file__).resolve().parent
            found = _find_dotenv(here, max_up=max_dotenv_up)
            if found:
                load_dotenv(dotenv_path=str(found), override=False)
            else:
                # fallback: try default behavior (current working dir)
                load_dotenv(override=False)

        # 2) Read API key
        api_key = os.getenv(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{self.config.api_key_env} is not set. "
                "Create a .env file at your project root with:\n"
                "  GEMINI_API_KEY=YOUR_KEY\n"
                "or export it as an environment variable."
            )

        # 3) Initialize GenAI client
        self.client = genai.Client(api_key=api_key)

    def generate_json(self, *, system: str, user: str) -> str:
        """
        Returns raw text (expected JSON).
        parsers.py handles extraction/validation/retry.
        """
        cfg = types.GenerateContentConfig(
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            top_k=self.config.top_k,
            response_mime_type=self.config.response_mime_type,
            system_instruction=system,
        )

        resp = self.client.models.generate_content(
            model=self.config.model,
            contents=user,
            config=cfg,
        )
        return (resp.text or "").strip()

