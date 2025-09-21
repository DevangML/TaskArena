#!/usr/bin/env python3
import json, time
from util import ROOT, SCORE_FILE

DONE = ROOT/"queue/done"
FAILED = ROOT/"queue/failed"

def load_score():
    try: return json.loads(SCORE_FILE.read_text())
    except: return {"pass":0,"fail":0}

def save_score(s):
    SCORE_FILE.write_text(json.dumps(s, indent=2))

if __name__=="__main__":
    s = load_score()
    while True:
        for p in list(DONE.glob("*.json")):
            s["pass"] += 1; p.unlink(missing_ok=True)
        for p in list(FAILED.glob("*.json")):
            s["fail"] += 1; p.unlink(missing_ok=True)
        save_score(s); time.sleep(1)
