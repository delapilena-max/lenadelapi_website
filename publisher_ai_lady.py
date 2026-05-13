import os,requests,shutil,subprocess,json
root = r'C:\projects\ai\content_bot'
uploaded = os.path.join(root,'outbox','ai_lady','uploaded')
published = os.path.join(root,'outbox','ai_lady','published')
log = os.path.join(root,'logs','bot_publisher.log')
os.makedirs(published, exist_ok=True)
WEBHOOK = os.environ.get('AI_LADY_WEBHOOK','').strip()
# AD_SPEND_AMOUNT controls paid amplification per-file (0 or unset = no ad call)
try:
    AD_SPEND_AMOUNT = float(os.environ.get('AD_SPEND_AMOUNT','0') or 0)
except:
    AD_SPEND_AMOUNT = 0.0
def log_line(line):
    ts = __import__('datetime').datetime.utcnow().isoformat()
    with open(log,'a',encoding='utf-8') as L:
        L.write(line + ' ' + ts + '\n')
for fn in sorted(os.listdir(uploaded)):
    src = os.path.join(uploaded, fn)
    if not os.path.isfile(src): continue
    with open(src,'r',encoding='utf-8',errors='ignore') as f:
        body = f.read()
    try:
        # If an ad spend is requested, check the guard first
        if AD_SPEND_AMOUNT > 0:
            try:
                chk = subprocess.run([os.path.join(root,'.venv','Scripts','python.exe'), os.path.join(root,'ads_guard.py'), 'check', str(AD_SPEND_AMOUNT)], capture_output=True, text=True, timeout=20)
                if chk.returncode != 0:
                    # parse output if possible
                    reason = chk.stdout.strip() or chk.stderr.strip() or 'ads_guard_rejected'
                    log_line('publish_failed_ad_blocked ' + fn + ' ' + reason)
                    print('publish_failed_ad_blocked', fn, reason)
                    continue
                # parse JSON to see dry_run flag
                try:
                    info = json.loads(chk.stdout.strip())
                except:
                    info = {}
            except Exception as e:
                log_line('publish_failed_ad_check_error ' + fn + ' ' + str(e))
                print('publish_failed_ad_check_error', fn, str(e))
                continue
        # perform publish action
        if WEBHOOK:
            resp = requests.post(WEBHOOK, json={'filename':fn,'content':body}, timeout=15)
            resp.raise_for_status()
            action = 'webhook_posted'
        else:
            dst = os.path.join(published, fn)
            shutil.move(src, dst)
            action = 'moved_to_published'
        log_line(action + ' ' + fn)
        print(action, fn)
        # If ad spend was requested and guard reported dry_run==False, record spend
        if AD_SPEND_AMOUNT > 0:
            dry_run = info.get('dry_run', True)
            if not dry_run:
                try:
                    spend = subprocess.run([os.path.join(root,'.venv','Scripts','python.exe'), os.path.join(root,'ads_guard.py'), 'spend', str(AD_SPEND_AMOUNT)], capture_output=True, text=True, timeout=20)
                    if spend.returncode != 0:
                        log_line('publish_failed_ad_record ' + fn + ' ' + (spend.stdout.strip() or spend.stderr.strip()))
                        print('publish_failed_ad_record', fn, spend.stdout.strip() or spend.stderr.strip())
                except Exception as e:
                    log_line('publish_failed_ad_record_error ' + fn + ' ' + str(e))
                    print('publish_failed_ad_record_error', fn, str(e))
    except Exception as e:
        log_line('publish_failed ' + fn + ' ' + str(e))
        print('publish_failed', fn, str(e))
