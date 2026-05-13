import os,sys,json
from mastodon_adapter import post_status
pub = os.path.join(os.path.dirname(os.path.dirname(__file__)),"outbox","ai_lady","published")
if not os.path.isdir(pub):
    print("no_published_files")
    sys.exit(0)
files = sorted([f for f in os.listdir(pub) if os.path.isfile(os.path.join(pub,f))])
if not files:
    print("no_published_files")
    sys.exit(0)
fn = files[0]
with open(os.path.join(pub,fn),'r',encoding='utf-8',errors='ignore') as F:
    body = F.read().strip()
text = (body[:500] + "...") if len(body)>500 else body
try:
    res = post_status(text)
    print(json.dumps(res, ensure_ascii=False))
except Exception as e:
    print("publish_error", str(e))
