"""
SDLC Agent Pipeline — Entry Point
──────────────────────────────────
Launches either the Streamlit UI or the FastAPI backend.

Usage:
  python main.py ui       # Start Streamlit UI (port 8501)
  python main.py api      # Start FastAPI backend (port 8000)
  python main.py both     # Start both concurrently
  python main.py run --project "My App" --files req.pdf sop.docx   # CLI run
"""

import sys
import subprocess
import argparse
from pathlib import Path


def start_ui():
    print("🖥  Starting Streamlit UI → http://localhost:8501")
    subprocess.run(["streamlit", "run", "ui/app.py", "--server.port", "8501"])


def start_api():
    print("⚙  Starting FastAPI backend → http://localhost:8000")
    subprocess.run(["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"])


def start_both():
    import threading
    t1 = threading.Thread(target=start_api, daemon=True)
    t2 = threading.Thread(target=start_ui)
    t1.start()
    t2.start()
    t2.join()


def cli_run(project: str, files: list[str], cloud: str = "aws", start_from: int = 0, dry_run: bool = False):
    """Run the pipeline from the command line without the UI."""
    import asyncio
    from config.logging import setup_logging
    from database.db import init_db
    from models.pipeline_state import PipelineState, AgentStatus
    from orchestrator.pipeline import PipelineOrchestrator, TOTAL_AGENTS
    from orchestrator.events import event_bus
    from rich.console import Console
    import time

    setup_logging()
    init_db()
    console = Console()

    if start_from > 0:
        # Resume: reload the last saved state so prior agent outputs are available
        from orchestrator.state_manager import PipelineStateManager
        saved = PipelineStateManager.load_last_run_for_project(project)
        if saved:
            state = saved
            console.print(f"[yellow]↩ Resuming run {state.run_id} from agent {start_from + 1}/11[/yellow]")
        else:
            console.print(f"[red]No saved run found for '{project}' — starting fresh[/red]")
            state = PipelineState(project_name=project, cloud_provider=cloud, input_files=files)
            start_from = 0
    else:
        state = PipelineState(
            project_name=project,
            cloud_provider=cloud,
            input_files=files,
        )

    console.rule(f"[bold blue]SDLC Pipeline — {project}[/bold blue]")
    if dry_run:
        console.print("[yellow]⚡ DRY-RUN mode — no Claude API calls[/yellow]\n")

    async def run():
        # Subscribe to events for live console output
        queue = event_bus.subscribe(state.run_id)
        orchestrator = PipelineOrchestrator()

        # Run pipeline in background
        pipeline_task = asyncio.create_task(
            orchestrator.run(state, start_from=start_from, dry_run=dry_run)
        )

        t0 = time.time()
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Check if pipeline finished
                if pipeline_task.done():
                    break
                continue

            etype = event.get("type", "")
            if etype == "agent_started":
                step  = event.get("step", "?")
                total = event.get("total", TOTAL_AGENTS)
                console.print(f"[cyan]▶[/cyan] [{step}/{total}] {event.get('agent_name','')}")
            elif etype == "agent_completed":
                step  = event.get("step", "?")
                total = event.get("total", TOTAL_AGENTS)
                console.print(f"[green]✔[/green] [{step}/{total}] {event.get('agent_name','')}: {event.get('summary','')}")
            elif etype == "agent_failed":
                console.print(f"[red]✖[/red] {event.get('agent_name', event.get('agent','?'))} FAILED: {event.get('error','')}")
            elif etype == "log":
                pass  # loguru already prints these
            elif etype == "pipeline_completed":
                elapsed = time.time() - t0
                console.rule(f"[bold green]Pipeline Complete! ({elapsed:.0f}s)[/bold green]")
                break
            elif etype == "pipeline_failed":
                console.rule(f"[bold red]Pipeline Failed: {event.get('error','')}[/bold red]")
                break
            elif etype == "__done__":
                break

        event_bus.unsubscribe(state.run_id, queue)
        final = await pipeline_task

        # Summary table
        results = list(final.agent_results.values()) if isinstance(final.agent_results, dict) else (final.agent_results or [])
        ok  = [r for r in results if r.status == AgentStatus.COMPLETED]
        bad = [r for r in results if r.status == AgentStatus.FAILED]
        console.print(f"\n[bold]{'✅' if not bad else '❌'} {len(ok)}/{TOTAL_AGENTS} agents completed | {len(bad)} failed[/bold]")
        if bad:
            for r in bad:
                console.print(f"  [red]✗[/red] {r.agent_name}: {r.error}")

    asyncio.run(run())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SDLC Agent Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("ui",   help="Start Streamlit UI")
    subparsers.add_parser("api",  help="Start FastAPI backend")
    subparsers.add_parser("both", help="Start both UI and API")

    run_parser = subparsers.add_parser("run", help="Run pipeline via CLI")
    run_parser.add_argument("--project", required=True, help="Project name")
    run_parser.add_argument("--files", nargs="+", required=True, help="Input files")
    run_parser.add_argument("--cloud", default="gcp", choices=["aws", "gcp", "azure", "localhost"])
    run_parser.add_argument("--start-from", type=int, default=0, help="Start from agent N (0-indexed)")
    run_parser.add_argument("--dry-run", action="store_true", help="Mock all agents (no Claude API calls)")

    args = parser.parse_args()

    if args.command == "ui":
        start_ui()
    elif args.command == "api":
        start_api()
    elif args.command == "both":
        start_both()
    elif args.command == "run":
        cli_run(args.project, args.files, args.cloud, args.start_from, getattr(args, "dry_run", False))
    else:
        parser.print_help()
