import os,sys,json,datetime
cfg_path = os.path.join('config','ads_config.json')
ledger_path = os.path.join('billing','ads_spend.json')
# Load config
with open(cfg_path,'r',encoding='utf-8') as C:
    cfg = json.load(C)
monthly_cap = float(cfg.get('monthly_cap_usd',0))
dry_run = bool(cfg.get('dry_run',True))
# Ensure ledger exists
if not os.path.exists(ledger_path):
    with open(ledger_path,'w',encoding='utf-8') as L:
        json.dump({}, L)
with open(ledger_path,'r',encoding='utf-8') as L:
    ledger = json.load(L)
def month_key(dt=None):
    dt = dt or datetime.datetime.utcnow()
    return dt.strftime('%Y-%m')
def current_spend():
    return float(ledger.get(month_key(), 0))
def can_spend(amount):
    if monthly_cap <= 0:
        return True, 'no_cap_set'
    return (current_spend() + amount) <= monthly_cap, 'cap_exceeded' if (current_spend() + amount) > monthly_cap else 'ok'
def record_spend(amount):
    k = month_key()
    ledger[k] = float(ledger.get(k,0)) + amount
    with open(ledger_path,'w',encoding='utf-8') as L:
        json.dump(ledger, L)
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python ads_guard.py check|spend <amount>")
        sys.exit(2)
    cmd = sys.argv[1]
    try:
        amt = float(sys.argv[2])
    except:
        print("invalid_amount")
        sys.exit(2)
    ok, reason = can_spend(amt)
    if cmd == "check":
        print(json.dumps({"ok": ok, "reason": reason, "current_month_spend": current_spend(), "monthly_cap": monthly_cap, "dry_run": dry_run}))
        sys.exit(0 if ok else 1)
    elif cmd == "spend":
        if not ok:
            print(json.dumps({"ok": False, "reason": reason, "current_month_spend": current_spend(), "monthly_cap": monthly_cap}))
            sys.exit(1)
        if dry_run:
            print(json.dumps({"ok": True, "dry_run": True, "would_record": amt, "current_month_spend": current_spend(), "monthly_cap": monthly_cap}))
            sys.exit(0)
        record_spend(amt)
        print(json.dumps({"ok": True, "recorded": amt, "new_month_spend": current_spend()}))
        sys.exit(0)
else:
    pass
