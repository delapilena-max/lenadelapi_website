# nodes/ai_lady_instagram/poster_selenium.py
"""
Minimal, focused poster helper — single-purpose update.

Behavior:
- Force Chrome to use the exact profile folder you pass (absolute path).
- Log the resolved user-data-dir and profile-directory clearly.
- Enable mobile emulation (iPhone X) so Instagram serves the mobile upload UI.
- Navigate once to the upload URL and log the resulting current_url and whether the upload input exists.
- Exit immediately after logging so you can verify the profile selection without other changes.

Usage:
    python nodes/ai_lady_instagram/poster_selenium.py <profile_dir> <video_path> <caption> [username]

Run this and paste back the three log lines:
- Resolved user-data-root
- Resolved profile-directory
- Current URL after navigation and whether file input was found
"""

import sys
import time
import logging
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

UPLOAD_URL = "https://www.instagram.com/create/select/?force=1"

def setup_logger(profile_dir):
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    name = Path(profile_dir).name
    log_file = logs_dir / f"{name}.log"
    logger = logging.getLogger("poster_selenium_minimal")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(sh)
    return logger

def make_driver_force_profile(profile_path: str, logger):
    """
    Force Chrome to use the exact profile folder passed by the user.

    If the provided path points to a Chrome profile folder (contains Preferences),
    use its parent as --user-data-dir and the folder name as --profile-directory.

    Otherwise, use the provided path as the user-data-dir and 'Default' as profile-directory.
    """
    options = webdriver.ChromeOptions()

    p = Path(profile_path).expanduser()
    try:
        p = p.resolve()
    except Exception:
        p = p

    # Default fallbacks
    user_data_root = str(p)
    profile_dir_name = "Default"

    if p.exists():
        # If path looks like a profile folder (contains Preferences), use parent as user-data-dir
        if (p / "Preferences").exists() or (p / "Bookmarks").exists():
            user_data_root = str(p.parent)
            profile_dir_name = p.name
            logger.debug("make_driver_force_profile: detected profile folder (has Preferences/Bookmarks).")
        else:
            # If path contains Default or profile folders, treat it as user-data-dir and prefer Default
            if (p / "Default").exists():
                user_data_root = str(p)
                profile_dir_name = "Default"
                logger.debug("make_driver_force_profile: detected user-data-dir with Default profile.")
            else:
                # Use provided path as user-data-dir and Default as profile
                user_data_root = str(p)
                profile_dir_name = "Default"
                logger.debug("make_driver_force_profile: using provided path as user-data-dir (Default profile).")
    else:
        # Path doesn't exist: still pass it to Chrome (Chrome will create it) but log clearly
        user_data_root = str(p)
        profile_dir_name = "Default"
        logger.debug("make_driver_force_profile: provided path does not exist on disk; will pass to Chrome as-is.")

    # Log resolved values
    logger.info("Resolved user-data-root: %s", user_data_root)
    logger.info("Resolved profile-directory: %s", profile_dir_name)
    logger.debug("Expected profile path: %s", str(Path(user_data_root) / profile_dir_name))

    # Add flags and mobile emulation
    options.add_argument(f"--user-data-dir={user_data_root}")
    options.add_argument(f"--profile-directory={profile_dir_name}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-extensions")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option("mobileEmulation", {"deviceName": "iPhone X"})

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    # small window size for mobile emulation sanity
    try:
        driver.set_window_size(375, 812)
    except Exception:
        pass

    # quick UA debug
    try:
        ua = driver.execute_script("return navigator.userAgent;")
        logger.debug("Browser userAgent: %s", ua)
    except Exception:
        logger.debug("Could not read userAgent via JS.")

    return driver

def main(profile_dir, video_path, caption, username=None):
    logger = setup_logger(profile_dir)
    driver = None
    try:
        driver = make_driver_force_profile(profile_dir, logger)
        logger.info("Opened browser with profile: %s", profile_dir)

        # If a username was provided, navigate to the profile first so Chrome loads the expected Instagram account/profile
        if username:
            profile_url = f"https://www.instagram.com/{username}/"
            logger.info("Navigating to profile URL first: %s", profile_url)
            driver.get(profile_url)
            # small wait to allow profile to load and cookies/session to settle
            time.sleep(2)

        # Navigate once to the upload URL (with cache-busting param)
        url = UPLOAD_URL + ("&_ts=%d" % int(time.time()))
        logger.info("Navigating to upload URL: %s", url)
        driver.get(url)
        time.sleep(3)

        current = driver.current_url
        logger.info("Current URL after navigation: %s", current)

        # Check for file input presence
        try:
            inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            has_file_input = len(inputs) > 0
        except Exception:
            has_file_input = False

        logger.info("File input present on page: %s", has_file_input)

        # Done — exit so you can inspect logs and browser state
        return 0
    except Exception as e:
        logger.exception("Unhandled exception during profile test: %s", e)
        return 1
    finally:
        # Always close the driver so you can re-run quickly; if you want to keep it open for inspection,
        # run the script manually in an interactive session and comment out the quit below.
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python nodes/ai_lady_instagram/poster_selenium.py <profile_dir> <video_path> <caption> [username]")
        sys.exit(2)
    profile_dir = sys.argv[1]
    video_path = sys.argv[2]
    if len(sys.argv) >= 5:
        # treat the last argument as an optional Instagram username and the intervening args as the caption
        username = sys.argv[-1]
        caption = " ".join(sys.argv[3:-1])
    else:
        username = None
        caption = " ".join(sys.argv[3:])
    rc = main(profile_dir, video_path, caption, username)
    sys.exit(rc)
