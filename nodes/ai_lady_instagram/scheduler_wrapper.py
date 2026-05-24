import os
import random
import subprocess
import sys
import time
from pathlib import Path

BASE = Path("nodes/ai_lady_instagram")
PYTHON = sys.executable or "python"

# How many interaction sessions per day (roughly)
MIN_INTERACTIONS_PER_DAY = 2
MAX_INTERACTIONS_PER_DAY = 5

# How many posting checks per day (if you have a watcher/poster loop)
MIN_POST_CHECKS_PER_DAY = 2
MAX_POST_CHECKS_PER_DAY = 6

# Random delay bounds between tasks (seconds)
MIN_DELAY_BETWEEN_TASKS = 300   # 5 minutes
MAX_DELAY_BETWEEN_TASKS = 2400  # 40 minutes


def run_script(script_name, *args):
    script_path = BASE / script_name
    if not script_path.exists():
        print(f"[WARN] Script not found: {script_path}")
        return

    cmd = [PYTHON, str(script_path), *args]
    print(f"[SCHEDULER] Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=False)
    except Exception as e:
        print(f"[SCHEDULER] Error running {script_name}: {e}")


def daily_schedule_loop():
    """
    Very simple scheduler:
    - Randomly decides how many interaction sessions to run
    - Randomly decides how many posting checks to run
    - Spreads them out with random delays
    - Intended to be run via cron / Task Scheduler once per day
    """
    interactions = random.randint(MIN_INTERACTIONS_PER_DAY, MAX_INTERACTIONS_PER_DAY)
    post_checks = random.randint(MIN_POST_CHECKS_PER_DAY, MAX_POST_CHECKS_PER_DAY)

    tasks = []

    for _ in range(interactions):
        tasks.append(("interaction", "interaction_worker.py"))

    for _ in range(post_checks):
        # If you have a watcher or poster script, wire it here
        # Example: tasks.append(("post_check", "watcher.py"))
        # For now, we just leave this as a placeholder hook.
        pass

    random.shuffle(tasks)

    print(f"[SCHEDULER] Today: {len(tasks)} tasks ({interactions} interactions, {post_checks} post checks)")

    for idx, (kind, script) in enumerate(tasks, start=1):
        print(f"[SCHEDULER] Task {idx}/{len(tasks)}: {kind} -> {script}")
        if kind == "interaction":
            run_script(script)
        else:
            run_script(script)

        delay = random.randint(MIN_DELAY_BETWEEN_TASKS, MAX_DELAY_BETWEEN_TASKS)
        print(f"[SCHEDULER] Sleeping {delay} seconds before next task…")
        time.sleep(delay)

    print("[SCHEDULER] Daily schedule loop complete.")


def main():
    daily_schedule_loop()


if __name__ == "__main__":
    main()
