"""
Sandboxed gate execution via Docker.

Problem solved
──────────────
Generated code runs in a temp directory with full host access by default.
A malicious or buggy generated test could read environment variables,
hit external APIs, write outside its temp directory, or exhaust resources.

Solution
────────
SandboxedGate wraps any BaseGate and runs its command inside a Docker
container with:
  - Network isolation    (--network none)
  - Read-only filesystem (--read-only + --tmpfs /tmp)
  - No host env vars     (secrets cannot be exfiltrated)
  - Memory + CPU caps    (runaway tests are bounded)
  - Non-root user        (images run as uid 1000)
  - Only the temp dir mounted (nothing else visible)

Graceful degradation
────────────────────
If Docker is not available, the sandbox falls back to native execution
and logs a warning. This keeps the harness functional on developer
machines without Docker while enforcing isolation in CI.

Path translation
────────────────
The gate's temp files live at e.g. /tmp/harness_xxx/ on the host.
Inside the container they are mounted at /work/.
Error output from tools refers to /work/file.py; the sandbox
translates these back to host paths before the inner gate's
_parse_errors() runs, so error line numbers and file names remain correct.

Usage
─────
# In config:
from harness.sandbox import SandboxConfig
config = HarnessConfig(
    ...,
    sandbox=SandboxConfig(enabled=True, language="python"),
)

# build_harness() uses it automatically when config.sandbox is set.
"""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .models import GateError, GateResult, GeneratedArtifact
from .gates.base import BaseGate, ProcessResult, run_process

log = logging.getLogger("harness.sandbox")

# Container workdir — all temp files are mounted here
CONTAINER_WORK = "/work"

# Default Docker images (built from harness/docker/Dockerfile.<lang>)
DEFAULT_IMAGES = {
    "python":     "harness-python:latest",
    "typescript": "harness-typescript:latest",
    "go":         "harness-go:latest",
    "rust":       "harness-rust:latest",
}


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class SandboxConfig:
    """Docker sandboxing configuration."""
    enabled: bool = True
    language: str = "python"
    image: str = ""                      # defaults to DEFAULT_IMAGES[language]
    network: str = "none"                # "none" | "bridge" | specific network
    memory_limit: str = "512m"
    cpu_limit: float = 2.0
    pids_limit: int = 128
    extra_mounts: list[str] = field(default_factory=list)  # ["/host/path:/container/path:ro"]
    fallback_on_docker_missing: bool = True

    def resolved_image(self) -> str:
        return self.image or DEFAULT_IMAGES.get(self.language, f"harness-{self.language}:latest")


# ── Sandboxed gate ─────────────────────────────────────────────────────────────

