"""Shared F5-TTS Finnish helpers: model loading, text normalization and synthesis.

Used by speak.py, compare_refs.py and other projects:

    from f5fi import load_model, synthesize
    tts = load_model()  # the recommended fine-tuned model; load_model("base") for the base model
    synthesize(tts, "ref.wav", "Viitteen sanat.", "Tekstiä puheeksi.", "out.wav", candidates=3)

Fixes on top of F5's own inference, each found by listening tests (see README):
- Text: boundary gemination is written out, "voisitko selittää sen" -> "voisitko selittääs sen" (rajageminaatio.py,
  needs Voikko).
- Text: capital Ä/Ö/Å are lowercased. The model has learned a word-initial capital Ä badly ("Älä mene" came out as
  "Lämene"); lowercase is pronounced right.
- Text: the first letter of each sentence is lowercased (LOWER_FIRST, docs/aantamishavainnot.md E6). A capital first letter changed the first sound ("Riittää" -> "viittää", "Tutkijat" -> "Kutkijat");
  lowercase was heard right. Blind listening test 2026-11-12: better in 4 of 7, worse in 1; Whisper heard the
  first word right in 24/24 lowercase takes vs 18/24 capital. Names (Voikko) and all-capital words are left alone.
- Reference: F5 trims the reference clip and keeps only 50 ms of silence after it. 600 ms gives a more natural
  start and phrasing, so that is the default here.
- Length: F5 estimates the speech length from text length alone, which cuts short sentences off ("Kiitos avusta"
  came out as "Kiitos avulla"). 0.3 s extra is given and the trailing silence is trimmed afterwards. 0.6 s was too
  much: the model filled it with an extra syllable ("pullaa" -> "pullaato"). 0.3 s also gave the most natural
  stress in listening. Texts under 10 bytes ("Joo.") keep F5's own handling, which sounded right; extra time made
  "Joo." sound like the sentence would go on, and dropping F5's slowdown broke it. Whisper heard these one-word
  lines wrong even when they were right, so judge them by ear.
- Randomness: the seed changes stress and can add or remove an extra syllable (seed 2 fixed "pullaato").
  synthesize(..., candidates=3) makes three takes and keeps the one local Whisper hears closest to the text.
  Stress and intonation also change with the seed, but Whisper does not hear them: seed_takes() keeps one take per
  seed and builds a listening page for choosing by ear (E9 in docs/aantamishavainnot.md).
- Pauses (optional, off by default): synthesize(..., max_pause=0.15) shortens the pauses inside a line to at most
  that many seconds, and longest_pause sets the longest one to exactly its value (E10). In listening 10.-11.11.2026
  a 0.15 s cap improved most lines, but a comma between main clauses or before a list needed a longer pause.
"""
import difflib
import html
import json
import os
import re
import sys
import unicodedata
from typing import NamedTuple

os.environ.setdefault("WANDB_MODE", "disabled")
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # model and vocoder are downloaded once; nothing is fetched at run time

import numpy as np
import soundfile as sf
import torch
import torchaudio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # rajageminaatio.py next to this file
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "base", "model_commonvoice_fi_librivox_fi_vox_populi_fi_20250323")
BASE_CKPT = os.path.join(BASE, "model_last_20250323.safetensors")
VOCAB = os.path.join(BASE, "vocab.txt")
# The one place that picks the recommended reference: speak.py, read_text.py and other projects use DEFAULT_REF
# when no reference is given. Its words are in the .txt next to it.
DEFAULT_REF = os.path.join(ROOT, "data", "viite", "v3", "viite_selitys_2.wav")
BUNDLED_REF = os.path.join(BASE, "AsmoKoskinenRef_v1.wav")  # the clip that came with the base model
# The one place that picks the recommended model, chosen by listening (2026-11-12: step 2000 of the first
# fine-tuning run). load_model(), speak.py, read_text.py and other projects use it when no checkpoint is given.
# The weights are not in the git repo; where the file is missing, the base model is used with a note.
FINETUNED_CKPT = os.path.join(ROOT, "checkpoints", "oma-v1", "malli_002000.safetensors")

