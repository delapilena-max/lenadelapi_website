import os,sys,time,json,requests,datetime
ROOT = r'C:\projects\ai\content_bot'
LOG = os.path.join(ROOT,'logs','monitor.log')
REVIEW_LOG = os.path.join(ROOT,'logs','review_ui.log')
WEBHOOK = os.environ.get('MONITOR_WEBHOOK','').strip()
def tail(fpath, pos=0):
    with open(fpath,'r',encoding='utf-8',errors=\"ignore\") as f:
        f.seek(pos)
        data = f.read()
        return data, f.tell()
def notify(line):
    ts = datetime.datetime.utcnow().isoformat()
    payload = {'ts':ts,'line':line}
    if WEBHOOK:
        try:
            requests.post(WEBHOOK, json=payload, timeout=6)
        except Exception as e:
            with open(LOG,'a',encoding='utf-8') as L:
                L.write(f\"{ts} webhook_error {e}\\n\")
    else:
        with open(LOG,'a',encoding='utf-8') as L:
            L.write(f\"{ts} {line}\\n\")
if __name__ == '__main__':
    if not os.path.exists(REVIEW_LOG):
        open(REVIEW_LOG,'a').close()
    pos = 0
    while True:
        try:
            data, pos = tail(REVIEW_LOG, pos)
            if data:
                for line in data.strip().splitlines():
                    if 'flagged' in line or 'auto_approved' in line or 'approved' in line:
                        notify(line)
            time.sleep(10)
        except Exception as e:
            with open(LOG,'a',encoding='utf-8') as L:
                L.write(datetime.datetime.utcnow().isoformat() + ' monitor_error ' + str(e) + '\\n')
            time.sleep(30)