class SandboxedGate:
    """
    Wraps any BaseGate and executes its command inside a Docker container.

    Satisfies the ExecutionAdapter protocol — can be used anywhere a
    native gate is used.
    """

    def __init__(self, inner: BaseGate, sandbox: SandboxConfig):
        self._inner = inner
        self._sandbox = sandbox
        self._docker_available: bool | None = None

    @property
    def gate_name(self) -> str:
        return self._inner.gate_name

    def run(self, artifact: GeneratedArtifact, env) -> GateResult:
        if not self._is_docker_available():
            if self._sandbox.fallback_on_docker_missing:
                log.warning(
                    "Docker not available — running gate '%s' natively (unsandboxed)",
                    self.gate_name,
                )
                return self._inner.run(artifact, env)
            return GateResult(
                gate=self.gate_name, passed=False,
                errors=[GateError(
                    message="Docker not available and fallback is disabled",
                    file=None, line=None, column=None,
                    code="DOCKER_MISSING", severity="error",
                )],
                duration_ms=0,
            )

        start = time.monotonic()
        inner_command = self._inner._command(env)
        docker_command = self._build_docker_command(inner_command, env.root)

        try:
            result = run_process(
                docker_command,
                cwd=str(env.root),
                timeout=self._inner.DEFAULT_TIMEOUT + 10,  # allow Docker overhead
            )
        except Exception as e:
            return GateResult(
                gate=self.gate_name, passed=False,
                errors=[GateError(
                    message=f"Docker execution failed: {e}",
                    file=None, line=None, column=None,
                    code="DOCKER_ERROR", severity="error",
                )],
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        # Translate /work/ paths in output back to host paths
        translated = self._translate_output(result, env.root)
        errors = self._inner._parse_errors(translated, env)

        return GateResult(
            gate=self.gate_name,
            passed=result.returncode == 0 and not errors,
            errors=errors,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_docker_command(self, inner_cmd: list[str], host_workdir: Path) -> list[str]:
        cfg = self._sandbox
        cmd = [
            "docker", "run",
            "--rm",
            "--network", cfg.network,
            "--memory", cfg.memory_limit,
            "--memory-swap", cfg.memory_limit,   # disable swap
            "--cpus", str(cfg.cpu_limit),
            "--pids-limit", str(cfg.pids_limit),
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=128m",
            "--security-opt", "no-new-privileges",
            # Mount only the temp work directory
            "-v", f"{host_workdir}:{CONTAINER_WORK}:rw",
            "-w", CONTAINER_WORK,
        ]

        for mount in cfg.extra_mounts:
            cmd += ["-v", mount]

        cmd.append(cfg.resolved_image())
        cmd.extend(inner_cmd)
        return cmd

    def _translate_output(self, result: ProcessResult, host_root: Path) -> ProcessResult:
        """
        Replace /work/ references in tool output with the actual host path.
        This lets the inner gate's _parse_errors work on familiar paths.
        """
        host_str = str(host_root)
        stdout = result.stdout.replace(CONTAINER_WORK + "/", host_str + "/")
        stderr = result.stderr.replace(CONTAINER_WORK + "/", host_str + "/")
        return ProcessResult(stdout=stdout, stderr=stderr, returncode=result.returncode)

    def _is_docker_available(self) -> bool:
        if self._docker_available is None:
            self._docker_available = shutil.which("docker") is not None
            if not self._docker_available:
                log.warning("'docker' binary not found in PATH")
        return self._docker_available


# ── Image management ──────────────────────────────────────────────────────────

class SandboxImageBuilder:
    """Builds harness Docker images from the bundled Dockerfiles."""

    def __init__(self, dockerfiles_dir: str | None = None):
        if dockerfiles_dir is None:
            dockerfiles_dir = str(Path(__file__).parent / "docker")
        self._dir = Path(dockerfiles_dir)

    def build(self, language: str, no_cache: bool = False) -> bool:
        """
        Build the harness image for the given language.
        Returns True on success.
        """
        dockerfile = self._dir / f"Dockerfile.{language}"
        if not dockerfile.exists():
            log.error("Dockerfile not found: %s", dockerfile)
            return False

        image = DEFAULT_IMAGES.get(language, f"harness-{language}:latest")
        cmd = ["docker", "build", "-t", image, "-f", str(dockerfile), str(self._dir)]
        if no_cache:
            cmd.insert(2, "--no-cache")

        log.info("Building %s…", image)
        result = run_process(cmd, cwd=str(self._dir), timeout=300)
        if result.returncode != 0:
            log.error("Build failed:\n%s", result.output)
            return False
        log.info("Built %s successfully", image)
        return True

    def build_all(self, no_cache: bool = False) -> dict[str, bool]:
        return {
            lang: self.build(lang, no_cache)
            for lang in DEFAULT_IMAGES
        }

    def status(self) -> dict[str, bool]:
        """Check which harness images are present in the local Docker daemon."""
        results: dict[str, bool] = {}
        for lang, image in DEFAULT_IMAGES.items():
            result = run_process(
                ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                cwd=".", timeout=5,
            )
            results[lang] = result.returncode == 0
        return results


# ── Convenience wrapper ───────────────────────────────────────────────────────

from contextlib import contextmanager

@contextmanager
def sandboxed_gate_suite_for(
    language: str,
    artifact: GeneratedArtifact,
    project_root: str,
    sandbox: SandboxConfig | None = None,
):
    """
    Like gate_suite_for() but wraps every gate in a SandboxedGate.
    Falls back to native execution if Docker is unavailable and
    sandbox.fallback_on_docker_missing is True (the default).

    with sandboxed_gate_suite_for("python", artifact, "./", sandbox_cfg) as gates:
        results = [g.run(artifact) for g in gates]
    """
    from .gates import gate_suite_for
    cfg = sandbox or SandboxConfig(language=language)

    with gate_suite_for(language, artifact, project_root) as raw_gates:
        sandboxed = []
        for gate in raw_gates:
            # gate is already a language-specific wrapper (PythonGate etc.)
            # We need to access its _inner BaseGate to sandbox it
            if hasattr(gate, "_inner"):
                sandboxed.append(_SandboxedWrapper(gate, cfg))
            else:
                # Fallback: use as-is
                sandboxed.append(gate)
        yield sandboxed


class _SandboxedWrapper:
    """Wraps a language gate (PythonGate etc.) with sandboxed execution."""

    def __init__(self, lang_gate, cfg: SandboxConfig):
        self._gate = lang_gate
        self._sandboxed_inner = SandboxedGate(lang_gate._inner, cfg)

    @property
    def gate_name(self) -> str:
        return self._gate.gate_name

    def run(self, artifact: GeneratedArtifact) -> GateResult:
        return self._sandboxed_inner.run(artifact, self._gate._env)
