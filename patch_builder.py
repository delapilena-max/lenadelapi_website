# patch_builder.py — overwrite previous version, save in C:\projects\ai\content_bot\
import pathlib

path = pathlib.Path("face_cache_builder.py")
src  = path.read_text(encoding="utf-8")
original = src

# ── Patch 3: fix add_cookies — remove path+secure (url-only is required) ───
OLD3 = '''        cookies.append({"name":"ksi18n.ai.portal_st","value":KLING_COOKIE,"url":"https://kling.ai","path":"/","secure":True})
    if KLING_COOKIE_PH:
        cookies.append({"name":"ksi18n.ai.portal_ph","value":KLING_COOKIE_PH,"url":"https://kling.ai","path":"/","secure":True})
    if KLING_USERID:
        cookies.append({"name":"userId","value":KLING_USERID,"url":"https://kling.ai","path":"/","secure":True})
    if KLING_TEAMID:
        cookies.append({"name":"teamId","value":KLING_TEAMID,"url":"https://kling.ai","path":"/","secure":True})'''

NEW3 = '''        cookies.append({"name":"ksi18n.ai.portal_st","value":KLING_COOKIE,"url":"https://kling.ai"})
    if KLING_COOKIE_PH:
        cookies.append({"name":"ksi18n.ai.portal_ph","value":KLING_COOKIE_PH,"url":"https://kling.ai"})
    if KLING_USERID:
        cookies.append({"name":"userId","value":KLING_USERID,"url":"https://kling.ai"})
    if KLING_TEAMID:
        cookies.append({"name":"teamId","value":KLING_TEAMID,"url":"https://kling.ai"})'''

# ── Patch 4: fix hidden el-upload file input ────────────────────────────────
# el-upload always sets display:none on input[type=file]; default state='visible'
# causes wait_for_selector to spin forever. Use state='attached' + JS unhide.
OLD4 = '''    # Attach file
    input_handle = await page.wait_for_selector('input[type="file"]', timeout=10000)
    await input_handle.set_input_files(str(image_path))'''

NEW4 = '''    # Attach file — el-upload hides input[type=file] with display:none
    # Use state='attached' (not 'visible'), then unhide via JS before set_input_files
    await page.wait_for_selector('input[type="file"]', state='attached', timeout=10000)
    await page.evaluate(
        "() => { const el = document.querySelector('input[type=\"file\"]'); "
        "if (el) { el.style.display = 'block'; el.style.opacity = '1'; } }"
    )
    await page.locator('input[type="file"]').set_input_files(str(image_path))'''

# ── Apply ───────────────────────────────────────────────────────────────────
results = []
for label, old, new in [("Patch 3 (add_cookies url-only)", OLD3, NEW3),
                         ("Patch 4 (hidden file input)",    OLD4, NEW4)]:
    if old in src:
        src = src.replace(old, new, 1)
        results.append(f"  ✓ {label}")
    else:
        results.append(f"  ✗ {label} — target not found (may already be applied)")

if src != original:
    path.write_text(src, encoding="utf-8")
    print("face_cache_builder.py updated:")
else:
    print("No changes written (all targets already patched):")

for r in results:
    print(r)
