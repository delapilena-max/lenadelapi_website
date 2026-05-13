# train_classifier.py - simple scaffold: train a filename-based classifier from review_labels.json
import os, json, datetime
from pathlib import Path
ROOT = Path(r'C:\projects\ai\content_bot')
INPATH = ROOT / 'logs' / 'review_labels.json'
OUTMODEL = ROOT / 'models' / 'classifier.pkl'
LOG = ROOT / 'logs' / 'train_classifier.log'
def log(msg):
    with open(LOG,'a',encoding='utf-8') as L:
        L.write(datetime.datetime.utcnow().isoformat() + ' ' + msg + '\\n')
try:
    if not INPATH.exists():
        log('NO_LABELS_FILE')
        print('NO_LABELS_FILE'); raise SystemExit(0)
    with open(INPATH,'r',encoding='utf-8') as F:
        data = json.load(F)
    # simple feature: filename tokens; label: approved vs flagged
    X = []
    y = []
    for e in data:
        fn = e.get('file','')
        action = e.get('action','').lower()
        label = 1 if 'approve' in action else 0
        tokens = fn.replace('_',' ').replace('.',' ').split()
        X.append(' '.join(tokens))
        y.append(label)
    if len(X) < 4:
        log('NOT_ENOUGH_LABELS ' + str(len(X)))
        print('NOT_ENOUGH_LABELS'); raise SystemExit(0)
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    import joblib
    vec = TfidfVectorizer(ngram_range=(1,2), max_features=500)
    Xv = vec.fit_transform(X)
    Xtr, Xte, ytr, yte = train_test_split(Xv, y, test_size=0.2, random_state=42)
    clf = LogisticRegression(max_iter=200)
    clf.fit(Xtr, ytr)
    score = clf.score(Xte, yte)
    joblib.dump({'vec':vec,'clf':clf}, OUTMODEL)
    log(f'TRAINED model saved {OUTMODEL} score={score:.3f}')
    print('TRAINED', score)
except Exception as e:
    log('TRAIN_ERROR ' + str(e))
    raise