LOWER_FIRST = True  # see lower_first()
COLON_SPLIT = True  # E1 in docs/aantamishavainnot.md, on since 2026-11-12 (better in 3 of 5): split at ": ", join with a pause
COLON_GAP_S = 0.3
REF_PAD_MS = 600
TAIL_S = 0.3  # extra time for the generated line; trailing silence is trimmed afterwards
SHORT_BYTES = 10  # below this F5 slows the line to speed 0.3 itself; that is left as it is
NFE = 32
PAUSE_BELOW_PEAK_DB = 40.0  # a pause is quieter than the loudest 5 ms frame by this much (as _trim_tail)
PAUSE_MIN_S = 0.1  # shorter quiet runs are closures and word joins, not pauses
PAUSE_FRAME_S = 0.005
FADE_S = 0.005  # at every cut, so a cut never clicks
WHISPER = "mlx-community/whisper-large-v3-turbo"  # for candidates; already in the Hugging Face cache

_ref_pad_ms = REF_PAD_MS


def _load_wav(path, *a, **kw):
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    return torch.from_numpy(data.T.copy()), sr


torchaudio.load = _load_wav  # torchaudio's own loader needs ffmpeg; reference clips are WAV


NAME_CLASSES = {"etunimi", "sukunimi", "paikannimi", "nimi"}
SENTENCE_START = re.compile(r"(?:^|[.!?…]\s+)[\"”'(–-]*\s*([^\W\d_][^\W\d_]*)")


def lower_first(text):
    """Lowercase the first letter of each sentence, except names and words with more capitals ("EU").

    A name is a word Voikko knows only as a name ("Leena", "Helsinki"); "Tuuli" or "Aamulla" are also common words
    and are lowercased."""
    import rajageminaatio

    v = rajageminaatio._analyzer()
    out, pos = [], 0
    for m in SENTENCE_START.finditer(text):
        word = m.group(1)
        if not word[0].isupper() or word[1:] != word[1:].lower():
            continue
        analyses = v.analyze(word) if v is not None else []
        if analyses and all(a.get("CLASS") in NAME_CLASSES for a in analyses):
            continue
        out.append(text[pos:m.start(1)] + word[0].lower())
        pos = m.start(1) + 1
    out.append(text[pos:])
    return "".join(out)


def normalize_text(text, geminate=True, lower=None):
    """Text as sent to the model: boundary gemination written out (rajageminaatio.py), capital Ä/Ö/Å lowercased,
    and with lower (default LOWER_FIRST) the first letter of each sentence lowercased."""
    import rajageminaatio

    text = unicodedata.normalize("NFC", text)
    if geminate:
        text = rajageminaatio.mark_compounds(rajageminaatio.mark(text))
    if LOWER_FIRST if lower is None else lower:
        text = lower_first(text)
    return text.replace("Ä", "ä").replace("Ö", "ö").replace("Å", "å")


def resolve_ckpt(ckpt=None):
    """Checkpoint path: None -> the recommended fine-tuned model (the base model if it is missing), "base" -> base."""
    if ckpt == "base":
        return BASE_CKPT
    if ckpt is not None:
        return ckpt
    if os.path.exists(FINETUNED_CKPT):
        return FINETUNED_CKPT
    print(f"huom: hienosäädettyä mallia {os.path.relpath(FINETUNED_CKPT, ROOT)} ei ole, käytetään perusmallia",
          file=sys.stderr)
    return BASE_CKPT


def load_model(ckpt=None, ref_pad_ms=REF_PAD_MS):
    """F5 with the fixes below. ckpt: None = the recommended fine-tuned model, "base" = the base model, or a path."""
    ckpt = resolve_ckpt(ckpt)
    global _ref_pad_ms
    _ref_pad_ms = ref_pad_ms
    from f5_tts.api import F5TTS
    from f5_tts.infer import utils_infer
    from pydub import AudioSegment

    if not getattr(utils_infer, "_f5fi_patched", False):
        trim_edges = utils_infer.remove_silence_edges

        def trim_and_pad(audio, *a, **kw):  # F5 then adds its own 50 ms
            return trim_edges(audio, *a, **kw) + AudioSegment.silent(max(0, _ref_pad_ms - 50))

        utils_infer.remove_silence_edges = trim_and_pad
        utils_infer._f5fi_patched = True
    return F5TTS(model="F5TTS_v1_Base", ckpt_file=ckpt, vocab_file=VOCAB)


