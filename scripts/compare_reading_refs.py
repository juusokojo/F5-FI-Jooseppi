"""Read the same passage with every reference clip given and build a local listening page.

    .venv/bin/python scripts/compare_reading_refs.py data/viite/v3/*.wav data/viite/v2-wav/viite_kerronta_1.wav \
        --text data/raw/aineisto/lukeminen_1.txt --paragraphs 2 --out data/vertailu/<kansio>

This is the reference test of docs/nauhoitusohje.md (vaihe A2): which reading style carries over best to a long
text. The passage is split and read as read_text.py does (one sentence per generation, 0.3 s between sentences,
0.7 s between paragraphs), through f5fi.py with all its fixes. The model is loaded once. A reference whose reading
already exists in --out is skipped, so an interrupted run continues where it stopped. Each clip <name>.wav needs
its words in <name>.txt. The page <out>/index.html is a local file: open it in a browser, do not publish it.
"""
import argparse
import html
import json
import os
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f5fi  # noqa: E402
import read_text  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("refs", nargs="+", help="reference clips (.wav with a .txt beside)")
    ap.add_argument("--text", required=True)
    ap.add_argument("--paragraphs", type=int, default=2, help="first N paragraphs, the title counts as one")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", help="model checkpoint; default: the recommended fine-tuned model (f5fi.FINETUNED_CKPT), base = the base model")
    ap.add_argument("--candidates", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    args.ckpt = f5fi.resolve_ckpt(args.ckpt)
    os.makedirs(args.out, exist_ok=True)

    with open(args.text, encoding="utf-8") as f:
        paras = read_text.paragraphs(f.read())[: args.paragraphs]
    plan = [(p_i, s) for p_i, p in enumerate(paras) for s in read_text.sentences(p)]

    results_path = os.path.join(args.out, "results.json")
    done = {}
    if os.path.exists(results_path):
        done = {r["name"]: r for r in json.load(open(results_path, encoding="utf-8"))["results"]}

    tts = None
    results = []
    for ref in args.refs:
        name = os.path.splitext(os.path.basename(ref))[0]
        out_wav = os.path.join(args.out, name + ".wav")
        if name in done and os.path.exists(out_wav):
            results.append(done[name])
            continue
        if tts is None:
            tts = f5fi.load_model(args.ckpt)
        with open(ref[:-4] + ".txt", encoding="utf-8") as f:
            ref_text = f.read().strip()
        t0 = time.monotonic()
        pieces, sr, prev = [], None, None
        tmp = os.path.join(args.out, ".tmp.wav")
        for p_i, sent in plan:
            res = f5fi.synthesize(tts, ref, ref_text, sent, tmp, seed=args.seed, candidates=args.candidates)
            wave, sr = sf.read(tmp, dtype="float32")
            if prev is not None:
                pieces.append(np.zeros(int((read_text.PARAGRAPH_PAUSE_S if p_i != prev else
                                            read_text.SENTENCE_PAUSE_S) * sr), np.float32))
            prev = p_i
            pieces.append(wave)
        os.remove(tmp)
        audio = np.concatenate(pieces)
        sf.write(out_wav, audio, sr)
        row = {"name": name, "ref": os.path.relpath(ref, args.out), "ref_text": ref_text,
               "ref_s": round(sf.info(ref).duration, 1), "out": os.path.basename(out_wav),
               "length_s": round(len(audio) / sr, 1), "compute_s": round(time.monotonic() - t0)}
        results.append(row)
        print(f"{name}: {row['length_s']} s ääntä, {row['compute_s']} s laskentaa", flush=True)
        save(args, paras, results)
    save(args, paras, results)


def save(args, paras, results):
    with open(os.path.join(args.out, "results.json"), "w", encoding="utf-8") as f:
        json.dump({"text": os.path.relpath(args.text, f5fi.ROOT), "paragraphs": args.paragraphs,
                   "ckpt": os.path.relpath(args.ckpt, f5fi.ROOT), "candidates": args.candidates, "seed": args.seed,
                   "results": results}, f, ensure_ascii=False, indent=1)
    rows = []
    for r in results:
        rows.append(f'<tr><th>{html.escape(r["name"])}</th>'
                    f'<td><audio controls preload="none" src="{html.escape(r["ref"])}"></audio>'
                    f'<div class=t>{html.escape(r["ref_text"])}</div></td>'
                    f'<td><audio controls preload="none" src="{html.escape(r["out"])}"></audio>'
                    f'<div class=t>{r["length_s"]} s</div></td></tr>')
    text_html = "".join(f"<p>{html.escape(p)}</p>" for p in paras)
    page = f"""<!doctype html><html lang="fi"><head><meta charset="utf-8"><title>Viitteet ja lukutapa</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;margin:24px;max-width:60em;background:#fff;color:#222}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:8px;vertical-align:top;text-align:left}}
audio{{width:100%;min-width:220px}}.t{{color:#666;font-size:13px}}</style></head><body>
<h1>Viitteet ja lukutapa</h1>
<p>Jokaisella viitteellä on luettu sama katkelma. Otto 1 = hillitysti, 2 = eläytyen, 3 = vähän liioitellen.
Vertailukohtana on aiempi suositusviite viite_kerronta_1. Malli: F5:n suomenkielinen perusmalli,
{args.candidates} otto(a) lausetta kohden.</p>
<table><tr><th>Viite</th><th>Viitenäyte</th><th>Luettu katkelma</th></tr>{''.join(rows)}</table>
<h2>Teksti</h2>{text_html}
<h2>Mitä kannattaa kuunnella</h2><ul><li>Kuulostaako luenta eloisalta mutta luontevalta?</li>
<li>Siirtyykö viitteen tunnelma (haikeus, jännite, innostus) tekstiin, jossa sitä ei ole?</li>
<li>Pysyykö ääni puhtaana ja tempo rauhallisena?</li></ul></body></html>"""
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


if __name__ == "__main__":
    main()
