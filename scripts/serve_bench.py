"""Measure how many simultaneous role-play sessions a running service holds (run it against the real GPU job).

    python scripts/serve_bench.py --state-dir ~/f5fi-tila --key-file ~/f5fi-tila/avaimet.json \
        --voice jooseppi --sessions 4 --turns 6 --think-s 5

Each simulated user opens a session, then speaks `--turns` short bursts (1-3 sentences) with `--think-s` seconds of
"thinking" between them, as a live conversation would. Prints, per run, the time until the audio is ready (what the
user waits for) and how much of it was queueing. Raise --sessions until the p95 time grows past what you accept
(1.5-2 s is a reasonable limit for a spoken reply); the number just below is the safe value for --max-sessions.
"""
import argparse
import json
import os
import random
import statistics
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f5client  # noqa: E402

SENTENCES = [
    "Hei, mukava tavata.", "Kerro vähän, mitä on tapahtunut.", "En oikein tiedä, mitä siihen sanoisi.",
    "Haluaisin kuulla, mitä sinä ajattelet asiasta.", "Se kuulostaa kyllä aika vaikealta.", "Otetaan tämä rauhassa.",
    "Voisitko selittää sen vielä kerran?", "Kiitos, että kerroit tämän minulle.", "Mitä me tästä eteenpäin tehtäisiin?",
]


def user(n, client, args, rows, lock):
    rnd = random.Random(n)
    try:
        s = client.session()
    except f5client.ServiceBusy as e:
        with lock:
            rows.append(("rejected", e.reason, 0, 0))
        return
    with s:
        for _ in range(args.turns):
            text = " ".join(rnd.choice(SENTENCES) for _ in range(rnd.randint(1, 3)))
            t0 = time.monotonic()
            try:
                _, info = s.speak(args.voice, text, args.emotion)
                total, wait = time.monotonic() - t0, float(info["wait_s"])
                with lock:
                    rows.append(("ok", info["sentences"], total, wait))
            except (f5client.ServiceBusy, f5client.ServiceDown) as e:
                with lock:
                    rows.append(("failed", str(e), time.monotonic() - t0, 0))
            time.sleep(args.think_s * rnd.uniform(0.5, 1.5))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url")
    ap.add_argument("--state-dir", help="luetaan current.json")
    ap.add_argument("--key-file", help='JSON {"interactive": ...}')
    ap.add_argument("--key")
    ap.add_argument("--voice", required=True)
    ap.add_argument("--emotion")
    ap.add_argument("--sessions", type=int, default=2)
    ap.add_argument("--turns", type=int, default=5)
    ap.add_argument("--think-s", type=float, default=5.0)
    args = ap.parse_args()
    url = args.url
    if not url:
        addr = f5client.read_address(os.path.join(args.state_dir, "current.json"))
        if addr is None:
            sys.exit("palvelua ei löydy (current.json puuttuu, on vanha tai ei ole ready-tilassa)")
        url = addr["url"]
    key = args.key
    if not key and args.key_file:
        with open(args.key_file, encoding="utf-8") as f:
            key = json.load(f)["interactive"]
    client = f5client.Client(url, key)
    rows, lock = [], threading.Lock()
    threads = [threading.Thread(target=user, args=(i, client, args, rows, lock)) for i in range(args.sessions)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = [r for r in rows if r[0] == "ok"]
    print(f"{args.sessions} istuntoa x {args.turns} vuoroa: {len(ok)} onnistui, "
          f"{sum(r[0] == 'rejected' for r in rows)} istuntoa hylättiin, {sum(r[0] == 'failed' for r in rows)} pyyntöä epäonnistui")
    if ok:
        tot, wait = sorted(r[2] for r in ok), sorted(r[3] for r in ok)
        q = lambda a, f: a[min(len(a) - 1, int(f * len(a)))]  # noqa: E731
        print(f"äänen valmistumisaika s: p50 {q(tot, .5):.2f}  p95 {q(tot, .95):.2f}  max {tot[-1]:.2f}  keskiarvo {statistics.mean(tot):.2f}")
        print(f"  josta jonossa     s: p50 {q(wait, .5):.2f}  p95 {q(wait, .95):.2f}  max {wait[-1]:.2f}")
    print("palvelimen tila:", json.dumps(client.status()["recent"]))


if __name__ == "__main__":
    main()