def _trim_head(wave, sr, keep_s=0.0, frame_s=0.02):
    frame = int(sr * frame_s)
    n = len(wave) // frame
    if n == 0:
        return wave
    db = 20 * np.log10(np.sqrt(np.mean(wave[: n * frame].reshape(n, frame) ** 2, axis=1)) + 1e-9)
    loud = np.flatnonzero(db > db.max() - 40)
    return wave[max(0, loud[0] * frame - int(keep_s * sr)):]


def _trim_tail(wave, sr, keep_s=0.15, frame_s=0.02):
    frame = int(sr * frame_s)
    n = len(wave) // frame
    if n == 0:
        return wave
    db = 20 * np.log10(np.sqrt(np.mean(wave[: n * frame].reshape(n, frame) ** 2, axis=1)) + 1e-9)
    loud = np.flatnonzero(db > db.max() - 40)
    end = min(len(wave), (loud[-1] + 1) * frame + int(keep_s * sr))
    return wave[:end]


class Result(NamedTuple):
    text: str  # text actually sent to the model
    seed: int  # seed of the kept take
    takes: list  # [(seed, score, transcript)] when candidates > 1, else []


def _plain(text):
    text = re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFC", text).lower())
    return " ".join(text.split())


def transcribe(wave, sr):
    """Local Whisper (mlx-whisper, large-v3-turbo) transcript of a generated line."""
    import mlx_whisper
    from scipy.signal import resample_poly

    g = np.gcd(int(sr), 16000)
    audio = resample_poly(wave, 16000 // g, int(sr) // g).astype(np.float32)
    return mlx_whisper.transcribe(audio, path_or_hf_repo=WHISPER, language="fi")["text"].strip()


def score(text, transcript):
    """Character-level similarity of the text and what Whisper heard, 0..1. Whisper writes colloquial words in
    standard form (tajunnu -> tajunnut), which lowers every take of a line alike, so only the ranking matters.
    Whisper also writes numbers as digits ("kello 10.00" for "kello kymmeneen"): digits that stand where the text has
    other words are taken to be those words, as there is no telling which number word they stand for."""
    written, heard = _plain(text).split(), _plain(transcript).split()
    fixed = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, written, heard, autojunk=False).get_opcodes():
        block = heard[j1:j2]
        if op in ("replace", "insert") and block and all(w.isdigit() for w in block):
            fixed += written[i1:i2]
        else:
            fixed += block
    return difflib.SequenceMatcher(None, " ".join(written), " ".join(fixed), autojunk=False).ratio()


def _generate(tts, ref, ref_text, text, nfe, speed, seed, tail_s):
    from f5_tts.infer.utils_infer import preprocess_ref_audio_text

    fix_duration = None
    if tail_s:
        # same estimate as F5 (length in UTF-8 bytes, relative to the reference) plus tail_s
        ref_file, ref_text_p = preprocess_ref_audio_text(ref, ref_text, show_info=lambda *a: None)
        ref_s = sf.info(ref_file).duration
        if len(ref_text_p[-1].encode("utf-8")) == 1:
            ref_text_p += " "
        gen_s = ref_s * len(text.encode("utf-8")) / len(ref_text_p.encode("utf-8")) / speed
        fix_duration = ref_s + gen_s + tail_s
    wave, sr, _ = tts.infer(ref, ref_text, text, nfe_step=nfe, speed=speed, seed=seed, fix_duration=fix_duration,
                            show_info=lambda *a: None, progress=None)
    if tail_s:
        wave = _trim_tail(wave, sr)
    return wave, sr


def split_colon(text, lower=None):
    """Parts of a text split at ': ' (E1). The first part ends in a full stop instead of the colon; later parts get
    a lowercase first letter like any sentence (lower_first). One part if there is no such colon."""
    parts = [p.strip() for p in re.split(r":\s+", text)]
    if len(parts) == 1:
        return parts
    parts = [p + "." if i < len(parts) - 1 else p for i, p in enumerate(parts)]
    if LOWER_FIRST if lower is None else lower:
        parts = [parts[0]] + [lower_first(p) for p in parts[1:]]
    return parts


