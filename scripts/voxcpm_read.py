"""Kokeilu: lue sama katkelma VoxCPM2:lla kuin F5:n lähtötasossa (data/vertailu/2026-11-06_lahtotaso).

    .venv-voxcpm/bin/python scripts/voxcpm_read.py data/vertailu/2026-11-06_lahtotaso --out data/vertailu/<kansio>

Lauseet, viite ja tauot luetaan lähtötason asetukset.json-tiedostosta, joten vertailu käyttää täsmälleen samaa
tekstiä. Tekstiä ei esikäsitellä (ei rajageminaatiota eikä Ä:n pienennystä), ja jokaisesta lauseesta tehdään yksi
otto ilman ehdokasvalintaa. Kloonaus on mallin "Ultimate Cloning" -tila: sama viite annetaan sekä jatkettavaksi
(prompt + litterointi) että äänen malliksi (reference). Malli tuottaa 48 kHz:n ääntä.
"""
import argparse
import json
import os
import shutil
import sys
import time

import numpy as np
import soundfile as sf
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(ROOT, "base-voxcpm2", "VoxCPM2")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline", help="F5:n lähtötason kansio, jossa on asetukset.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--cfg", type=float, default=2.0)
    ap.add_argument("--steps", type=int, default=10)
    ap.add_argument("--device", default="mps")
    args = ap.parse_args()

    with open(os.path.join(args.baseline, "asetukset.json"), encoding="utf-8") as f:
        base = json.load(f)
    ref = os.path.join(ROOT, base["ref"])
    with open(os.path.splitext(ref)[0] + ".txt", encoding="utf-8") as f:
        ref_text = f.read().strip()

    from voxcpm import VoxCPM
    model = VoxCPM.from_pretrained(MODEL_DIR, load_denoiser=False, device=args.device, optimize=False)
    sr = model.tts_model.sample_rate

    os.makedirs(os.path.join(args.out, "lauseet"), exist_ok=True)
    pieces, rows, prev_para = [], [], None
    t_start = time.monotonic()
    for s in base["sentences"]:
        para = s["name"].split("_")[0]
        if prev_para is not None:
            pause = base["paragraph_pause_s"] if para != prev_para else base["sentence_pause_s"]
            pieces.append(np.zeros(int(pause * sr), np.float32))
        prev_para = para
        torch.manual_seed(args.seed)
        t = time.monotonic()
        wav = model.generate(text=s["text"], prompt_wav_path=ref, prompt_text=ref_text, reference_wav_path=ref,
                             cfg_value=args.cfg, inference_timesteps=args.steps)
        wav = np.asarray(wav, np.float32)
        sf.write(os.path.join(args.out, "lauseet", s["name"] + ".wav"), wav, sr)
        pieces.append(wav)
        rows.append({"name": s["name"], "text": s["text"], "seconds": round(len(wav) / sr, 2),
                     "compute_s": round(time.monotonic() - t)})
        print(f"{s['name']} {len(wav) / sr:4.1f} s ääntä, {time.monotonic() - t:4.0f} s laskentaa  {s['text']}",
              flush=True)

    audio = np.concatenate(pieces)
    sf.write(os.path.join(args.out, "lukeminen.wav"), audio, sr)
    settings = {"model": os.path.relpath(MODEL_DIR, ROOT), "baseline": os.path.relpath(args.baseline, ROOT),
                "ref": base["ref"], "seed": args.seed, "cfg_value": args.cfg, "inference_timesteps": args.steps,
                "candidates": 1, "preprocessing": "ei", "sample_rate": sr, "length_s": round(len(audio) / sr, 1),
                "compute_s": round(time.monotonic() - t_start), "sentences": rows}
    with open(os.path.join(args.out, "asetukset.json"), "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=1)
    # lähtötason ääni samaan kansioon, jotta kuuntelusivu toimii suoraan tiedostona
    shutil.copy(os.path.join(args.baseline, "lukeminen.wav"), os.path.join(args.out, "f5_lukeminen.wav"))
    print(f"\n{len(audio) / sr:.1f} s, {settings['compute_s']} s laskentaa -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
