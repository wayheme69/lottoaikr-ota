#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kr_results.py — flux de la v5 de LOTTO AI KR : kr_results.json (08/10/2026)

  lotto : 30 derniers tirages 로또 6/45 (6 numéros + bonus) + vrai gain par gagnant pour chaque rang
          (« 6 » = 1등, « 5+B » = 2등, « 5 » = 3등, « 4 » = 4등, « 3 » = 5등) et nombre de gagnants.
  next  : date du prochain tirage (samedi suivant le dernier tirage connu, heure de Séoul).

Source OFFICIELLE : 동행복권 https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do
  srchDir=latest&srchCursorLtEpsd=N → tirages > N (le plus récent d'abord) ;
  srchDir=older&srchCursorLtEpsd=N  → les 10 tirages < N.
Recoupement : miroir public smok95.github.io/lotto/results/all.json — numéros, bonus et gains des
tirages présents dans les deux doivent être identiques (sinon échec bruyant).
Local (DNS détourné) : KR_RESOLVE="www.dhlottery.co.kr:443:IP".
"""
import json, os, subprocess, sys, time
from datetime import date, datetime, timedelta, timezone

FEED = "kr_results.json"
KEEP = 30
MAX_STALE_DAYS = 9
API = "https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do"
MIRROR = "https://smok95.github.io/lotto/results/all.json"
KEYS = ["6", "5+B", "5", "4", "3"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def curl(url, timeout=60):
    extra = []
    for r in filter(None, os.environ.get("KR_RESOLVE", "").split(",")):
        extra += ["--resolve", r]
    r = subprocess.run(["curl", "-sL", "--max-time", str(timeout), "-A", UA] + extra + [url],
                       capture_output=True, text=True, timeout=timeout + 30)
    return r.stdout if r.returncode == 0 else ""


def api(direction, cursor):
    for i in range(4):
        try:
            return json.loads(curl(f"{API}?srchDir={direction}&srchCursorLtEpsd={cursor}"))["data"]["list"]
        except Exception:
            print(f"  API essai {i + 1} KO ({direction} {cursor})", file=sys.stderr); time.sleep(8 * (i + 1))
    raise SystemExit("API dhlottery injoignable")


def row(x):
    d = x["ltRflYmd"]; iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    nums = sorted(int(x[f"tm{i}WnNo"]) for i in range(1, 7)); b = int(x["bnsWnNo"])
    if len(set(nums)) != 6 or not all(1 <= n <= 45 for n in nums) or not 1 <= b <= 45 or b in nums:
        raise SystemExit(f"{iso}: valeurs invalides {nums} + {b}")
    pay, win = {}, {}
    for k, key in enumerate(KEYS, 1):
        win[key] = int(x.get(f"rnk{k}WnNope") or 0)
        amt = int(x.get(f"rnk{k}WnAmt") or 0)
        if amt > 0 and win[key] > 0:
            pay[key] = amt
    return {"date": iso, "draw": int(x["ltEpsd"]), "numbers": nums, "bonus": b, "payouts": pay, "winners": win}


def main():
    prev = {}
    if os.path.exists(FEED):
        try:
            prev = json.load(open(FEED))
        except Exception as e:
            print("flux existant illisible:", e, file=sys.stderr)
    # n° estimé : 1회 = 07/12/2002, un tirage par semaine
    est = 1 + (date.today() - date(2002, 12, 7)).days // 7
    rows = {}
    cur = est - 12
    for _ in range(20):   # « latest » renvoie au plus 10 tirages au-dessus du curseur : on remonte jusqu'au bout
        got = api("latest", cur)
        for x in got:
            r = row(x); rows[r["draw"]] = r
        if len(got) < 10:
            break
        cur = max(rows); time.sleep(1)
    if not rows:
        raise SystemExit("API : aucun tirage récent")
    while len(rows) < KEEP:
        got = api("older", min(rows))
        if not got:
            break
        for x in got:
            r = row(x); rows[r["draw"]] = r
        time.sleep(1)
    lst = sorted(rows.values(), key=lambda r: r["draw"], reverse=True)[:KEEP]
    # Recoupement avec le miroir
    m = json.loads(curl(MIRROR, 120) or "[]")
    mm = {x["draw_no"]: x for x in m}
    checked = 0
    for r in lst:
        x = mm.get(r["draw"])
        if not x:
            continue
        mp = {KEYS[i]: d["prize"] for i, d in enumerate(x["divisions"][:5]) if d["prize"] > 0 and d["winners"] > 0}
        if sorted(x["numbers"]) != r["numbers"] or x["bonus_no"] != r["bonus"] or mp != r["payouts"]:
            raise SystemExit(f"{r['draw']}회 : officiel ≠ miroir\n{r}\n{x}")
        checked += 1
    age = (date.today() - date.fromisoformat(lst[0]["date"])).days
    nd = date.fromisoformat(lst[0]["date"]) + timedelta(days=7)
    print(f"lotto: {len(lst)} tirages, dernier {lst[0]['draw']}회 {lst[0]['date']} ({age} j), {checked} recoupés miroir, prochain {nd}", file=sys.stderr)
    if age > MAX_STALE_DAYS or len(lst) < 10:
        raise SystemExit("FAIL: flux périmé ou trop court")
    new = {"lotto": lst, "next": {"lotto": nd.isoformat()}}
    if new == {k: prev.get(k) for k in new}:
        print("Aucune nouvelle donnée.", file=sys.stderr); return
    json.dump({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), **new},
              open(FEED, "w"), ensure_ascii=False, indent=1)
    print("OK", file=sys.stderr)


if __name__ == "__main__":
    main()