def synthesize(tts, ref, ref_text, text, out, nfe=NFE, speed=1.0, seed=1, tail_s=TAIL_S, normalize=True,
               candidates=1, colon_split=None, max_pause=None, longest_pause=None):
    """Write `text` spoken in the voice of `ref` to `out` (wav).

    candidates > 1 generates that many takes (seeds seed, seed+1, ...), has local Whisper transcribe each and keeps
    the one closest to the text. This catches extra syllables and cut-off endings, not stress or tone. Lines under
    10 bytes get one take: Whisper hears one-word lines wrong even when they are right. Stops early on a perfect take.

    colon_split (default COLON_SPLIT, only with normalize): say the parts around ': ' as separate takes (E1).

    max_pause / longest_pause (seconds, default off): see cap_pauses (E10). With a colon split they apply to each part;
    the pause at the colon stays COLON_GAP_S.
    """
    if colon_split is None:
        colon_split = COLON_SPLIT and normalize
    if normalize:
        text = normalize_text(text)
    parts = split_colon(text) if colon_split else [text]
    if len(parts) > 1:
        waves, takes, first_seed = [], [], None
        for p in parts:
            wave, sr, s, t = _synth_one(tts, ref, ref_text, p, nfe, speed, seed, tail_s, candidates)
            waves.append(cap_pauses(wave, sr, max_pause, longest_pause))
            takes += t
            first_seed = s if first_seed is None else first_seed
        joined = []
        for k, w in enumerate(waves):
            if k:
                w = _trim_head(w, sr)
                joined.append(np.zeros(int(COLON_GAP_S * sr), dtype=w.dtype))
            if k < len(waves) - 1:
                w = _trim_tail(w, sr, keep_s=0)  # the gap is exactly COLON_GAP_S of silence
            joined.append(w)
        sf.write(out, np.concatenate(joined), sr)
        return Result(" | ".join(parts), first_seed, takes)
    wave, sr, s, t = _synth_one(tts, ref, ref_text, text, nfe, speed, seed, tail_s, candidates)
    sf.write(out, cap_pauses(wave, sr, max_pause, longest_pause), sr)
    return Result(text, s, t)


def _synth_one(tts, ref, ref_text, text, nfe, speed, seed, tail_s, candidates):
    """One take, or the best of `candidates` takes by Whisper. Returns (wave, sr, seed, takes)."""
    short = len(text.encode("utf-8")) < SHORT_BYTES
    if short:
        tail_s = 0  # F5's own handling (slowed to speed 0.3) gives a natural one-word line
        candidates = 1
    if candidates <= 1:
        wave, sr = _generate(tts, ref, ref_text, text, nfe, speed, seed, tail_s)
        return wave, sr, seed, []

    best, takes = None, []
    for s in range(seed, seed + candidates):
        wave, sr = _generate(tts, ref, ref_text, text, nfe, speed, s, tail_s)
        heard = transcribe(wave, sr)
        sc = score(text, heard)
        takes.append((s, sc, heard))
        if best is None or sc > best[0]:
            best = (sc, s, wave, sr)
        if sc >= 1.0:
            break
    return best[2], best[3], best[1], takes


def find_pauses(wave, sr, min_s=PAUSE_MIN_S, below_peak_db=PAUSE_BELOW_PEAK_DB, frame_s=PAUSE_FRAME_S):
    """Pauses inside a line as [(start_s, end_s)]: quiet runs of at least min_s. Silence at the start or end of the
    line is not a pause."""
    frame = max(1, int(round(sr * frame_s)))
    n = len(wave) // frame
    if n == 0:
        return []
    rms = np.sqrt(np.mean(np.asarray(wave[: n * frame], dtype=np.float64).reshape(n, frame) ** 2, axis=1))
    db = 20 * np.log10(rms + 1e-9)
    quiet = db < db.max() - below_peak_db
    pauses, i = [], 0
    while i < n:
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < n and quiet[j]:
            j += 1
        if i > 0 and j < n and (j - i) * frame >= min_s * sr - 1e-6:
            pauses.append((i * frame / sr, j * frame / sr))
        i = j
    return pauses


