"""Runtime configuration. Secrets never appear in API responses."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: ROOT / "data")
    mesh_api_key: str = ""
    mesh_base_url: str = "https://api.meshapi.ai/v1"
    chat_model: str = "openai/gpt-4o-mini"
    image_model: str = "openai/gpt-image-1-mini"
    demo_mode: bool = False
    seed_demo: bool = True
    max_revisions: int = 2
    mesh_timeout: float = 90.0
    worker_enabled: bool = True

    def __post_init__(self):
        self.data_dir = Path(self.data_dir).resolve()
        if self.mesh_base_url.rstrip("/") != "https://api.meshapi.ai/v1":
            raise ValueError("All AI requests must use https://api.meshapi.ai/v1.")


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env", override=False)
    return Settings(
        data_dir=Path(os.getenv("CREATOROS_DATA_DIR", str(ROOT / "data"))),
        mesh_api_key=os.getenv("MESH_API_KEY", ""),
        mesh_base_url=os.getenv("MESH_BASE_URL", "https://api.meshapi.ai/v1"),
        chat_model=os.getenv("MESH_CHAT_MODEL", "openai/gpt-4o-mini"),
        image_model=os.getenv("MESH_IMAGE_MODEL", "openai/gpt-image-1-mini"),
        seed_demo=os.getenv("CREATOROS_SEED_DEMO", "true").lower() == "true",
    )
