from flask import Flask, render_template_string, redirect, url_for, request
import os, shutil, datetime, threading, json
ROOT = r'C:\projects\ai\content_bot'
STAGING = os.path.join(ROOT,'outbox','ai_lady','staging')
UPLOADED = os.path.join(ROOT,'outbox','ai_lady','uploaded')
FLAGGED = os.path.join(STAGING,'flagged')
LOG = os.path.join(ROOT,'logs','review_ui.log')
MODEL_PATH = os.path.join(ROOT,'models','classifier.pkl')
os.makedirs(STAGING, exist_ok=True)
os.makedirs(UPLOADED, exist_ok=True)
os.makedirs(FLAGGED, exist_ok=True)
app = Flask(__name__)
TEMPLATE = '''
<!doctype html><title>Review UI</title>
<h2>Staging items</h2>
<form method="post" action="/refresh"><button>Refresh Model</button></form>
<table border=1 cellpadding=6>
<tr><th>File</th><th>Age</th><th>Suggestion</th><th>Actions</th></tr>
{% for f,age,sugg in items %}
<tr><td>{{f}}</td><td>{{age}}</td><td>{{sugg}}</td>
<td>
<form style="display:inline" method="post" action="/approve"><input type="hidden" name="fn" value="{{f}}"><button>Approve</button></form>
<form style="display:inline" method="post" action="/flag"><input type="hidden" name="fn" value="{{f}}"><button>Flag</button></form>
</td></tr>
{% endfor %}
</table>
<hr>
<h3>Audit (last 50 lines)</h3>
<pre>{{audit}}</pre>
'''
_model = None
_vec = None
_clf = None
def load_model():
    global _model, _vec, _clf
    try:
        import joblib
        data = joblib.load(MODEL_PATH)
        _vec = data.get('vec') if isinstance(data, dict) else None
        _clf = data.get('clf') if isinstance(data, dict) else None
        _model = True if _clf and _vec else None
        return True
    except Exception:
        _model = None
        _vec = None
        _clf = None
        return False
def model_suggestion(fn):
    if not _model:
        return 'no-model'
    try:
        text = fn.replace('_',' ').replace('.',' ')
        Xv = _vec.transform([text])
        prob = float(_clf.predict_proba(Xv)[0][1])
        if prob >= 0.60:
            return f'approve ({prob:.2f})'
        if prob <= 0.40:
            return f'flag ({prob:.2f})'
        return f'review ({prob:.2f})'
    except Exception:
        return 'model-error'
def log_line(line):
    ts = datetime.datetime.utcnow().isoformat()
    with open(LOG,'a',encoding='utf-8') as L:
        L.write(line + ' ' + ts + '\\n')
def list_items():
    files = []
    for fn in sorted(os.listdir(STAGING)):
        path = os.path.join(STAGING,fn)
        if os.path.isdir(path): continue
        age = datetime.datetime.utcnow() - datetime.datetime.utcfromtimestamp(os.path.getmtime(path))
        sugg = model_suggestion(fn)
        files.append((fn, str(age).split('.')[0], sugg))
    return files
def read_audit():
    if not os.path.exists(LOG): return ''
    with open(LOG,'r',encoding='utf-8') as L:
        lines = L.readlines()[-50:]
    return ''.join(lines)
@app.route('/')
def index():
    return render_template_string(TEMPLATE, items=list_items(), audit=read_audit())
@app.route('/approve', methods=['POST'])
def approve():
    fn = request.form.get('fn','')
    src = os.path.join(STAGING,fn)
    if os.path.isfile(src):
        dst = os.path.join(UPLOADED,fn)
        shutil.move(src,dst)
        log_line(f"approved {fn}")
    return redirect(url_for('index'))
@app.route('/flag', methods=['POST'])
def flag():
    fn = request.form.get('fn','')
    src = os.path.join(STAGING,fn)
    if os.path.isfile(src):
        dst = os.path.join(FLAGGED,fn)
        shutil.move(src,dst)
        log_line(f"flagged {fn}")
    return redirect(url_for('index'))
@app.route('/refresh', methods=['POST'])
def refresh():
    ok = load_model()
    log_line('model_refresh ' + ('ok' if ok else 'failed'))
    return redirect(url_for('index'))
if __name__ == '__main__':
    load_model()
    def worker():
        import time
        THRESHOLD_HOURS = 24
        while True:
            try:
                now = datetime.datetime.utcnow()
                for fn in os.listdir(STAGING):
                    path = os.path.join(STAGING,fn)
                    if not os.path.isfile(path): continue
                    mtime = datetime.datetime.utcfromtimestamp(os.path.getmtime(path))
                    age_hours = (now - mtime).total_seconds()/3600.0
                    if age_hours >= THRESHOLD_HOURS:
                        dst = os.path.join(UPLOADED,fn)
                        shutil.move(path,dst)
                        log_line(f"auto_approved {fn} age_hours={age_hours:.1f}")
                time.sleep(300)
            except Exception as e:
                log_line('worker_error ' + str(e))
                time.sleep(60)
    t = threading.Thread(target=worker,daemon=True)
    t.start()
    app.run(host='127.0.0.1',port=5000)
