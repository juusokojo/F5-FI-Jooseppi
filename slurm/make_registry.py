"""Build voices.json (the voice and clip registry of scripts/serve.py) from a folder of reference clips.

    python slurm/make_registry.py --refs-dir data/viite/palvelu \
        --ckpt valdemar=checkpoints/valdemar-v1/malli_002000.safetensors --out slurm/voices.json

Layout: <refs-dir>/<voice>/<clip>.wav, with the words spoken in the clip in <clip>.txt next to it. The clip's file
name (without .wav) is what the app sends as "clip", and the folder name is the voice ("jooseppi", "justiina2" ...).
Voices not named in --ckpt use the recommended fine-tuned model ("default": Jooseppi's, which the adult voices share).
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rel(path):
    path = os.path.abspath(path)
    return os.path.relpath(path, ROOT) if path.startswith(ROOT + os.sep) else path


def build(refs_dir, ckpts=None, seed=1, log=print):
    ckpts = {k.lower(): v for k, v in (ckpts or {}).items()}
    voices = {}
    for voice in sorted(os.listdir(refs_dir)):
        folder = os.path.join(refs_dir, voice)
        if not os.path.isdir(folder):
            continue
        clips = {}
        for name in sorted(os.listdir(folder)):
            stem, ext = os.path.splitext(name)
            if ext.lower() != ".wav":
                continue
            if not os.path.exists(os.path.join(folder, stem + ".txt")):
                log(f"ohitetaan {voice}/{name}: {stem}.txt (viitteen teksti) puuttuu")
                continue
            clips[stem.lower()] = {"ref": rel(os.path.join(folder, name)), "seed": seed}
        if not clips:
            log(f"ohitetaan ääni {voice}: ei viiteäänitteitä")
            continue
        ckpt = ckpts.get(voice.lower(), "default")
        voices[voice.lower()] = {"ckpt": rel(ckpt) if ckpt not in ("default", "base") else ckpt,
                                 "default_emotion": "neutraali" if "neutraali" in clips else next(iter(clips)),
                                 "emotions": clips}
    unknown = set(ckpts) - set(voices)
    if unknown:
        log(f"varoitus: --ckpt nimeää äänet, joilla ei ole viitteitä: {sorted(unknown)}")
    return {"voices": voices}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refs-dir", required=True)
    ap.add_argument("--ckpt", action="append", default=[], metavar="ÄÄNI=POLKU", help="äänen oma hienosäätö (voi toistaa)")
    ap.add_argument("--seed", type=int, default=1, help="oletussiemen kaikille viitteille")
    ap.add_argument("--out", default=os.path.join(ROOT, "slurm", "voices.json"))
    a = ap.parse_args(argv)
    reg = build(a.refs_dir, dict(c.split("=", 1) for c in a.ckpt), a.seed)
    if not reg["voices"]:
        sys.exit("yhtään ääntä ei löytynyt")
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    for name, v in reg["voices"].items():
        print(f"{name}: {len(v['emotions'])} viitettä, malli {v['ckpt']}")
    print("kirjoitettu:", a.out)


if __name__ == "__main__":
    main()
