from __future__ import annotations

import argparse
import contextlib
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import uvicorn

from .app import create_app
from .config import ROOT, Config


def port_available(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def log_tail(path: Path, lines: int = 25) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(engine log is not readable yet)"
    return "\n".join(content[-lines:])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Whisper engine and caption bridge.")
    parser.add_argument("--backend", choices=["vulkan", "cuda", "cpu"])
    parser.add_argument("--threads", type=int)
    parser.add_argument("--engine-timeout", type=float, default=240.0,
                        help="Seconds to wait for the engine to load the model (default: 240).")
    args = parser.parse_args()
    config = Config.load()
    if args.backend:
        config.backend = args.backend
    if args.threads:
        config.whisper_threads = args.threads
    config.validate()
    executable = Path(config.engine_paths.get(config.backend, ""))
    if not executable.is_file():
        installed = ", ".join(sorted(config.engine_paths)) or "none"
        raise FileNotFoundError(
            f"No {config.backend.upper()} whisper-server is registered (installed backends: {installed}).\n"
            f"Run:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\Setup.ps1 "
            f"-Backend {config.backend.upper()} -Prebuilt\n"
            f"Then:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\Start.ps1"
        )
    if not Path(config.model_path).is_file():
        raise FileNotFoundError("Whisper model is missing. Run Setup.ps1 or supply -ModelPath.")
    if not all(port_available(p) for p in (config.bridge_port, config.engine_port)):
        raise RuntimeError("A configured local port is already in use. Close the previous runner or change data/config.json.")

    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    logfile = logs / f"whisper-{config.backend}.log"
    empty_public = ROOT / "data" / "empty-public"
    empty_public.mkdir(parents=True, exist_ok=True)
    command = [str(executable), "-m", config.model_path, "-l", "ja", "-t", str(config.whisper_threads),
               "--host", "127.0.0.1", "--port", str(config.engine_port),
               "--request-path", f"/engine-{config.engine_secret}",
               "--public", str(empty_public), "-bo", "1", "-bs", "1", "-nf", "-sns"]
    if config.backend == "cpu":
        command.append("-ng")
    env = os.environ.copy()
    env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
    print("\nLOCAL DUAL CAPTIONS  |  Japanese + English\n", flush=True)
    print(f"Requested Whisper backend: {config.backend.upper()}", flush=True)
    print("Translation: CPU / offline OPUS-MT JA→EN weights", flush=True)
    print(f"Engine log: {logfile}", flush=True)
    print("Loading model. First startup can take a while…", flush=True)
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    engine = None
    try:
        with logfile.open("w", encoding="utf-8") as output:
            engine = subprocess.Popen(command, cwd=str(ROOT), env=env, stdout=output, stderr=subprocess.STDOUT,
                                      creationflags=creationflags)
            with httpx.Client(timeout=2, trust_env=False) as client:
                deadline = time.monotonic() + max(10.0, args.engine_timeout)
                while time.monotonic() < deadline:
                    if engine.poll() is not None:
                        raise RuntimeError(
                            f"Whisper exited with code {engine.returncode}.\n"
                            f"----- last lines of {logfile} -----\n{log_tail(logfile)}\n----- end -----\n"
                            "Typical causes: a DLL missing from the folder that holds whisper-server.exe, "
                            "an unsupported flag, a GPU driver problem, or not enough free memory."
                        )
                    try:
                        response = client.get(config.engine_url + "/health")
                        if response.status_code == 200 and response.json().get("status") == "ok":
                            break
                    except (httpx.HTTPError, ValueError):
                        pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError(
                        f"Whisper did not become ready within {int(max(10.0, args.engine_timeout))} seconds.\n"
                        f"----- last lines of {logfile} -----\n{log_tail(logfile)}\n----- end -----\n"
                        "Big models load slowly the first time. Retry with --engine-timeout 600."
                    )
            print(f"Engine    : {executable}", flush=True)
            print(f"Model     : {config.model_path}", flush=True)
            if config.backend != "cpu":
                print(f"Check {logfile} to confirm your GPU was really selected; "
                      "a failed GPU init falls back to CPU silently.", flush=True)
            print(f"\nPairing key (keep private): {config.token}", flush=True)
            print("Paste this key into the extension once. It is also in data/pairing-key.txt.", flush=True)
            print(f"Bridge: http://127.0.0.1:{config.bridge_port}", flush=True)
            print("Keep this terminal open. Press Ctrl+C to stop both processes.\n", flush=True)
            # This is software to run on the USER'S Windows PC. Loopback binding
            # is intentional; it must not be exposed through a public preview.
            uvicorn.run(create_app(config), host="127.0.0.1", port=config.bridge_port,
                        ws_max_size=64000, ws_max_queue=16, access_log=False, log_level="info")
    except KeyboardInterrupt:
        return 0
    finally:
        if engine is not None and engine.poll() is None:
            if os.name == "nt":
                with contextlib.suppress(OSError):
                    engine.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                engine.terminate()
            try:
                engine.wait(timeout=5)
            except subprocess.TimeoutExpired:
                engine.kill()
                engine.wait(timeout=3)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"\nSetup/start error: {exc}", file=sys.stderr)
        sys.exit(1)
