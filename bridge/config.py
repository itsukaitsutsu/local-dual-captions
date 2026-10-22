from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "data" / "config.json"


@dataclass
class Config:
    token: str = ""
    engine_secret: str = ""
    backend: str = "vulkan"
    model_path: str = ""
    translation_path: str = ""
    bridge_port: int = 8765
    engine_port: int = 8178
    whisper_threads: int = 4
    translation_threads: int = 4
    engine_paths: dict[str, str] = field(default_factory=dict)
    allowed_extension_ids: list[str] = field(default_factory=list)

    @property
    def engine_url(self) -> str:
        return f"http://127.0.0.1:{self.engine_port}/engine-{self.engine_secret}"

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> Config:
        if not path.exists():
            raise FileNotFoundError("Run scripts/Setup.ps1 first; data/config.json is missing.")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        result = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        result.validate()
        return result

    def validate(self) -> None:
        if len(self.token) < 32 or len(self.engine_secret) < 32:
            raise ValueError("Pairing and internal engine keys must be at least 32 characters.")
        if self.backend not in {"vulkan", "cuda", "cpu"}:
            raise ValueError("Backend must be vulkan, cuda, or cpu.")
        if not all(1024 <= p <= 65535 for p in (self.bridge_port, self.engine_port)):
            raise ValueError("Ports must be between 1024 and 65535.")
        if self.bridge_port == self.engine_port:
            raise ValueError("The bridge and engine need different ports.")
        if not 1 <= self.translation_threads <= 32 or not 1 <= self.whisper_threads <= 128:
            raise ValueError("Invalid thread count.")

    def save(self, path: Path = CONFIG_PATH) -> None:
        self.validate()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, indent=2) + "\n", encoding="utf-8")
        (path.parent / "pairing-key.txt").write_text(self.token + "\n", encoding="utf-8")

    @classmethod
    def fresh(cls) -> Config:
        return cls(token=secrets.token_urlsafe(32), engine_secret=secrets.token_urlsafe(32))