def cap_pauses(wave, sr, max_s=None, longest_s=None):
    """`wave` with each pause inside it (find_pauses) cut to at most max_s seconds from its middle (E10). With
    longest_s the longest pause is set to exactly that length instead, shortened or lengthened with silence, for a
    comma that needs its pause ("varmana, esimerkiksi ..."). Unchanged when both are None."""
    if max_s is None and longest_s is None:
        return wave
    pauses = find_pauses(wave, sr)
    ops = [[s, e, e - s if max_s is None else min(e - s, max_s)] for s, e in pauses]
    if longest_s is not None and ops:
        ops[max(range(len(ops)), key=lambda k: ops[k][1] - ops[k][0])][2] = longest_s
    pieces, at = [], 0
    for s, e, target in ops:
        d = e - s
        if abs(target - d) < 0.005:
            continue
        if target < d:
            a, b = int(round((s + target / 2) * sr)), int(round((e - target / 2) * sr))
            pieces.append(wave[at:a])
            at = b
        else:
            mid = int(round((s + e) / 2 * sr))
            pieces += [wave[at:mid], np.zeros(int(round((target - d) * sr)), dtype=wave.dtype)]
            at = mid
    if not pieces:
        return wave
    pieces.append(wave[at:])
    fade = int(FADE_S * sr)
    out = []
    for k, p in enumerate(pieces):
        p = np.array(p, copy=True)
        if len(p) > 2 * fade and p.any():
            if k > 0:
                p[:fade] *= np.linspace(0, 1, fade, dtype=p.dtype)
            if k < len(pieces) - 1:
                p[-fade:] *= np.linspace(1, 0, fade, dtype=p.dtype)
        out.append(p)
    return np.concatenate(out)


SEEDS_FILE = "siemenet.json"  # what seed_takes() has made in a folder; the page is built from it
SEEDS_PAGE = "index.html"


def parse_seeds(spec):
    """Seeds from "4-11", "4,6,9" or "4-6,9" (in that order, no repeats)."""
    seeds = []
    for part in str(spec).replace(" ", "").split(","):
        if not part:
            continue
        lo, dash, hi = part.partition("-")
        lo = int(lo)
        hi = int(hi) if dash else lo  # "4-" is an error, not 4
        if hi < lo:
            raise ValueError(f"siemenväli väärin päin: {part}")
        seeds += [x for x in range(lo, hi + 1) if x not in seeds]
    if not seeds:
        raise ValueError(f"ei siemeniä: {spec!r}")
    return seeds


def seed_takes(tts, ref, ref_text, text, out_dir, seeds, name=None, whisper=True, force=False, ckpt=None, **kw):
    """One take of `text` per seed in `out_dir`, for choosing stress and intonation by ear (E9).

    Takes are <name>-sNN.wav. The same text keeps its name, and a new text gets the next free one (lause01,
    lause02, ...), so several sentences can be made into one folder, also by separate runs. A take that already
    exists for the same text and settings is not made again unless `force`. Whisper's transcript is kept as a note
    only: it shows a missing or extra word, not stress. Writes <out_dir>/siemenet.json and the local listening page
    <out_dir>/index.html (not to be published). Other keyword arguments go to synthesize (nfe, speed, tail_s,
    normalize, colon_split); candidates is always 1. Returns the entry of this text from siemenet.json.
    """
    os.makedirs(out_dir, exist_ok=True)
    data = _load_seeds(out_dir)
    kw.pop("candidates", None)
    settings = {"ref": os.path.abspath(ref), "ckpt": os.path.abspath(ckpt) if ckpt else None,
                **{k: kw[k] for k in sorted(kw) if kw[k] is not None}}  # an option left out is not a change
    entry = next((e for e in data["lauseet"] if e["text"] == text and (name is None or e["name"] == name)), None)
    if entry is None:
        used = {e["name"] for e in data["lauseet"]}
        if name is None:
            name = next(f"lause{i:02d}" for i in range(1, 10 ** 4) if f"lause{i:02d}" not in used)
        elif name in used:
            raise ValueError(f"nimi {name} on jo toisella tekstillä kansiossa {out_dir}")
        entry = {"name": name, "text": text, "model_text": None, "takes": []}
        data["lauseet"].append(entry)
    if entry.get("settings") != settings:
        entry["settings"], entry["takes"] = settings, []  # takes made with other settings would not compare
    by_seed = {t["seed"]: t for t in entry["takes"]}
    for seed in seeds:
        wav = f"{entry['name']}-s{seed:02d}.wav"
        path = os.path.join(out_dir, wav)
        if not force and seed in by_seed and os.path.exists(path):
            continue
        res = synthesize(tts, ref, ref_text, text, path, seed=seed, candidates=1, **kw)
        entry["model_text"] = res.text
        take = {"seed": seed, "file": wav, "duration_s": round(sf.info(path).duration, 2)}
        if whisper:
            wave, sr = sf.read(path, dtype="float32")
            heard = transcribe(wave, sr)
            take.update(whisper=heard, score=round(score(res.text.replace(" | ", " "), heard), 3))
        by_seed[seed] = take
        entry["takes"] = sorted(by_seed.values(), key=lambda t: t["seed"])
        _save_seeds(out_dir, data)  # after every take, so an interrupted run keeps what it made
    _save_seeds(out_dir, data)
    return entry


