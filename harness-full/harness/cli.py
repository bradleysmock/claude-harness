"""
python -m harness <command> [args]

Single-spec commands:
  init                    Set up harness in current repo
  forge  <description>    Open Claude Code with forge-spec command
  submit <spec>           Run a spec through the harness
  review <spec>           Open Claude Code with review-spec command
  finish <run-id>         Open Claude Code with finish-task command
  debug  <run-id>         Open Claude Code with debug-escalation command

Multi-spec task commands:
  forge-task <description>  Open Claude Code with forge-task command
  task       <task-file>    Run a full task (DAG of specs)
  debug-task <run-id>       Open Claude Code to debug a task run

Utility:
  status                  Show recent runs
  stats                   Show failure memory statistics
"""

from __future__ import annotations
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


# ── Single-spec commands ──────────────────────────────────────────────────────

def cmd_init(args):
    dirs = [
        ".claude/commands",
        ".harness/specs",
        ".harness/tasks",
        ".harness/results",
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        print(f"  created {d}/")

    # Copy Claude Code commands from package
    commands_src = Path(__file__).parent / "commands"
    commands_dst = Path(".claude/commands")
    if commands_src.exists():
        for f in commands_src.glob("*.md"):
            dst = commands_dst / f.name
            if not dst.exists():
                dst.write_text(f.read_text())
                print(f"  wrote   {dst}")

    # Gitignore
    gitignore = Path(".gitignore")
    entries = [".harness/results/", "harness_memory.db"]
    if gitignore.exists():
        existing = gitignore.read_text()
        with gitignore.open("a") as fh:
            for e in entries:
                if e not in existing:
                    fh.write(f"\n{e}")
        print("  updated .gitignore")

    # Config template
    config_path = Path(".harness/config.py")
    if not config_path.exists():
        config_path.write_text(_CONFIG_TEMPLATE)
        print("  wrote   .harness/config.py  ← edit before first run")

    print("\nDone. Next:")
    print("  1. Edit .harness/config.py")
    print("  2. make forge TASK='your task'         (single spec)")
    print("     make forge-task FEATURE='your feature' (multi-spec)")


def cmd_forge(args):
    if not args:
        print("Usage: python -m harness forge 'task description'")
        sys.exit(1)
    _open_claude(f"/forge-spec\n\nTask: {' '.join(args)}")


def cmd_submit(args):
    force = "--force" in args
    args = [a for a in args if a != "--force"]

    if not args:
        _list_specs()
        sys.exit(0)

    spec_path = _resolve(".harness/specs", args[0], ".py")
    config = _load_config()
    spec = _load_object(spec_path, "spec")

    # ── Quality gate ──────────────────────────────────────────────────────────
    from harness.scorer import SpecScorer
    score = SpecScorer().score(spec, project_root=config.index.project_root)
    print(score.formatted_report())

    if score.verdict == "block" and not force:
        print("Submission blocked. Fix the issues above or run with --force.")
        sys.exit(2)
    if score.verdict == "warn":
        print("Proceeding with warnings. Consider fixing before retrying on failure.\n")

    # ── Run ───────────────────────────────────────────────────────────────────
    print(f"Submitting spec: {spec.id}")
    print("─" * 52)

    from harness import build_harness
    harness = build_harness(config)
    run = harness.run(spec)

    result_path = Path(f".harness/results/{spec.id}.json")
    result_path.write_text(json.dumps(_run_to_dict(run), indent=2))

    print("─" * 52)
    if run.outcome == "passed":
        print(f"\n✓ Passed in {len(run.attempts)} attempt(s)")
        print(f"  Next: python -m harness finish {spec.id}")
    else:
        print(f"\n⚠ Escalated after {len(run.attempts)} attempt(s)")
        print(f"  Next: python -m harness debug {spec.id}")

    sys.exit(0 if run.outcome == "passed" else 1)


def cmd_review(args):
    if not args:
        _list_specs(); sys.exit(0)
    spec_path = _resolve(".harness/specs", args[0], ".py")
    _open_claude(f"/review-spec\n\nSpec file: {spec_path}")


def cmd_finish(args):
    if not args:
        _list_results(outcome="passed"); sys.exit(0)
    result_path = _resolve(".harness/results", args[0], ".json")
    _open_claude(f"/finish-task\n\nResult file: {result_path}")


def cmd_debug(args):
    if not args:
        _list_results(outcome="escalated"); sys.exit(0)
    result_path = _resolve(".harness/results", args[0], ".json")
    _open_claude(f"/debug-escalation\n\nResult file: {result_path}")


# ── Multi-spec task commands ──────────────────────────────────────────────────

def cmd_forge_task(args):
    if not args:
        print("Usage: python -m harness forge-task 'feature description'")
        sys.exit(1)
    _open_claude(f"/forge-task\n\nFeature: {' '.join(args)}")


def cmd_task(args):
    force = "--force" in args
    args = [a for a in args if a != "--force"]

    if not args:
        _list_tasks(); sys.exit(0)

    task_path = _resolve(".harness/tasks", args[0], ".py")
    config = _load_config()
    task = _load_object(task_path, "task")

    # ── Quality gate — score all specs before any API call ────────────────────
    from harness.scorer import SpecScorer
    scorer = SpecScorer()
    blocked_specs, warned_specs = [], []
    for ts in task.specs:
        s = scorer.score(ts.spec, project_root=config.index.project_root)
        print(s.formatted_report())
        if s.verdict == "block":
            blocked_specs.append(ts.spec.id)
        elif s.verdict == "warn":
            warned_specs.append(ts.spec.id)
    if blocked_specs and not force:
        print(f"Task blocked — fix issues in: {', '.join(blocked_specs)}")
        print("Run with --force to submit anyway.")
        sys.exit(2)
    if warned_specs:
        print(f"Warnings in: {', '.join(warned_specs)} — proceeding.\n")

    print(f"\nTask: {task.id}")
    print(f"Specs ({len(task.specs)}): {', '.join(ts.spec.id for ts in task.specs)}")
    print("─" * 52)

    from harness import build_harness, TaskOrchestrator
    harness = build_harness(config)
    task_orch = TaskOrchestrator(spec_orchestrator=harness)
    task_run = task_orch.run(task, task_file_path=task_path)

    result_path = Path(f".harness/results/{task.id}.task.json")
    result_path.write_text(json.dumps(_task_run_to_dict(task_run), indent=2))

    print("─" * 52)
    print(f"\nOutcome:  {task_run.outcome.upper()}")
    print(f"Passed:   {len(task_run.passed_specs)}/{len(task.specs)}")
    print(f"Duration: {task_run.total_duration_ms:,}ms\n")

    for sr in task_run.spec_runs:
        icon = "✓" if sr.run.outcome == "passed" else ("~" if sr.blocked_by else "✗")
        note = f"  ← blocked by: {sr.blocked_by}" if sr.blocked_by else ""
        print(f"  {icon} {sr.task_spec.spec.id}{note}")

    if task_run.outcome == "passed":
        print(f"\n  Next: python -m harness finish-task {task.id}")
    else:
        print(f"\n  Next: python -m harness debug-task {task.id}")

    sys.exit(0 if task_run.outcome == "passed" else 1)


def cmd_finish_task(args):
    if not args:
        _list_results(suffix=".task.json"); sys.exit(0)
    result_path = _resolve(".harness/results", args[0], ".task.json")
    _open_claude(f"/finish-task\n\nTask result file: {result_path}")


def cmd_debug_task(args):
    if not args:
        _list_results(suffix=".task.json", outcome="partial"); sys.exit(0)
    result_path = _resolve(".harness/results", args[0], ".task.json")
    _open_claude(f"/debug-escalation\n\nTask result file: {result_path}")


def cmd_task_reset(args):
    """Clear the checkpoint for a task, forcing a full re-run."""
    if not args:
        print("Usage: python -m harness task-reset <task-name>")
        sys.exit(1)
    from harness.checkpoint import CheckpointStore
    store = CheckpointStore()
    cleared = store.clear(args[0])
    if cleared:
        print(f"Checkpoint cleared: {args[0]}")
    else:
        print(f"No checkpoint found for: {args[0]}")


def cmd_checkpoint_status(args):
    """Show checkpoint status for all tasks or a specific task."""
    from harness.checkpoint import CheckpointStore
    store = CheckpointStore()
    task_dir = Path(".harness/tasks")
    checkpoints_dir = Path(".harness/checkpoints")

    if not checkpoints_dir.exists() or not list(checkpoints_dir.glob("*.json")):
        print("No checkpoints found.")
        return

    tasks = [args[0]] if args else [
        f.stem for f in checkpoints_dir.glob("*.json")
    ]
    for task_id in tasks:
        status = store.status(task_id)
        if status:
            specs = status["completed_specs"]
            print(f"  {task_id}")
            print(f"    Updated:   {status['updated_at']}")
            print(f"    Completed: {len(specs)} spec(s) — {', '.join(specs)}")
        else:
            print(f"  {task_id}  (no checkpoint)")


def cmd_index_status(args):
    """Show index statistics: chunk count, file count, last sync."""
    config = _load_config()
    from harness.index import PersistedVectorStore
    store = PersistedVectorStore(db_path=config.index.index_db_path)
    manifest = store.get_manifest()
    total_chunks = store.count()
    print(f"\nIndex: {config.index.index_db_path}")
    print(f"  Files indexed:  {len(manifest)}")
    print(f"  Chunks total:   {total_chunks}")
    if manifest:
        last = max(v[0] for v in manifest.values()) if manifest else "never"
        # get indexed_at from DB directly
        import sqlite3, json as _j
        with sqlite3.connect(config.index.index_db_path) as conn:
            row = conn.execute(
                "SELECT MAX(indexed_at) FROM file_manifest"
            ).fetchone()
        print(f"  Last synced:    {row[0] or 'never'}")
    print()


def cmd_index_rebuild(args):
    """Force a full re-index, re-embedding all files regardless of hash."""
    config = _load_config()
    from harness.context import AnthropicEmbedder, SemanticChunker
    from harness.index import PersistedVectorStore, IncrementalIndexer
    embedder = AnthropicEmbedder(api_key=config.llm.api_key)
    store = PersistedVectorStore(db_path=config.index.index_db_path)
    indexer = IncrementalIndexer(
        SemanticChunker(), embedder, store,
        ignore_patterns=config.index.ignore_patterns,
    )
    print(f"Force re-indexing {config.index.project_root}…")
    stats = indexer.sync(config.index.project_root, force=True)
    print(f"  {stats.summary()}")
    if config.index.convention_files:
        n = indexer.sync_conventions(config.index.convention_files)
        print(f"  Conventions: {n} file(s) updated")


def cmd_sandbox_build(args):
    """Build harness Docker images for sandboxed execution."""
    from harness.sandbox import SandboxImageBuilder
    builder = SandboxImageBuilder()
    no_cache = "--no-cache" in args
    languages = [a for a in args if not a.startswith("--")]

    if not languages:
        # Build all
        results = builder.build_all(no_cache=no_cache)
        for lang, ok in results.items():
            print(f"  {'✓' if ok else '✗'} harness-{lang}:latest")
    else:
        for lang in languages:
            ok = builder.build(lang, no_cache=no_cache)
            print(f"  {'✓' if ok else '✗'} harness-{lang}:latest")


def cmd_sandbox_status(args):
    """Show which harness Docker images are available."""
    import shutil
    if not shutil.which("docker"):
        print("Docker not found in PATH — sandbox unavailable")
        return
    from harness.sandbox import SandboxImageBuilder
    builder = SandboxImageBuilder()
    status = builder.status()
    print("\nHarness sandbox images:")
    for lang, present in status.items():
        icon = "✓" if present else "✗ (run: make sandbox-build LANG=" + lang + ")"
        print(f"  {icon}  harness-{lang}:latest")
    print()


def cmd_harden(args):
    """Preview spec hardening without running generation. Useful for review."""
    if not args:
        print("Usage: python -m harness harden <spec-name>")
        sys.exit(1)

    spec_path = _resolve(".harness/specs", args[0], ".py")
    config = _load_config()
    spec = _load_object(spec_path, "spec")

    from harness import build_harness
    from harness.hardener import SpecHardener
    from harness.llm.client import AnthropicLLMClient

    llm = AnthropicLLMClient(
        api_key=config.llm.api_key, model=config.llm.model,
        temperature=config.llm.temperature, max_retries=config.llm.prompt_retries,
    )
    hardener = SpecHardener(llm_client=llm)
    _, report = hardener.harden(spec)
    print(report.formatted())

    if report.open_ambiguities:
        print("\nNote: open ambiguities exist. Resolve them in the spec before submitting.")
        sys.exit(1)
    sys.exit(0)


# ── Utility commands ──────────────────────────────────────────────────────────

def cmd_status(args):
    results = list(Path(".harness/results").glob("*.json"))
    if not results:
        print("No runs yet.")
        return
    runs = []
    for f in sorted(results, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            runs.append((f.name, json.loads(f.read_text())))
        except Exception:
            continue
    print(f"\n{'FILE':<40} {'OUTCOME':<12} {'DURATION':>10}")
    print("─" * 64)
    for name, r in runs[:20]:
        ms = r.get("total_duration_ms", "?")
        ms_str = f"{ms:,}ms" if isinstance(ms, int) else str(ms)
        print(f"{name:<40} {r.get('outcome','?'):<12} {ms_str:>10}")


def cmd_stats(args):
    config = _load_config()
    from harness.memory import SQLiteFailureMemory
    from harness.context import AnthropicEmbedder
    memory = SQLiteFailureMemory(
        db_path=config.db_path,
        embedder=AnthropicEmbedder(api_key=config.llm.api_key),
    )
    s = memory.stats()
    print(f"\nTotal runs:       {s.total_runs}")
    print(f"Total failures:   {s.total_failures}")
    print(f"Resolution rate:  {s.resolution_rate:.1%}")
    print(f"Mean attempts:    {s.mean_attempts_to_resolve}")
    if s.failures_by_gate:
        print("\nFailures by gate:")
        for gate, n in sorted(s.failures_by_gate.items(), key=lambda x: -x[1]):
            print(f"  {gate:<22} {n}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _open_claude(message: str):
    try:
        subprocess.run(["claude", "--message", message])
    except FileNotFoundError:
        print("Claude Code CLI not found. Install: https://claude.ai/code")
        print("\nPaste this into Claude Code manually:\n" + "─" * 50)
        print(message)


def _load_config():
    return _load_object(".harness/config.py", "config")


def _load_object(path: str, attr: str):
    spec = importlib.util.spec_from_file_location("_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, attr)


def _resolve(directory: str, name: str, ext: str) -> str:
    candidates = [
        name,
        f"{directory}/{name}",
        f"{directory}/{name}{ext}",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    print(f"Not found: {name} (looked in {directory}/)")
    sys.exit(1)


def _list_specs():
    _list_dir(".harness/specs", "*.py", "specs")

def _list_tasks():
    _list_dir(".harness/tasks", "*.py", "tasks")

def _list_dir(directory: str, pattern: str, label: str):
    items = list(Path(directory).glob(pattern))
    if not items:
        print(f"No {label} in {directory}/")
    else:
        print(f"Available {label}:")
        for p in items:
            print(f"  {p.stem}")

def _list_results(suffix: str = ".json", outcome: str | None = None):
    for f in Path(".harness/results").glob(f"*{suffix}"):
        try:
            data = json.loads(f.read_text())
            if outcome is None or data.get("outcome") == outcome:
                print(f"  {f.stem}  ({data.get('outcome', '?')})")
        except Exception:
            continue


def _run_to_dict(run) -> dict:
    return {
        "id": run.id, "outcome": run.outcome,
        "total_duration_ms": run.total_duration_ms,
        "spec": {"id": run.spec.id, "metadata": run.spec.metadata},
        "attempts": [
            {
                "number": a.number,
                "artifact": {
                    "implementation": a.artifact.implementation,
                    "tests": a.artifact.tests,
                    "reasoning": a.artifact.reasoning,
                    "assumptions": a.artifact.assumptions,
                    "notes": a.artifact.notes,
                },
                "gate_results": [
                    {"gate": g.gate, "passed": g.passed, "duration_ms": g.duration_ms,
                     "errors": [{"message": e.message, "file": e.file,
                                 "line": e.line, "code": e.code}
                                for e in g.errors]}
                    for g in a.gate_results
                ],
            }
            for a in run.attempts
        ],
    }


def _task_run_to_dict(task_run) -> dict:
    return {
        "id": task_run.id,
        "task_id": task_run.task.id,
        "outcome": task_run.outcome,
        "total_duration_ms": task_run.total_duration_ms,
        "spec_runs": [
            {
                "spec_id": sr.task_spec.spec.id,
                "outcome": sr.run.outcome,
                "blocked_by": sr.blocked_by,
                "attempts": len(sr.run.attempts),
                "implementation": (
                    sr.run.attempts[-1].artifact.implementation
                    if sr.run.attempts else None
                ),
                "target_file": sr.task_spec.spec.metadata.get("target_file"),
            }
            for sr in task_run.spec_runs
        ],
    }


_CONFIG_TEMPLATE = '''\
"""Harness configuration for this repo. Edit before first run."""
import os
from harness import HarnessConfig, LLMConfig, IndexConfig

config = HarnessConfig(
    llm=LLMConfig(
        api_key=os.environ["ANTHROPIC_API_KEY"],
    ),
    index=IndexConfig(
        project_root="./src",                    # adjust to your source root
        convention_files=["./CONVENTIONS.md"],   # add PATTERNS.md etc. as needed
        index_db_path=".harness/index.db",       # persisted vector store
    ),
    db_path=".harness/memory.db",
    max_retries=3,
    log_level="INFO",
)
'''


# ── Score command ─────────────────────────────────────────────────────────────

def cmd_score(args):
    """Score a spec or all specs in a task without submitting."""
    if not args:
        print("Usage: python -m harness score <spec-or-task-name>")
        sys.exit(1)

    from harness.scorer import SpecScorer
    config = _load_config()
    scorer = SpecScorer()

    # Try as task first, then spec
    task_path = Path(f".harness/tasks/{args[0]}.py")
    spec_path_candidate = Path(f".harness/specs/{args[0]}.py")

    if task_path.exists():
        task = _load_object(str(task_path), "task")
        all_pass = True
        for ts in task.specs:
            s = scorer.score(ts.spec, project_root=config.index.project_root)
            print(s.formatted_report())
            if s.verdict != "pass":
                all_pass = False
        sys.exit(0 if all_pass else 1)
    elif spec_path_candidate.exists() or any(
        Path(p).exists() for p in [args[0], f".harness/specs/{args[0]}"]
    ):
        spec_path = _resolve(".harness/specs", args[0], ".py")
        spec = _load_object(spec_path, "spec")
        s = scorer.score(spec, project_root=config.index.project_root)
        print(s.formatted_report())
        sys.exit(0 if s.verdict == "pass" else 1)
    else:
        print(f"Not found as spec or task: {args[0]}")
        sys.exit(1)


# ── Entry point ───────────────────────────────────────────────────────────────

COMMANDS = {
    "init":               cmd_init,
    "forge":              cmd_forge,
    "score":              cmd_score,
    "harden":             cmd_harden,
    "submit":             cmd_submit,
    "review":             cmd_review,
    "finish":             cmd_finish,
    "debug":              cmd_debug,
    "forge-task":         cmd_forge_task,
    "task":               cmd_task,
    "task-reset":         cmd_task_reset,
    "checkpoint-status":  cmd_checkpoint_status,
    "finish-task":        cmd_finish_task,
    "debug-task":         cmd_debug_task,
    "index-status":       cmd_index_status,
    "index-rebuild":      cmd_index_rebuild,
    "sandbox-build":      cmd_sandbox_build,
    "sandbox-status":     cmd_sandbox_status,
    "status":             cmd_status,
    "stats":              cmd_stats,
}

def main():
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        print(__doc__)
        sys.exit(0)
    COMMANDS[args[0]](args[1:])

if __name__ == "__main__":
    main()
