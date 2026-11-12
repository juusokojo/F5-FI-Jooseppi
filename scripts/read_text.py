"""Read a longer text aloud: one sentence per generation, joined with short pauses into one wav.

    .venv/bin/python scripts/read_text.py data/raw/aineisto/lukeminen_1.txt \
        --until-s 60 --out data/vertailu/<kansio>

F5's fixes in f5fi.py (text normalization, reference pause, extra time) are tuned for single lines, so the text is
split into sentences and each is synthesized on its own. Dialogue dashes are dropped. --until-s stops at the end of
the paragraph during which the reading passes that length; --paragraphs N reads exactly the first N paragraphs, which
is how a later model reads the same passage for comparison. The run is written to <out>/lukeminen.wav, its text and
settings to <out>/asetukset.json, and per-sentence takes to <out>/lauseet/.
"""
import argparse
import html
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f5fi

import numpy as np
import soundfile as sf

SENTENCE_PAUSE_S = 0.3
PARAGRAPH_PAUSE_S = 0.7
# split after . ! ? when the next sentence starts with a capital (possibly after a dialogue dash); "No? hän kysyi."
# stays together
SPLIT = re.compile(r"(?<=[.!?])\s+(?=(?:–\s+)?[A-ZÅÄÖ])")


def paragraphs(text):
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]


def sentences(paragraph):
    out = []
    for s in SPLIT.split(paragraph):
        s = re.sub(r"^–\s+", "", s).strip()
        if s:
            out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--ref", default=f5fi.DEFAULT_REF, help="default: f5fi.DEFAULT_REF")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", help="model checkpoint; default: the recommended fine-tuned model (f5fi.FINETUNED_CKPT), base = the base model")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--until-s", type=float, help="stop after the paragraph that passes this many seconds")
    g.add_argument("--paragraphs", type=int, help="read the first N paragraphs (title counts as one)")
    ap.add_argument("--candidates", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-pause", type=float, help="shorten pauses inside each sentence to at most this (e.g. 0.15)")
    args = ap.parse_args()
    args.ckpt = f5fi.resolve_ckpt(args.ckpt)

    os.makedirs(os.path.join(args.out, "lauseet"), exist_ok=True)
    with open(os.path.splitext(args.ref)[0] + ".txt", encoding="utf-8") as f:
        ref_text = f.read().strip()
    with open(args.text, encoding="utf-8") as f:
        paras = paragraphs(f.read())
    if args.paragraphs:
        paras = paras[: args.paragraphs]

    tts = f5fi.load_model(args.ckpt)
    pieces, rows, total, sr, n_para = [], [], 0.0, None, 0
    t_start = time.monotonic()
    for p_i, para in enumerate(paras):
        if p_i:
            pieces.append(("pause", PARAGRAPH_PAUSE_S))
            total += PARAGRAPH_PAUSE_S
        for s_i, sent in enumerate(sentences(para)):
            if s_i:
                pieces.append(("pause", SENTENCE_PAUSE_S))
                total += SENTENCE_PAUSE_S
            name = f"k{p_i + 1:02d}_l{s_i + 1:02d}"
            path = os.path.join(args.out, "lauseet", name + ".wav")
            res = f5fi.synthesize(tts, args.ref, ref_text, sent, path, seed=args.seed, candidates=args.candidates,
                                  max_pause=args.max_pause)
            wave, sr = sf.read(path, dtype="float32")
            pieces.append(("wave", wave))
            total += len(wave) / sr
            best = next((t for t in res.takes if t[0] == res.seed), None)
            rows.append({"name": name, "text": sent, "model_text": res.text, "seed": res.seed,
                         "score": best[1] if best else None, "heard": best[2] if best else None})
            print(f"{name} {total:5.1f} s  siemen {res.seed}"
                  + (f"  {best[1]:.0%}  Whisper: {best[2]}" if best else "") + f"\n    {sent}", flush=True)
        n_para = p_i + 1
        if args.until_s and total >= args.until_s:
            break

    audio = np.concatenate([np.zeros(int(x * sr), np.float32) if kind == "pause" else x for kind, x in pieces])
    sf.write(os.path.join(args.out, "lukeminen.wav"), audio, sr)
    settings = {"text_file": os.path.relpath(args.text, f5fi.ROOT), "paragraphs": n_para,
                "ref": os.path.relpath(args.ref, f5fi.ROOT), "ckpt": os.path.relpath(args.ckpt, f5fi.ROOT),
                "seed": args.seed, "candidates": args.candidates, "sentence_pause_s": SENTENCE_PAUSE_S,
                "paragraph_pause_s": PARAGRAPH_PAUSE_S, "ref_pad_ms": f5fi.REF_PAD_MS, "tail_s": f5fi.TAIL_S,
                "nfe": f5fi.NFE, "max_pause": args.max_pause, "length_s": round(len(audio) / sr, 1), "sentences": rows}
    with open(os.path.join(args.out, "asetukset.json"), "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=1)

    text_html = "".join(f"<p>{html.escape(p)}</p>" for p in paras[:n_para])
    page = f"""<!doctype html><html lang="fi"><head><meta charset="utf-8"><title>Lukunäyte</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:46em;margin:2em auto;padding:0 1em}}
audio{{width:100%}}p{{margin:.6em 0}}.meta{{color:#666;font-size:14px}}</style></head><body>
<h1>Lukunäyte</h1><p class="meta">Malli: {html.escape(settings['ckpt'])}<br>Viite: {html.escape(settings['ref'])}<br>
Pituus {settings['length_s']} s, {len(rows)} lausetta, {n_para} kappaletta tiedostosta {html.escape(settings['text_file'])}</p>
<audio controls src="lukeminen.wav"></audio><h2>Teksti</h2>{text_html}</body></html>"""
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"\n{len(audio) / sr:.1f} s, {n_para} kappaletta, {time.monotonic() - t_start:.0f} s laskentaa -> "
          f"{os.path.join(args.out, 'lukeminen.wav')}")


if __name__ == "__main__":
    main()
