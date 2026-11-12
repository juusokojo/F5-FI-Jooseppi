"""Synthesize listed variants with one model load and build a local listening page.

    .venv/bin/python scripts/variants.py variants.tsv --ref data/viite/v3/viite_selitys_2.wav --out data/vertailu/<folder>

variants.tsv has one variant per line: name<TAB>text<TAB>options, where options are space-separated key=value
pairs for f5fi.synthesize (nfe, speed, seed, tail_s, normalize, candidates) and ref_pad_ms. Empty options = defaults.
"""
import argparse
import html
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f5fi


def parse_opts(s):
    opts = {}
    for kv in s.split():
        k, v = kv.split("=")
        opts[k] = v.lower() == "true" if v.lower() in ("true", "false") else (float(v) if "." in v else int(v))
    return opts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("variants")
    ap.add_argument("--ref", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.splitext(args.ref)[0] + ".txt", encoding="utf-8") as f:
        ref_text = f.read().strip()

    rows = []
    for line in open(args.variants, encoding="utf-8"):
        if line.strip() and not line.startswith("#"):
            name, text, *rest = line.rstrip("\n").split("\t")
            rows.append((name, text, rest[0] if rest else ""))

    tts = f5fi.load_model()
    done = []
    for name, text, opt_s in rows:
        opts = parse_opts(opt_s)
        f5fi._ref_pad_ms = opts.pop("ref_pad_ms", f5fi.REF_PAD_MS)
        path = os.path.join(args.out, name + ".wav")
        t0 = time.monotonic()
        res = f5fi.synthesize(tts, args.ref, ref_text, text, path, **opts)
        print(f"{name}: {time.monotonic() - t0:.1f} s  mallille: {res.text}", flush=True)
        for seed, sc, heard in res.takes:
            print(f"  {'*' if seed == res.seed else ' '} siemen {seed}: {sc:.0%}  Whisper: {heard}", flush=True)
        info = opt_s or "oletukset"
        if res.takes:
            info += f" (valittu siemen {res.seed}/{len(res.takes)})"
        done.append((name, text, res.text, info))

    tr = "".join(f'<tr><td>{html.escape(n)}</td><td>{html.escape(t)}</td><td>{html.escape(o)}</td>'
                 f'<td><audio controls src="{html.escape(n)}.wav"></audio></td></tr>' for n, t, s, o in done)
    page = f"""<!doctype html><html lang="fi"><head><meta charset="utf-8"><title>Muunnelmat</title>
<style>body{{font:15px system-ui;margin:24px;background:#fff;color:#222}}td{{border:1px solid #ccc;padding:8px}}
table{{border-collapse:collapse}}</style></head><body><h1>Muunnelmat</h1>
<p>Viitenäyte {html.escape(os.path.basename(args.ref))}</p><table>{tr}</table></body></html>"""
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


if __name__ == "__main__":
    main()
