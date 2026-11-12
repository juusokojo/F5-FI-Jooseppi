"""Synthesize the same test lines with every reference clip in a folder and build a local listening page.

    .venv/bin/python scripts/compare_refs.py data/viite --out data/vertailu/<folder>

Each clip <name>.wav needs its words in <name>.txt. The page <out>/index.html plays each reference next to the
lines generated from it. It is a local file: open it in a browser, do not publish it. Synthesis goes through f5fi.py (normalization, fixes).
"""
import argparse
import glob
import html
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f5fi

LINES = [
    "Hyvää huomenta. Tämän päivän ohjelmassa on kolme lyhyttä esitystä ja yhteinen keskustelu.",
    "Mä en ihan tajunnu, mitä sä tarkotit. Voisitko selittää sen vielä kerran?",
    "Kun aloitin tämän projektin, en uskonut, että siitä tulisi näin laaja.",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("refs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", help="model checkpoint; default: the recommended fine-tuned model (f5fi.FINETUNED_CKPT), base = the base model")
    ap.add_argument("--nfe", type=int, default=f5fi.NFE)
    ap.add_argument("--candidates", type=int, default=1, help="takes per line; Whisper keeps the closest")
    args = ap.parse_args()
    args.ckpt = f5fi.resolve_ckpt(args.ckpt)
    os.makedirs(args.out, exist_ok=True)

    tts = f5fi.load_model(args.ckpt)

    refs = sorted(glob.glob(os.path.join(args.refs, "*.wav")))
    results = []
    for ref in refs:
        name = os.path.splitext(os.path.basename(ref))[0]
        with open(ref[:-4] + ".txt", encoding="utf-8") as f:
            ref_text = f.read().strip()
        row = {"name": name, "ref": os.path.relpath(ref, args.out), "ref_text": ref_text, "out": []}
        for i, text in enumerate(LINES, 1):
            path = os.path.join(args.out, f"{name}_{i}.wav")
            t0 = time.monotonic()
            f5fi.synthesize(tts, ref, ref_text, text, path, nfe=args.nfe, candidates=args.candidates)
            print(f"{name} {i}: {time.monotonic() - t0:.1f} s", flush=True)
            row["out"].append(os.path.basename(path))
        results.append(row)

    with open(os.path.join(args.out, "results.json"), "w", encoding="utf-8") as f:
        json.dump({"lines": LINES, "ckpt": args.ckpt, "nfe": args.nfe, "results": results}, f, ensure_ascii=False, indent=1)
    write_page(args.out, results)


def write_page(out, results):
    head = "".join(f"<th>{i}. {html.escape(t)}</th>" for i, t in enumerate(LINES, 1))
    rows = []
    for r in results:
        cells = "".join(f'<td><audio controls preload="none" src="{html.escape(o)}"></audio></td>' for o in r["out"])
        rows.append(f'<tr><th>{html.escape(r["name"])}<br><audio controls preload="none" src="{html.escape(r["ref"])}">'
                    f'</audio></th>{cells}</tr>')
    page = f"""<!doctype html><html lang="fi"><head><meta charset="utf-8"><title>Viitenäytevertailu</title>
<style>body{{font:15px system-ui;margin:24px;background:#fff;color:#222}}table{{border-collapse:collapse}}
th,td{{border:1px solid #ccc;padding:8px;vertical-align:top;text-align:left}}thead th{{max-width:280px;font-weight:600}}
tbody th{{font-weight:600}}audio{{width:240px}}</style></head><body>
<h1>Viitenäytevertailu</h1><p>Vasemmalla sinun viitenäytteesi, oikealla samat testilauseet sen äänellä tuotettuna.</p>
<table><thead><tr><th>Viitenäyte</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"""
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


if __name__ == "__main__":
    main()
