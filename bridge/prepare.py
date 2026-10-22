from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import ROOT, Config

# SHA-256 LFS hashes from the official whisper.cpp model repository.
MODELS = {
    "large-v3-turbo": (1624555275, "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"),
    "large-v3-turbo-q8_0": (874188075, "317eb69c11673c9de1e1f0d459b253999804ec71ac4c23c17ecf5fbe24e259a1"),
    "large-v3-turbo-q5_0": (574041195, "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2"),
}
TRANSLATION_MANIFEST = Path(__file__).with_name("translation-manifest.json")

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, path: Path, checksum: str, expected_size: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and (not expected_size or path.stat().st_size == expected_size):
        print(f"Verifying {path.name}…", flush=True)
        if sha256(path) == checksum:
            return path
        raise RuntimeError(f"Checksum mismatch for {path}. Rename/delete it before retrying.")
    part = path.with_name(path.name + ".part")
    for attempt in range(3):
        offset = part.stat().st_size if part.exists() else 0
        if expected_size and offset == expected_size:
            if sha256(part) == checksum:
                os.replace(part, path)
                return path
            raise RuntimeError(f"Checksum mismatch for {part}; remove this partial file and retry.")
        headers = {"User-Agent": "LocalDualCaptions/0.1 (offline model setup)"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=90) as response:
                if response.status == 206:
                    if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                        raise RuntimeError("Download server returned an unexpected byte range.")
                    mode = "ab"
                else:
                    offset, mode = 0, "wb"
                length = int(response.headers.get("Content-Length", 0))
                total = expected_size or offset + length
                next_report = offset
                with part.open(mode) as target:
                    while block := response.read(1024 * 1024):
                        target.write(block)
                        offset += len(block)
                        if offset >= next_report:
                            percent = f" ({offset / total:.0%})" if total else ""
                            print(f"  {path.name}: {offset / 1048576:.0f} MiB{percent}", flush=True)
                            next_report = offset + 32 * 1024 * 1024
            if expected_size and part.stat().st_size != expected_size:
                raise OSError("Download was incomplete")
            if sha256(part) != checksum:
                raise RuntimeError(f"Checksum mismatch for {part}; remove it and retry. Nothing was installed.")
            os.replace(part, path)
            return path
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == 2:
                raise RuntimeError(f"Download interrupted. Partial file retained at {part}. Run setup again to resume.") from exc
            print("Download interrupted; retrying from the last saved byte…", flush=True)
            time.sleep(2 ** attempt)
    raise RuntimeError("Download failed")


def install_translation(destination: Path) -> Path:
    manifest = json.loads(TRANSLATION_MANIFEST.read_text(encoding="utf-8"))
    base = f"https://huggingface.co/{manifest['repository']}/resolve/{manifest['revision']}"
    for name, metadata in manifest["files"].items():
        download(f"{base}/{name}", destination / name, metadata["sha256"], metadata["size"])
    (destination / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Download/verify local models and generate pairing keys.")
    parser.add_argument("--backend", choices=["vulkan", "cuda", "cpu"], required=True)
    parser.add_argument("--server-path", type=Path, required=True)
    parser.add_argument("--model", choices=list(MODELS), default="large-v3-turbo")
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--translation-path", type=Path)
    args = parser.parse_args()
    if not args.server_path.is_file():
        raise FileNotFoundError(f"whisper-server executable not found: {args.server_path}")
    config = Config.load() if (ROOT / "data" / "config.json").exists() else Config.fresh()
    model_dir = ROOT / "models"
    if args.model_path:
        model = args.model_path.resolve()
        if not model.is_file():
            raise FileNotFoundError(model)
        print(f"Using your existing model (not downloaded or modified): {model}", flush=True)
    else:
        size, digest = MODELS[args.model]
        filename = f"ggml-{args.model}.bin"
        model = download(f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{filename}",
                         model_dir / filename, digest, size)
    translation = args.translation_path.resolve() if args.translation_path else model_dir / "ja-en"
    if not args.translation_path:
        print("Downloading/verifying pinned OPUS-MT Japanese → English weights…", flush=True)
        install_translation(translation)
    from .engines import JapaneseTranslator
    print("Testing local translation…", flush=True)
    translator = JapaneseTranslator(translation, config.translation_threads)
    if not translator.translate("こんにちは。"):
        raise RuntimeError("The translation model produced no output")
    config.backend = args.backend
    config.engine_paths[args.backend] = str(args.server_path.resolve())
    config.model_path = str(model.resolve())
    config.translation_path = str(translation.resolve())
    config.save()
    print(f"\nSetup complete. Backend: {config.backend.upper()}", flush=True)
    print(f"Pairing key (private): {config.token}", flush=True)
    print("Run Start.cmd, then load the extension/ folder at chrome://extensions.\n", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nSetup error: {exc}", file=sys.stderr)
        sys.exit(1)
