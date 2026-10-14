"""Isolated execution of KiCad tools.

Two runners share one interface:

* :class:`LocalRunner` executes ``kicad-cli`` / KiCad's Python as subprocesses
  of the worker (the worker container is the isolation boundary in Docker
  Compose).
* :class:`DockerRunner` starts a fresh, network-less KiCad container for every
  command, mounting only the job's working directory.

Commands are always argument vectors assembled by backend code from fixed
templates - never shell strings, and never text produced by the AI. All file
arguments are paths *relative to the job working directory* so the same
command works for both runners.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.core.config import Settings

SCRIPTS_DIR = Path(__file__).parent / "scripts"
ALLOWED_SCRIPTS = {"build_pcb.py", "drc_pcbnew.py", "probe.py"}

Tool = Literal["cli", "python"]


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def log(self) -> str:
        status = "TIMEOUT" if self.timed_out else f"exit {self.returncode}"
        parts = [f"$ {' '.join(self.argv)}  [{status}, {self.duration_s:.1f}s]"]
        if self.stdout.strip():
            parts.append(self.stdout.strip()[-4000:])
        if self.stderr.strip():
            parts.append("stderr: " + self.stderr.strip()[-4000:])
        return "\n".join(parts)


class EdaRunner(ABC):
    mode: str

    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    def run(self, tool: Tool, args: list[str], workdir: Path, timeout: int | None = None) -> CommandResult: ...

    @abstractmethod
    def engine_footprint_dir(self) -> str:
        """Footprint library directory as seen by the EDA engine."""

    @abstractmethod
    def describe(self) -> dict: ...

    def _exec(self, argv: list[str], cwd: Path, timeout: int, env: dict | None = None) -> CommandResult:
        start = time.monotonic()
        try:
            proc = subprocess.run(
                argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env, check=False
            )
            return CommandResult(argv, proc.returncode, proc.stdout, proc.stderr, time.monotonic() - start)
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            err = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
            return CommandResult(argv, -1, out, err, time.monotonic() - start, timed_out=True)
        except FileNotFoundError as e:
            return CommandResult(argv, 127, "", str(e), time.monotonic() - start)


def _check_script(args: list[str]) -> None:
    if not args or args[0] not in ALLOWED_SCRIPTS:
        raise ValueError(f"script {args[:1]} is not an allowed EDA script")


class LocalRunner(EdaRunner):
    mode = "local"

    def run(self, tool: Tool, args: list[str], workdir: Path, timeout: int | None = None) -> CommandResult:
        timeout = timeout or self.settings.eda_command_timeout_seconds
        home = workdir / ".kicad-home"
        home.mkdir(parents=True, exist_ok=True)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        # Headless KiCad has no first-run configuration, so define the standard
        # library path variables explicitly (they point at the official libraries).
        for major in range(6, 11):
            env[f"KICAD{major}_FOOTPRINT_DIR"] = str(self.settings.footprint_dir())
            env[f"KICAD{major}_SYMBOL_DIR"] = str(self.settings.symbol_dir())
        if tool == "cli":
            argv = [self.settings.kicad_cli, *args]
        else:
            _check_script(args)
            argv = [self.settings.kicad_python, "-I", str(SCRIPTS_DIR / args[0]), *args[1:]]
        return self._exec(argv, workdir, timeout, env)

    def engine_footprint_dir(self) -> str:
        return str(self.settings.footprint_dir())

    def describe(self) -> dict:
        return {
            "mode": self.mode,
            "kicad_cli": shutil.which(self.settings.kicad_cli) or self.settings.kicad_cli,
            "kicad_python": shutil.which(self.settings.kicad_python) or self.settings.kicad_python,
        }


class DockerRunner(EdaRunner):
    mode = "docker"
    CONTAINER_SCRIPTS = "/opt/pcbai-scripts"
    CONTAINER_FOOTPRINTS = "/usr/share/kicad/footprints"

    def run(self, tool: Tool, args: list[str], workdir: Path, timeout: int | None = None) -> CommandResult:
        timeout = timeout or self.settings.eda_command_timeout_seconds
        workdir = workdir.resolve()
        base = [
            "docker", "run", "--rm", "--network", "none",
            "--memory", "2g", "--cpus", "2", "--pids-limit", "256",
            "--security-opt", "no-new-privileges",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "-e", "HOME=/tmp", "-e", "LANG=C.UTF-8",
            "-v", f"{workdir}:/work", "-w", "/work",
            "-v", f"{SCRIPTS_DIR.resolve()}:{self.CONTAINER_SCRIPTS}:ro",
            "--entrypoint", "",
            self.settings.kicad_docker_image,
        ]
        if tool == "cli":
            argv = [*base, "kicad-cli", *args]
        else:
            _check_script(args)
            argv = [*base, "python3", "-I", f"{self.CONTAINER_SCRIPTS}/{args[0]}", *args[1:]]
        return self._exec(argv, workdir, timeout + 30)

    def engine_footprint_dir(self) -> str:
        return self.CONTAINER_FOOTPRINTS

    def describe(self) -> dict:
        return {"mode": self.mode, "image": self.settings.kicad_docker_image}


def make_runner(settings: Settings) -> EdaRunner:
    return DockerRunner(settings) if settings.kicad_exec_mode == "docker" else LocalRunner(settings)
