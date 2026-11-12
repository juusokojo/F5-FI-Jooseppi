"""Synthesize Finnish speech with F5-TTS Finnish.

    .venv/bin/python scripts/speak.py "Tekstiä puheeksi." --out puhe.wav
    .venv/bin/python scripts/speak.py "Tekstiä." --ref oma.wav --ref-text "Mitä viitteessä sanotaan." --out puhe.wav
    .venv/bin/python scripts/speak.py "Tekstiä." --seeds 4-11 --out kansio/

--seeds makes one take per seed into the folder --out and a local listening page kansio/index.html for choosing
stress and intonation by ear (f5fi.seed_takes). Run it again with another text and the same folder to add a
sentence to the same page; takes that already exist are not made again.

Without --ref, the recommended reference f5fi.DEFAULT_REF is used. --ckpt picks a fine-tuned checkpoint
from checkpoints/ instead of the base model. Text normalization and inference fixes are in f5fi.py.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f5fi


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text")
    ap.add_argument("--out", required=True, help="output .wav, or a folder with --seeds")
    ap.add_argument("--ref", default=f5fi.DEFAULT_REF, help="reference clip whose voice is copied (default: f5fi.DEFAULT_REF)")
    ap.add_argument("--ref-text", help="words of the reference clip (default: the .txt next to it)")
    ap.add_argument("--ckpt", default=f5fi.BASE_CKPT, help="model checkpoint")
    ap.add_argument("--nfe", type=int, default=f5fi.NFE, help="flow steps: 16 is about twice as fast, 32 default")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--ref-pad-ms", type=int, default=f5fi.REF_PAD_MS, help="silence after the reference (F5's own: 50)")
    ap.add_argument("--tail", type=float, default=f5fi.TAIL_S, help="extra seconds for the line (0 = F5's own estimate)")
    ap.add_argument("--raw", action="store_true", help="send the text without normalization")
    ap.add_argument("--candidates", type=int, default=1,
                    help="takes to generate; local Whisper keeps the one closest to the text (e.g. 3)")
    ap.add_argument("--seeds", help="one take per seed into the folder --out, e.g. 4-11 or 4,6,9")
    ap.add_argument("--name", help="with --seeds: file name prefix (default lause01, lause02, ...)")
    ap.add_argument("--no-whisper", action="store_true", help="with --seeds: no Whisper note per take")
    ap.add_argument("--force", action="store_true", help="with --seeds: make existing takes again")
    args = ap.parse_args()
    if args.seeds and args.candidates > 1:
        ap.error("--seeds and --candidates exclude each other: Whisper cannot pick stress, so --seeds keeps every take")
    seeds = None
    if args.seeds:
        try:
            seeds = f5fi.parse_seeds(args.seeds)
        except ValueError as err:
            ap.error(str(err))
        if args.out.lower().endswith(".wav"):
            ap.error("with --seeds, --out is a folder")

    ref_text = args.ref_text
    if ref_text is None:
        with open(os.path.splitext(args.ref)[0] + ".txt", encoding="utf-8") as f:
            ref_text = f.read().strip()

    t0 = time.time()
    tts = f5fi.load_model(args.ckpt, ref_pad_ms=args.ref_pad_ms)
    t1 = time.time()
    if seeds:
        entry = f5fi.seed_takes(tts, args.ref, ref_text, args.text, args.out, seeds, name=args.name,
                                whisper=not args.no_whisper, force=args.force, ckpt=args.ckpt, nfe=args.nfe,
                                speed=args.speed, tail_s=args.tail, normalize=not args.raw)
        print(f"{entry['name']}: {len(entry['takes'])} ottoa, {time.time() - t1:.0f} s (laite {tts.device})")
        if entry["model_text"] and entry["model_text"] != args.text:
            print(f"mallille: {entry['model_text']}")
        for t in entry["takes"]:
            print(f"  siemen {t['seed']:>2}: {t['file']}" + (f"  Whisper: {t['whisper']}" if "whisper" in t else ""))
        print(f"kuuntelusivu: {os.path.join(args.out, f5fi.SEEDS_PAGE)}")
        return
    res = f5fi.synthesize(tts, args.ref, ref_text, args.text, args.out, nfe=args.nfe, speed=args.speed,
                          seed=args.seed, tail_s=args.tail, normalize=not args.raw, candidates=args.candidates)
    t2 = time.time()
    print(f"{args.out}  (laite {tts.device}, lataus {t1 - t0:.1f} s, synteesi {t2 - t1:.1f} s)")
    if res.text != args.text:
        print(f"mallille: {res.text}")
    for seed, sc, heard in res.takes:
        print(f"  {'*' if seed == res.seed else ' '} siemen {seed}: {sc:.0%}  Whisper: {heard}")


if __name__ == "__main__":
    main()
