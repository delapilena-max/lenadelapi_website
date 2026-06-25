# pipeline/orchestrator.py
# Orchestrator for ReelForge pipeline with integrated Life Engine pre-publisher stage.
# Save this file at pipeline/orchestrator.py and run your pipeline entrypoint (e.g., python run_reel_forge.py).
# Python 3.8+

import sys
import uuid
import time
import traceback
from pathlib import Path
from datetime import datetime

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def log(stage: str, msg: str = ""):
    ts = datetime.utcnow().isoformat()
    if msg:
        print(f"[{ts}] [orchestrator] Running stage: {stage} - {msg}")
    else:
        print(f"[{ts}] [orchestrator] Running stage: {stage}")

# -------------------------
# Life Engine pre-publisher
# -------------------------
def run_life_engine_stage():
    """
    Import and run the life_engine hook (nodes.ai_lady_instagram.life_engine_hook.run_once).
    This runs inside the orchestrator process so imports and PYTHONPATH behave consistently.
    """
    try:
        import importlib
        hook = importlib.import_module("nodes.ai_lady_instagram.life_engine_hook")
        # run_once should return an exit code (0 success, non-zero otherwise)
        rc = getattr(hook, "run_once", lambda: 0)()
        if rc != 0:
            print(f"[orchestrator] life_engine_hook returned {rc}", file=sys.stderr)
        else:
            print("[orchestrator] life_engine_hook completed successfully")
    except ModuleNotFoundError:
        print("[orchestrator] life_engine_hook module not found; skipping life engine stage")
    except Exception:
        traceback.print_exc()
        print("[orchestrator] life_engine_hook failed", file=sys.stderr)

# -------------------------
# Pipeline stage runners
# -------------------------
def run_stage_callable(module_name: str, func_name: str = "run"):
    """
    Try to import module_name and call func_name() if present.
    If module or function is missing, skip with a log.
    """
    try:
        import importlib
        mod = importlib.import_module(module_name)
        func = getattr(mod, func_name, None)
        if callable(func):
            func()
            return True
        else:
            print(f"[orchestrator] {module_name}.{func_name} not found; skipping")
            return False
    except ModuleNotFoundError:
        print(f"[orchestrator] {module_name} not found; skipping")
        return False
    except Exception:
        traceback.print_exc()
        print(f"[orchestrator] Error running {module_name}.{func_name}", file=sys.stderr)
        return False

# -------------------------
# Minimal default stage implementations
# -------------------------
# These are fallbacks if your project doesn't provide the stage modules.
def default_dialogue():
    print("[dialogue] (default) generating dialogue..."); time.sleep(0.2)

def default_tts():
    print("[tts] (default) synthesizing audio..."); time.sleep(0.2)

def default_compositor():
    print("[compositor] (default) compositing assets..."); time.sleep(0.2)

def default_renderer():
    print("[renderer] (default) rendering final media..."); time.sleep(0.2)

def default_publisher():
    print("[publisher] (default) publishing outputs..."); time.sleep(0.2)

# -------------------------
# Main orchestrator flow
# -------------------------
def main():
    correlation_id = uuid.uuid4().hex
    print(f"[orchestrator] Pipeline start. Correlation ID: {correlation_id}")

    # Stage: dialogue
    log("dialogue")
    if not run_stage_callable("pipeline.stages.dialogue", "run"):
        default_dialogue()

    # Stage: tts
    log("tts")
    if not run_stage_callable("pipeline.stages.tts", "run"):
        default_tts()

    # Stage: compositor
    log("compositor")
    if not run_stage_callable("pipeline.stages.compositor", "run"):
        default_compositor()

    # Stage: renderer
    log("renderer")
    if not run_stage_callable("pipeline.stages.renderer", "run"):
        default_renderer()

    # Pre-publisher: run life engine hook to queue posts
    log("life_engine_pre_publisher")
    run_life_engine_stage()

    # Stage: publisher
    log("publisher")
    if not run_stage_callable("pipeline.stages.publisher", "run"):
        default_publisher()

    print(f"[orchestrator] Pipeline complete. Correlation ID: {correlation_id}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[orchestrator] Interrupted by user")
    except Exception:
        traceback.print_exc()
        print("[orchestrator] Fatal error", file=sys.stderr)
        raise
