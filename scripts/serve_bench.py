"""Measure how many simultaneous role-play users a running service holds (run it against the real GPU job).

    python scripts/serve_bench.py --voice justiina2 --clip neutraali --users 3 --turns 6 --think-s 8

Reads the address and key like Rooliharjoittelu does (~/.f5-palvelu/osoite.json and avain, or --contract-dir/--url/--key).
Each simulated user speaks `--turns` short bursts (1-3 sentences) to POST /synthesize with `--think-s` seconds of
"thinking" between them, as a live conversation would. Prints the time until the audio is ready (what the user waits
for), how much of it was queueing, and how many requests the service turned away (503). Raise --users until the p95
time grows past what you accept (1.5-2 s is reasonable for a spoken reply); the number just below is how many
conversations the app should let in at once.
"""
import argparse
import json
import os
import random
import sys
import threading
import time

import httpx

SENTENCES = [
    "Hei, mukava tavata.", "Kerro vähän, mitä on tapahtunut.", "En oikein tiedä, mitä siihen sanoisi.",
    "Haluaisin kuulla, mitä sinä ajattelet asiasta.", "Se kuulostaa kyllä aika vaikealta.", "Otetaan tämä rauhassa.",
    "Voisitko selittää sen vielä kerran?", "Kiitos, että kerroit tämän minulle.", "Mitä me tästä eteenpäin tehtäisiin?",
]


def user(n, http, args, rows, lock):
    rnd = random.Random(n)
    time.sleep(rnd.uniform(0, args.think_s))  # users do not all start at the same moment
    for _ in range(args.turns):
        body = {"voice": args.voice, "clip": args.clip, "text": " ".join(rnd.choice(SENTENCES) for _ in range(rnd.randint(1, 3)))}
        t0 = time.monotonic()
        try:
            r = http.post("/synthesize", json=body)
            total = time.monotonic() - t0
            if r.status_code == 200:
                row = ("ok", total, float(r.headers["x-wait-s"]), 0)
            else:
                row = ("busy" if r.status_code == 503 else f"virhe {r.status_code}", total, 0, int(r.headers.get("retry-after", 0)))
                if r.status_code != 503:
                    print("  vastaus:", r.status_code, r.text[:150], file=sys.stderr)
        except httpx.HTTPError as e:
            row = (f"yhteysvirhe {type(e).__name__}", time.monotonic() - t0, 0, 0)
        with lock:
            rows.append(row)
        time.sleep(max(row[3], args.think_s * rnd.uniform(0.5, 1.5)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--contract-dir", default=os.path.expanduser("~/.f5-palvelu"))
    ap.add_argument("--url")
    ap.add_argument("--key")
    ap.add_argument("--voice", required=True)
    ap.add_argument("--clip", required=True)
    ap.add_argument("--users", type=int, default=2)
    ap.add_argument("--turns", type=int, default=5)
    ap.add_argument("--think-s", type=float, default=6.0)
    args = ap.parse_args()
    url, key = args.url, args.key
    if not url:
        with open(os.path.join(args.contract_dir, "osoite.json"), encoding="utf-8") as f:
            url = json.load(f)["url"]
    if not key:
        with open(os.path.join(args.contract_dir, "avain"), encoding="utf-8") as f:
            key = f.read().strip()
    http = httpx.Client(base_url=url, headers={"Authorization": f"Bearer {key}"}, timeout=60)
    print("palvelu:", http.get("/health").json())
    rows, lock = [], threading.Lock()
    threads = [threading.Thread(target=user, args=(i, http, args, rows, lock)) for i in range(args.users)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = [r for r in rows if r[0] == "ok"]
    other = {}
    for r in rows:
        if r[0] != "ok":
            other[r[0]] = other.get(r[0], 0) + 1
    print(f"{args.users} käyttäjää x {args.turns} vuoroa: {len(ok)} onnistui, muut: {other or 'ei yhtään'}")
    if ok:
        tot, wait = sorted(r[1] for r in ok), sorted(r[2] for r in ok)
        q = lambda a, f: a[min(len(a) - 1, int(f * len(a)))]  # noqa: E731
        print(f"äänen valmistumisaika s: p50 {q(tot, .5):.2f}  p95 {q(tot, .95):.2f}  max {tot[-1]:.2f}")
        print(f"  josta jonossa     s: p50 {q(wait, .5):.2f}  p95 {q(wait, .95):.2f}  max {wait[-1]:.2f}")


if __name__ == "__main__":
    main()
