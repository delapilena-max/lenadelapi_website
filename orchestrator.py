"""
orchestrator.py — Human-pattern posting orchestrator
Discovers nodes in nodes/, drains queue/ with staggered human timing,
builds face cache when queue drops below threshold.
Run daily via Windows Task Scheduler → run_daily.bat
"""
import json, sys, subprocess, time, logging
from datetime import datetime, date, timedelta
from pathlib import Path
from human_schedule import should_post_today, get_post_times, TZ

ROOT    = Path(__file__).parent
NODES   = ROOT / "nodes"
QUEUE   = ROOT / "queue"
POSTED  = ROOT / "posted"
LOG_DIR = ROOT / "logs"
PYTHON  = sys.executable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"orchestrator_{date.today()}.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("orch")

# ── Helpers ────────────────────────────────────────────────────────────────────

def run(cmd, label):
    cmd = [str(c) for c in cmd]
    log.info(f"[{label}] {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=ROOT)
    log.info(f"[{label}] exit={r.returncode}")
    return r.returncode

def sleep_until(t, label):
    secs = (t - datetime.now(tz=TZ)).total_seconds()
    if secs > 0:
        log.info(f"Sleeping {secs/60:.1f} min → {t.strftime('%H:%M')} [{label}]")
        time.sleep(secs)

# ── Node discovery ─────────────────────────────────────────────────────────────

def discover_nodes():
    nodes = []
    if not NODES.exists():
        log.error(f"nodes/ directory not found at {NODES}")
        return nodes
    for d in sorted(NODES.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        rf = d / "posting_rules.json"
        if not rf.exists():
            log.warning(f"nodes/{d.name}: no posting_rules.json — skipping")
            continue
        rules = json.loads(rf.read_text(encoding="utf-8"))
        if not rules.get("enabled", True):
            log.info(f"nodes/{d.name}: disabled")
            continue
        rules["_name"] = d.name
        rules["_dir"]  = d
        nodes.append(rules)
        log.info(f"Node: {d.name} ({rules.get('node_type', 'generic')})")
    return nodes

# ── Queue ──────────────────────────────────────────────────────────────────────

def scan_queue():
    """All episode dirs in queue/ that have final_video.mp4, sorted oldest first."""
    eps = []
    if not QUEUE.exists():
        return eps
    for ep_dir in sorted(QUEUE.iterdir()):
        if not ep_dir.is_dir():
            continue
        vid  = ep_dir / "final_video.mp4"
        meta = ep_dir / "episode.json"
        if not vid.exists():
            continue
        node_name = None
        if meta.exists():
            try:
                m = json.loads(meta.read_text(encoding="utf-8"))
                node_name = (m.get("node") or m.get("character")
                             or m.get("persona") or m.get("node_name"))
            except Exception:
                pass
        eps.append({"dir": ep_dir, "video": vid, "meta": meta, "node": node_name})
    return eps

def queue_count_for(episodes, node_name):
    return sum(1 for e in episodes if e["node"] in (None, node_name))

def mark_posted(ep, platform):
    """Write a receipt to posted/<ep>/posted_log.json.
    Does NOT move the folder so other platforms can still post it."""
    dest = POSTED / ep["dir"].name
    dest.mkdir(parents=True, exist_ok=True)
    receipt = dest / "posted_log.json"
    entry = {"posted_at": datetime.now(tz=TZ).isoformat(), "platform": platform}
    try:
        existing = json.loads(receipt.read_text()) if receipt.exists() else []
        if not isinstance(existing, list):
            existing = [existing]
        existing.append(entry)
        receipt.write_text(json.dumps(existing, indent=2))
    except Exception as e:
        log.warning(f"Could not write receipt: {e}")

# ── Auth ───────────────────────────────────────────────────────────────────────

def refresh_auth():
    s = ROOT / "save_state_cdp.py"
    if s.exists():
        log.info("Refreshing Kling auth...")
        run([PYTHON, s], "auth")
        time.sleep(4)
    else:
        log.warning("save_state_cdp.py not found, skipping auth refresh")

# ── Build ──────────────────────────────────────────────────────────────────────

def build_face_cache(node):
    count = node.get("face_cache_count", 1)
    run([PYTHON, ROOT / "face_cache_builder.py", "--count", str(count)],
        f"{node['_name']}/face_build")
    time.sleep(5)

# ── Post ───────────────────────────────────────────────────────────────────────

def post_episode(ep, platform, node):
    cmds  = node.get("post_commands", {})
    parts = cmds.get(platform)

    if parts:
        script = ROOT / parts[0]
        extra  = parts[1:]
    else:
        script = ROOT / "posting_agent.py"
        extra  = ["--platform", platform]

    if not script.exists():
        log.warning(f"Script not found: {script} — skipping {platform}")
        return False

    cmd = [PYTHON, script] + extra + ["--video", str(ep["video"])]
    if ep["meta"].exists():
        cmd += ["--meta", str(ep["meta"])]

    rc = run(cmd, f"{node['_name']}/{platform}")
    if rc == 0:
        mark_posted(ep, platform)
        return True
    log.warning(f"Post failed: {node['_name']} → {platform} (exit {rc})")
    return False

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    POSTED.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    today = date.today()
    now   = datetime.now(tz=TZ)
    log.info(f"=== Orchestrator {today.strftime('%A %B %d %Y')} {now.strftime('%H:%M %Z')} ===")

    nodes  = discover_nodes()
    active = [n for n in nodes if should_post_today(n["_name"], n, today)]
    log.info(f"Active today: {[n['_name'] for n in active]}")

    if not active:
        log.info("No nodes scheduled today — exiting.")
        return

    # Auth once at the top — all nodes share kling session
    refresh_auth()

    # Scan queue once
    all_episodes = scan_queue()
    log.info(f"Queue: {len(all_episodes)} episodes ready")

    # ── Face cache builds ──────────────────────────────────────────────────────
    # Build before the posting window opens so content is ready
    for node in active:
        if not node.get("build_face_cache", False):
            continue
        threshold = node.get("queue_min_threshold", 3)
        count     = queue_count_for(all_episodes, node["_name"])
        if count < threshold:
            log.info(f"{node['_name']}: queue={count} < threshold={threshold}, building face cache")
            build_face_cache(node)
        else:
            log.info(f"{node['_name']}: queue={count} episodes, no build needed")

    # ── Build posting schedule ─────────────────────────────────────────────────
    # Each active node gets human-pattern post times; we pair them with
    # queue episodes round-robin, oldest episode first.
    ep_cursor = {n["_name"]: 0 for n in active}
    node_eps  = {
        n["_name"]: [e for e in all_episodes if e["node"] in (None, n["_name"])]
        for n in active
    }

    schedule = []  # list of (datetime, node, platform, episode)
    for node in active:
        for post_time, platform in get_post_times(node["_name"], node, today):
            eps = node_eps[node["_name"]]
            idx = ep_cursor[node["_name"]]
            if idx >= len(eps):
                log.info(f"{node['_name']}: no more episodes for {platform}, skipping slot")
                continue
            schedule.append((post_time, node, platform, eps[idx]))
            ep_cursor[node["_name"]] += 1

    schedule.sort(key=lambda x: x[0])

    if not schedule:
        log.info("Nothing to post today — queue may be empty.")
        return

    log.info(f"Today's schedule ({len(schedule)} posts):")
    for t, node, platform, ep in schedule:
        log.info(f"  {t.strftime('%H:%M')}  {node['_name']} → {platform}  [{ep['dir'].name}]")

    # ── Execute ────────────────────────────────────────────────────────────────
    for post_time, node, platform, ep in schedule:
        sleep_until(post_time, f"{node['_name']}/{platform}")
        success = post_episode(ep, platform, node)
        if success:
            log.info(f"✓ Posted: {node['_name']} → {platform} [{ep['dir'].name}]")
        # Brief human pause between consecutive posts regardless of success
        time.sleep(8)

    log.info("=== Orchestrator run complete ===")

if __name__ == "__main__":
    main()
