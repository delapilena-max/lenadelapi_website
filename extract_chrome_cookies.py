import json
import os
import sqlite3
from pathlib import Path
import shutil

# Path to your real Chrome profile
CHROME_PROFILE = rf"C:\Users\{os.getlogin()}\AppData\Local\Google\Chrome\User Data\Default"

# Chrome's cookie DB
COOKIE_DB = Path(CHROME_PROFILE) / "Network" / "Cookies"

# Output file for Playwright
OUTPUT = Path("kling_state.json")

# Kling domain
DOMAIN = "kling.ai"


def extract():
    # Copy DB because Chrome locks it
    temp_db = Path("cookies_tmp.db")
    shutil.copy2(COOKIE_DB, temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT name, value, host_key, path, expires_utc, is_secure
        FROM cookies
        WHERE host_key LIKE ?
        """,
        (f"%{DOMAIN}%",),
    )

    cookies = []
    for name, value, host, path, expires, secure in cursor.fetchall():
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": host,
                "path": path,
                "expires": expires,
                "secure": bool(secure),
                "httpOnly": False,
                "sameSite": "Lax",
            }
        )

    conn.close()
    temp_db.unlink()

    state = {"cookies": cookies, "origins": []}
    OUTPUT.write_text(json.dumps(state, indent=2), encoding="utf-8")

    print(f"Saved Kling cookies to {OUTPUT.resolve()}")


if __name__ == "__main__":
    extract()
