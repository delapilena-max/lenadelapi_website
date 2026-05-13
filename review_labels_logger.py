import os,sys,json,datetime,shutil
ROOT = r'C:\projects\ai\content_bot'
REVIEW_LOG = os.path.join(ROOT,'logs','review_ui.log')
OUT = os.path.join(ROOT,'logs','review_labels.json')
def append_label(entry):
    data = []
    if os.path.exists(OUT):
        try:
            with open(OUT,'r',encoding='utf-8') as F:
                data = json.load(F)
        except:
            data = []
    data.append(entry)
    with open(OUT,'w',encoding='utf-8') as F:
        json.dump(data, F, indent=2)
def tail_and_extract(pos=0):
    if not os.path.exists(REVIEW_LOG):
        open(REVIEW_LOG,'a').close()
    with open(REVIEW_LOG,'r',encoding='utf-8',errors='ignore') as F:
        F.seek(pos)
        lines = F.read()
        return lines, F.tell()
if __name__ == '__main__':
    pos = 0
    while True:
        try:
            lines, pos = tail_and_extract(pos)
            if lines:
                for L in lines.strip().splitlines():
                    if 'approved ' in L or 'flagged ' in L or 'auto_approved ' in L:
                        ts,rest = L.split(' ',1)
                        parts = rest.split()
                        action = parts[1] if len(parts)>1 else 'unknown'
                        fn = parts[0] if parts else 'unknown'
                        entry = {'ts':ts,'action':action,'file':fn}
                        append_label(entry)
            time.sleep(8)
        except Exception as e:
            with open(os.path.join(ROOT,'logs','review_labels_logger_error.log'),'a',encoding='utf-8') as E:
                E.write(datetime.datetime.utcnow().isoformat() + ' ' + str(e) + '\\n')
            time.sleep(20)
