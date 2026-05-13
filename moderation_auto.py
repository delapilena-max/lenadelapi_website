import os,shutil,re,sys
root = r'C:\projects\ai\content_bot'
staging = os.path.join(root,'outbox','ai_lady','staging')
uploaded = os.path.join(root,'outbox','ai_lady','uploaded')
log = os.path.join(root,'logs','bot_current.log')
banned_patterns = [r'\b(?:sex|porn|hate|terror|bomb|kill)\b', r'http[s]?://\S+']  # simple, conservative filters
compiled = [re.compile(p, re.I) for p in banned_patterns]
os.makedirs(uploaded, exist_ok=True)
for fn in sorted(os.listdir(staging)):
    src = os.path.join(staging, fn)
    if not os.path.isfile(src): continue
    with open(src, 'r', encoding='utf-8', errors='ignore') as f:
        txt = f.read()
    flagged = any(p.search(txt) for p in compiled)
    if flagged:
        with open(log, 'a', encoding='utf-8') as L:
            L.write(f'flagged {fn} {__import__("datetime").datetime.utcnow().isoformat()}\\n')
        print('flagged', fn)
    else:
        dst = os.path.join(uploaded, fn)
        shutil.move(src, dst)
        with open(log, 'a', encoding='utf-8') as L:
            L.write(f'auto_approved_and_moved {fn} {__import__("datetime").datetime.utcnow().isoformat()}\\n')
        print('approved', fn)
