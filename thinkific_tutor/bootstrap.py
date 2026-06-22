from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _candidate_paths() -> list[Path]:
    root = repo_root()
    candidates: list[Path] = []
    configured = os.getenv("AI_TUTOR_APP_PATH", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            root / "vendor" / "ai-tutor-app",
            root.parent / "ai-tutor-app",
            root.parent.parent / "GitHub" / "ai-tutor-app",
            Path("/opt/ai-tutor-app"),
        ]
    )
    return candidates


def find_ai_tutor_app_path() -> Path:
    for candidate in _candidate_paths():
        if (candidate / "app" / "chat_service.py").is_file():
            return candidate.resolve()
    searched = "\n".join(f"- {path}" for path in _candidate_paths())
    raise RuntimeError(
        "Could not find ai-tutor-app. Set AI_TUTOR_APP_PATH to the existing "
        f"repo path.\nSearched:\n{searched}"
    )


def load_environment(ai_tutor_path: Path) -> None:
    """Load local env first, then fill missing values from ai-tutor-app.

    This keeps deploy-time environment variables strongest, lets this adapter
    have its own .env, and still supports reusing the existing tutor app's .env
    without copying secrets into the new repo.
    """

    load_dotenv(repo_root() / ".env", override=False)
    load_dotenv(ai_tutor_path / ".env", override=False)


def ensure_ai_tutor_importable() -> Path:
    ai_tutor_path = find_ai_tutor_app_path()
    load_environment(ai_tutor_path)
    path_text = str(ai_tutor_path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)
    os.environ.setdefault(
        "AI_TUTOR_KB_AGENTS_PATH",
        str(ai_tutor_path / "data" / "scraping_scripts" / "kb_agents_template.md"),
    )
    return ai_tutor_path