def _load_seeds(out_dir):
    path = os.path.join(out_dir, SEEDS_FILE)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"lauseet": []}


def _save_seeds(out_dir, data):
    with open(os.path.join(out_dir, SEEDS_FILE), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, SEEDS_PAGE), "w", encoding="utf-8") as f:
        f.write(seed_page(data))


def seed_page(data):
    """Local listening page for the takes in siemenet.json: each sentence with its takes side by side and a
    choice per sentence. The choices are collected into a text to copy back (and kept in the browser)."""
    e = html.escape
    blocks = []
    for entry in data["lauseet"]:
        rows = []
        for t in entry["takes"]:
            note = ""
            if "whisper" in t:
                note = f'<div class=note>Whisper ({t["score"]:.2f}): {e(t["whisper"])}</div>'
            rows.append(f'<label class=take><input type=radio name="{e(entry["name"])}" value="{t["seed"]}">'
                        f'<span class=seed>siemen {t["seed"]}</span>'
                        f'<audio controls preload="none" src="{e(t["file"])}"></audio>'
                        f'<span class=dur>{t["duration_s"]:.1f} s</span>{note}</label>')
        model = ""
        if entry.get("model_text") and entry["model_text"] != entry["text"]:
            model = f'<div class=note>mallille: {e(entry["model_text"])}</div>'
        blocks.append(f'<section><h2>{e(entry["name"])}</h2><p class=text>{e(entry["text"])}</p>{model}'
                      f'{"".join(rows)}</section>')
    return f"""<!doctype html><html lang="fi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Siemenvalinta</title>
<style>
:root{{--bg:#f6f3ec;--fg:#1f2a26;--muted:#5c6862;--card:#fff;--line:#d9d3c7;--pick:#e3efe6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#191c1b;--fg:#e7e4dc;--muted:#a3aba6;--card:#232826;--line:#3a403d;--pick:#24372b}}}}
body{{font:16px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);margin:0;padding:16px;max-width:52em}}
section{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:14px 0}}
h2{{font-size:1rem;margin:0;color:var(--muted)}} .text{{font-size:1.1rem;margin:.2em 0 .5em}}
.take{{display:grid;grid-template-columns:auto auto 1fr auto;gap:4px 10px;align-items:center;padding:6px;border-radius:6px}}
.take:has(input:checked){{background:var(--pick)}} audio{{width:100%;min-width:160px}}
.seed{{font-variant-numeric:tabular-nums;white-space:nowrap}} .dur{{color:var(--muted);font-size:.85rem}}
.note{{grid-column:2/-1;color:var(--muted);font-size:.85rem}} section>.note{{margin-bottom:.4em}}
textarea{{width:100%;box-sizing:border-box;font:inherit;padding:6px;min-height:6em;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px}}
</style></head><body>
<h1>Siemenvalinta</h1>
<p>Samasta tekstistä on yksi otto kullakin siemenellä. Kuuntele ja valitse jokaisesta lauseesta otto, jossa paino ja
sävelkulku ovat oikein. Whisperin litterointi kertoo vain puuttuvista tai ylimääräisistä sanoista, ei painosta.
Sivu on paikallinen tiedosto: älä julkaise sitä tai ääntä verkkoon.</p>
{"".join(blocks)}
<h2>Valinnat</h2><textarea id=out readonly></textarea>
<script>
const KEY = "siemenvalinta:" + location.pathname;
function load() {{ try {{ return JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{ return {{}}; }} }}
function show() {{
  const picks = {{}};
  document.querySelectorAll("input[type=radio]:checked").forEach(r => picks[r.name] = r.value);
  document.getElementById("out").value = Object.entries(picks).map(([n, s]) => n + ": siemen " + s).join("\n");
  try {{ localStorage.setItem(KEY, JSON.stringify(picks)); }} catch (e) {{}}
}}
const saved = load();
document.querySelectorAll("input[type=radio]").forEach(r => {{
  if (saved[r.name] === r.value) r.checked = true;
  r.addEventListener("change", show);
}});
show();
</script></body></html>
"""
