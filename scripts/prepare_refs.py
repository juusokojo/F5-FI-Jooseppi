"""Turn raw reference recordings (aifc/m4a/wav from QuickTime) into F5 reference clips.

    .venv/bin/python scripts/prepare_refs.py data/raw/viitenäytteet --out data/viite

Each file is converted with macOS afconvert to 24 kHz mono 16-bit WAV, leading and trailing silence is trimmed
(keeping a short margin) and the clip is normalized to RMS 0.1 (-20 dBFS), with peaks kept under -1 dBFS.
F5 matches its output level to the reference whenever the reference is quieter than RMS 0.1, so a quiet clip
gives quiet speech. Normalization is a plain gain: it changes level, not tone. Clipping in the recording and the
noise floor after the gain are reported.

--ext picks one format when the folder holds the same recordings in several formats (e.g. --ext wav).
"""
import argparse
import glob
import os
import subprocess
import tempfile

import numpy as np
import soundfile as sf

SR = 24000
MARGIN_S = 0.25  # silence kept at both ends
FRAME_S = 0.02
MIN_RUN = 5  # frames (0.1 s)
TARGET_RMS = 0.1  # F5's own target level
PEAK_MAX = 10 ** (-1 / 20)  # -1 dBFS
EXTS = ("aifc", "aiff", "aif", "m4a", "wav")


def trim(data):
    frame = int(SR * FRAME_S)
    n = len(data) // frame
    rms = np.sqrt(np.mean(data[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    noise = np.percentile(db, 10)
    threshold = max(noise + 12, np.max(db) - 45)
    # speech = runs of at least MIN_RUN loud frames; shorter blips are clicks (e.g. the record button)
    loud = np.concatenate([[0], (db > threshold).astype(int), [0]])
    edges = np.flatnonzero(np.diff(loud))
    runs = [(a, b) for a, b in zip(edges[::2], edges[1::2]) if b - a >= MIN_RUN]
    first, last = runs[0][0], runs[-1][1]
    start = max(0, first * frame - int(MARGIN_S * SR))
    end = min(len(data), last * frame + int(MARGIN_S * SR))
    return data[start:end], noise


def normalize(data, noise_db):
    rms = np.sqrt(np.mean(data ** 2))
    peak = np.max(np.abs(data))
    gain = min(TARGET_RMS / rms, PEAK_MAX / peak)
    return data * gain, 20 * np.log10(gain), gain < TARGET_RMS / rms, noise_db + 20 * np.log10(gain)


def db(x):
    return 20 * np.log10(x + 1e-12)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="folder of raw recordings")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ext", choices=EXTS, help="only files of this format")
    ap.add_argument("--no-normalize", action="store_true", help="keep the recorded level")
    args = ap.parse_args()

    exts = [args.ext] if args.ext else EXTS
    files = sorted(f for ext in exts for f in glob.glob(os.path.join(args.src, f"*.{ext}")))
    stems = [os.path.splitext(os.path.basename(f))[0].lower() for f in files]
    dupes = sorted({n for n in stems if stems.count(n) > 1})
    if dupes:
        raise SystemExit(f"Samannimisiä tiedostoja eri muodoissa ({', '.join(dupes)}). Valitse muoto, esim. --ext wav.")
    os.makedirs(args.out, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            name = os.path.splitext(os.path.basename(f))[0].lower()
            conv = os.path.join(tmp, name + ".wav")
            subprocess.run(["afconvert", "-f", "WAVE", "-d", f"LEF32@{SR}", "-c", "1", f, conv], check=True)
            data, sr = sf.read(conv, dtype="float32")
            assert sr == SR
            cut, noise = trim(data)
            rms_in, peak_in = np.sqrt(np.mean(cut ** 2)), np.max(np.abs(cut))
            warn = []
            if peak_in > 0.99:
                warn.append("SÄRÖ: äänite on leikkautunut, nauhoita hiljaisemmin")
            level = f"taso {db(rms_in):.1f} dB, huippu {db(peak_in):.1f} dB"
            if not args.no_normalize:
                cut, gain_db, peak_limited, noise = normalize(cut, noise)
                level += f" -> vahvistus {gain_db:+.1f} dB, taso {db(np.sqrt(np.mean(cut ** 2))):.1f} dB"
                if peak_limited:
                    warn.append("huiput rajoittivat vahvistusta, taso jäi alle tavoitteen")
            if noise > -55:
                warn.append("taustakohinaa")
            sf.write(os.path.join(args.out, name + ".wav"), cut, SR, subtype="PCM_16")
            print(f"{name}: {len(data) / SR:.1f} s -> {len(cut) / SR:.1f} s, {level}, kohina {noise:.1f} dB"
                  f"{'  ' + '; '.join(warn) if warn else ''}")


if __name__ == "__main__":
    main()
