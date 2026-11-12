"""Cut a recording of read sentences into fine-tuning clips, check each with local Whisper, keep one good take per
sentence and write F5's metadata.csv.

    .venv/bin/python scripts/prepare_dataset.py "data/raw/viitenäytteet/lauseet1.wav" --sarja 1 --out data/aineisto

The recording is one series of docs/lukulauseet.md read in order with pauses between sentences (--sarja N), or
any sentences listed one per line in a text file (--text file.txt). A continuous reading of a whole text
(data/raw/aineisto/lukeminen_N.txt, read in one go with short pauses) is aligned word by word instead
(--lukeminen file.txt, see kohdistus.py and process_reading); the steps below are for the sentence series:

1. Convert to 24 kHz mono (afconvert) and split at pauses of at least MIN_PAUSE_S.
2. Transcribe each piece with local Whisper and match it to the sentence it is closest to.
3. Keep, for each sentence, the last take that matches it well (a mistake is followed by a retake). Earlier takes,
   cut-off takes and pieces that match no sentence are dropped and listed with the reason.
4. Normalize each kept clip like the reference clips (RMS 0.1, peaks under -1 dBFS) and write it to <out>/wavs/.
5. Write <out>/<name>.tsv (every piece, its transcript, score and decision), <out>/<name>.html (listening page)
   and rebuild <out>/metadata.csv from all .tsv files, with texts through f5fi.normalize_text so training text
   matches what synthesis sends to the model.

The text of a kept clip is the written sentence. Takes whose words differ slightly from it are kept but flagged
("tarkista"), so they can be listened to and the .tsv text corrected by hand; then run with --rebuild.
A kept clip that turns out unclear is dropped with --drop lauseet1_07 (moved to hylatyt/, metadata rebuilt).
A clip read with other words than written gets its text fixed with --set-text lauseet3_03 "Sanat niin kuin sanottiin."
Flagged clips that sound right are marked checked with --approve lauseet4 (whole recording) or --approve lauseet4_06.
"""
import argparse
import csv
import glob
import html
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f5fi  # noqa: E402
import kohdistus  # noqa: E402
import read_text  # noqa: E402
from prepare_refs import normalize  # noqa: E402

SR = 24000
FRAME_S = 0.02
MIN_PAUSE_S = 0.8  # sentences are read with ~2 s pauses; commas give much shorter ones
SPLIT_PAUSE_S = 0.2  # shortest pause tried when one piece holds two sentences read too close together
MIN_SPEECH_S = 0.4  # shorter pieces are clicks or breaths
EDGE_S = 0.2  # silence kept at both ends of a clip
ACCEPT = 0.85  # score needed to count as a take of the sentence
EXACT = 0.97  # below this a kept take is flagged for listening
FIELDS = ["piece", "file", "start", "end", "sentence", "written", "heard", "score", "status"]
DROPPED = "hylätty käsin"


def sentences_from_lukulauseet(path, sarja):
    text = open(path, encoding="utf-8").read()
    part = re.search(rf"^## Sarja {sarja}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not part:
        raise SystemExit(f"Sarjaa {sarja} ei löydy tiedostosta {path}")
    return [m.group(1).strip() for m in re.finditer(r"^\d+\.\s+(.+)$", part.group(1), re.M)]


def _frame_db(data):
    frame = int(SR * FRAME_S)
    n = len(data) // frame
    return 20 * np.log10(np.sqrt(np.mean(data[: n * frame].reshape(n, frame) ** 2, axis=1)) + 1e-12)


def _threshold(db):
    return max(np.percentile(db, 10) + 25, db.max() - 50)


def inner_pauses(data, a, b, threshold):
    """Pauses of at least SPLIT_PAUSE_S inside data[a:b], longest first, as sample positions of their middles."""
    frame = int(SR * FRAME_S)
    db = _frame_db(data[a:b])
    quiet = np.concatenate([[0], (db <= threshold).astype(int), [0]])
    edges = np.flatnonzero(np.diff(quiet))
    runs = [(y - x, (x + y) // 2) for x, y in zip(edges[::2], edges[1::2])
            if x > 0 and y < len(db) and (y - x) * FRAME_S >= SPLIT_PAUSE_S]
    return [a + mid * frame for _, mid in sorted(runs, reverse=True)]


def split_on_pauses(data):
    frame = int(SR * FRAME_S)
    db = _frame_db(data)
    n = len(db)
    threshold = _threshold(db)
    loud = np.concatenate([[0], (db > threshold).astype(int), [0]])
    edges = np.flatnonzero(np.diff(loud))
    runs = list(zip(edges[::2], edges[1::2]))
    pause = int(MIN_PAUSE_S / FRAME_S)
    merged = []
    for a, b in runs:  # join speech runs separated by less than a sentence pause
        if merged and a - merged[-1][1] < pause:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    pieces = []
    for k, (a, b) in enumerate(merged):
        if (b - a) * FRAME_S < MIN_SPEECH_S:
            continue
        lo = merged[k - 1][1] if k else 0
        hi = merged[k + 1][0] if k + 1 < len(merged) else n
        start = max(a - int(EDGE_S / FRAME_S), (lo + a) // 2)
        end = min(b + int(EDGE_S / FRAME_S), (b + hi) // 2)
        pieces.append((start * frame, min(len(data), end * frame)))
    return pieces


def split_pair(data, a, b, heard, sentences, threshold, match, tries=3):
    """If data[a:b] holds two consecutive sentences, split it at an inner pause so both halves match. Returns the
    two rows, or None."""
    pair = max(range(len(sentences) - 1), key=lambda i: f5fi.score(sentences[i] + " " + sentences[i + 1], heard))
    if f5fi.score(sentences[pair] + " " + sentences[pair + 1], heard) < ACCEPT:
        return None
    for cut in inner_pauses(data, a, b, threshold)[:tries]:
        first, second = match(a, cut), match(cut, b)
        if (first["sentence"], second["sentence"]) == (pair + 1, pair + 2) and min(first["score"], second["score"]) >= ACCEPT:
            return [first, second]
    return None


def coverage(written, heard):
    return len(f5fi._plain(heard)) / max(1, len(f5fi._plain(written)))


def load_audio(recording):
    """The recording as 24 kHz mono float32 (afconvert reads wav, aif and m4a)."""
    with tempfile.TemporaryDirectory() as tmp:
        conv = os.path.join(tmp, "rec.wav")
        subprocess.run(["afconvert", "-f", "WAVE", "-d", f"LEF32@{SR}", "-c", "1", recording, conv], check=True)
        data, _ = sf.read(conv, dtype="float32")
    return data


def transcribe_words(data, db, threshold, cache):
    """Whisper's words with times (s) for the whole recording, transcribed in pieces cut at pauses. Saved to `cache`
    (json) and reused while the recording is unchanged."""
    import json

    import mlx_whisper
    from scipy.signal import resample_poly

    key = {"samples": len(data), "rms": round(float(np.sqrt(np.mean(data ** 2))), 8)}
    if os.path.exists(cache):
        saved = json.load(open(cache, encoding="utf-8"))
        if saved.get("key") == key:
            return saved["words"]
    words = []
    pieces = kohdistus.chunks(db, threshold, FRAME_S)
    for k, (a, b) in enumerate(pieces, 1):
        audio = resample_poly(data[int(a * SR):int(b * SR)], 2, 3).astype(np.float32)  # 24 kHz -> 16 kHz
        res = mlx_whisper.transcribe(audio, path_or_hf_repo=f5fi.WHISPER, language="fi", word_timestamps=True,
                                     condition_on_previous_text=False)
        for seg in res["segments"]:
            for w in seg.get("words", []):
                words.append({"word": w["word"].strip(), "start": round(a + w["start"], 3),
                              "end": round(a + w["end"], 3)})
        print(f"\r  Whisper: {k}/{len(pieces)} palaa, {b:.0f} s", end="", flush=True)
    print()
    with open(cache, "w", encoding="utf-8") as f:
        json.dump({"key": key, "words": words}, f, ensure_ascii=False)
    return words


def text_sentences(path):
    """Sentences of a reading text in reading order: paragraphs split as read_text.py does, dialogue dashes dropped."""
    return [s for p in read_text.paragraphs(open(path, encoding="utf-8").read()) for s in read_text.sentences(p)]


def process_reading(recording, text_path, out, name):
    """A continuous reading of text_path aligned sentence by sentence (kohdistus.py). Clips are named
    <name>_NNN.wav by the sentence's number in the whole text."""
    os.makedirs(os.path.join(out, "wavs"), exist_ok=True)
    os.makedirs(os.path.join(out, "hylatyt"), exist_ok=True)
    sentences = text_sentences(text_path)
    data = load_audio(recording)
    db = _frame_db(data)
    threshold = _threshold(db)
    print(f"{name}: {len(data) / SR:.0f} s, tekstissä {len(sentences)} virkettä")
    words = transcribe_words(data, db, threshold, os.path.join(out, f"{name}.sanat.json"))
    rows = kohdistus.sentence_rows(sentences, words, db, threshold, FRAME_S)
    # a rerun replaces the clips of the previous run of this recording
    for old in glob.glob(os.path.join(out, "wavs", f"{name}_[0-9][0-9][0-9].wav")) + \
            glob.glob(os.path.join(out, "hylatyt", f"{name}_patka*.wav")):
        os.remove(old)
    for k, r in enumerate(rows, 1):
        r["piece"] = k
        a, b = int(r["start"] * SR), int(r["end"] * SR)
        if r["status"].startswith(kohdistus.KEPT):
            r["file"] = f"{name}_{r['sentence']:03d}.wav"
            clip, _, _, _ = normalize(data[a:b], -90.0)
            sf.write(os.path.join(out, "wavs", r["file"]), clip, SR, subtype="PCM_16")
        else:
            r["file"] = ""
            sf.write(os.path.join(out, _dropped_path(name, k)), data[a:b], SR, subtype="PCM_16")
        nums = f"{r['sentence']}-{r['last']}" if r.get("last", r["sentence"]) != r["sentence"] else str(r["sentence"])
        print(f"  {k:3d} [{r['start']:7.1f}-{r['end']:7.1f} s] virke {nums:>7s} {r['score']:4.0%} "
              f"{r['status']:24s} {r['heard']}", flush=True)
    save(out, name, rows)
    return rows, kohdistus.missing_sentences(rows, len(sentences)), len(sentences)


def process(recording, sentences, out, name):
    os.makedirs(os.path.join(out, "wavs"), exist_ok=True)
    data = load_audio(recording)
    pieces = split_on_pauses(data)
    print(f"{name}: {len(data) / SR:.0f} s, {len(pieces)} pätkää, {len(sentences)} lausetta")

    threshold = _threshold(_frame_db(data))

    def match(a, b):
        heard = f5fi.transcribe(data[a:b], SR)
        scores = [f5fi.score(s, heard) for s in sentences]
        best = int(np.argmax(scores))
        return {"start": a, "end": b, "sentence": best + 1, "written": sentences[best], "heard": heard,
                "score": scores[best]}

    rows = []
    for a, b in pieces:
        r = match(a, b)
        if r["score"] < ACCEPT:
            parts = split_pair(data, a, b, r["heard"], sentences, threshold, match)
            if parts:
                print(f"     [{a / SR:6.1f}-{b / SR:6.1f} s] kaksi lausetta samassa pätkässä, jaettu", flush=True)
                rows += parts
                continue
        rows.append(r)
    for k, r in enumerate(rows, 1):
        r["piece"] = k
        print(f"  {k:2d} [{r['start'] / SR:6.1f}-{r['end'] / SR:6.1f} s] lause {r['sentence']:2d} {r['score']:.0%}  "
              f"{r['heard']}", flush=True)

    for r in rows:
        if r["score"] < ACCEPT:
            short = coverage(r["written"], r["heard"]) < 0.9
            r["status"] = "keskeneräinen" if short and r["score"] >= 0.4 else "ei vastaa lausetta"
    for i in range(1, len(sentences) + 1):
        takes = [r for r in rows if r["sentence"] == i and "status" not in r]
        for r in takes[:-1]:
            r["status"] = "uusittu"
        if takes:
            keep = takes[-1]
            keep["status"] = "käytössä" if keep["score"] >= EXACT else "käytössä, tarkista"
            keep["file"] = f"{name}_{i:02d}.wav"
            clip, _, _, _ = normalize(data[keep["start"]:keep["end"]], -90.0)
            sf.write(os.path.join(out, "wavs", keep["file"]), clip, SR, subtype="PCM_16")
    os.makedirs(os.path.join(out, "hylatyt"), exist_ok=True)
    for r in rows:
        r.setdefault("file", "")
        if not r["file"]:  # kept for listening on the review page only
            sf.write(os.path.join(out, _dropped_path(name, r["piece"])), data[r["start"]:r["end"]], SR, subtype="PCM_16")
        r["start"], r["end"] = r["start"] / SR, r["end"] / SR

    save(out, name, rows)
    missing = [i for i in range(1, len(sentences) + 1) if not any(r["sentence"] == i and r["file"] for r in rows)]
    return rows, missing


def _dropped_path(name, piece):
    return f"hylatyt/{name}_patka{int(piece):02d}.wav"


def save(out, name, rows):
    with open(os.path.join(out, f"{name}.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "start": f"{float(r['start']):.2f}", "end": f"{float(r['end']):.2f}",
                        "score": f"{float(r['score']):.3f}"})
    write_page(out, name, rows)


def load(out, name):
    rows = list(csv.DictReader(open(os.path.join(out, f"{name}.tsv"), encoding="utf-8"), delimiter="\t"))
    for k, r in enumerate(rows, 1):
        r.setdefault("piece", k)
        r["piece"] = int(r["piece"] or k)
        r["sentence"], r["score"] = int(r["sentence"]), float(r["score"])
    return rows


def drop(out, clip_ids):
    """Drop kept clips by id (lauseet1_07): status DROPPED, wav moved to hylatyt/."""
    for cid in clip_ids:
        name = cid.rsplit("_", 1)[0]
        rows = load(out, name)
        hit = [r for r in rows if r["file"] == cid + ".wav"]
        if not hit:
            print(f"{cid}: ei löydy käytössä olevista pätkistä")
            continue
        r = hit[0]
        os.replace(os.path.join(out, "wavs", r["file"]), os.path.join(out, _dropped_path(name, r["piece"])))
        r["file"], r["status"] = "", DROPPED
        save(out, name, rows)
        print(f"{cid}: hylätty (pätkä {r['piece']}, lause {r['sentence']})")


def approve(out, ids):
    """Mark flagged clips as checked by ear: a clip id (lauseet4_06) or a whole recording name (lauseet4)."""
    for cid in ids:
        is_name = os.path.exists(os.path.join(out, f"{cid}.tsv")) or not re.search(r"_\d+$", cid)
        name = cid if is_name else cid.rsplit("_", 1)[0]
        rows = load(out, name)
        n = 0
        for r in rows:
            if r["status"].startswith("käytössä, tarkista") and (cid == name or r["file"] == cid + ".wav"):
                r["status"] = "käytössä, kuunneltu"
                n += 1
        save(out, name, rows)
        print(f"{cid}: {n} pätkää merkitty kuunnelluksi")


def set_text(out, cid, text):
    """Replace the text of kept clip `cid` with what was actually said."""
    name = cid.rsplit("_", 1)[0]
    rows = load(out, name)
    hit = [r for r in rows if r["file"] == cid + ".wav"]
    if not hit:
        raise SystemExit(f"{cid}: ei löydy käytössä olevista pätkistä")
    hit[0]["written"], hit[0]["status"] = text, "käytössä, teksti korjattu"
    save(out, name, rows)
    print(f"{cid}: {text}")


def write_page(out, name, rows):
    """Listening page: every piece, kept or not. Dropped pieces are in <out>/hylatyt/ for listening only."""
    missing = sorted({r["sentence"] for r in rows} - {r["sentence"] for r in rows if r["file"]})
    tr = []
    for r in rows:
        src = f"wavs/{r['file']}" if r["file"] else _dropped_path(name, r["piece"])
        color = {"käytössä": "#e6f4ea", "käytössä, teksti korjattu": "#e6f4ea", "käytössä, kuunneltu": "#e6f4ea",
                 "käytössä, tarkista": "#fff4d6", "käytössä, tarkista raja": "#fff4d6"}.get(r["status"], "#fbe9e9")
        tr.append(f'<tr style="background:{color}"><td>{r["piece"]}</td><td>{r["sentence"]}</td>'
                  f'<td>{html.escape(r["status"])}</td><td>{r["score"]:.0%}</td>'
                  f'<td>{html.escape(r["written"])}<br><i>Whisper: {html.escape(r["heard"])}</i></td>'
                  f'<td><audio controls preload="none" src="{src}"></audio></td></tr>')
    miss = (f"<p><b>Puuttuu hyväksytty otto:</b> lauseet {', '.join(map(str, missing))}</p>" if missing else "")
    page = f"""<!doctype html><html lang="fi"><head><meta charset="utf-8"><title>{html.escape(name)}</title>
<style>body{{font:15px system-ui;margin:24px;background:#fff;color:#222}}table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;text-align:left}}audio{{width:220px}}</style></head><body>
<h1>{html.escape(name)}</h1><p>Vihreä: käytössä. Keltainen: käytössä, mutta Whisperin litterointi poikkeaa tekstistä,
joten kuuntele. Punainen: hylätty.</p>{miss}
<table><tr><th>Pätkä</th><th>Lause</th><th>Tila</th><th>Pisteet</th><th>Teksti</th><th>Ääni</th></tr>{''.join(tr)}</table>
</body></html>"""
    with open(os.path.join(out, f"{name}.html"), "w", encoding="utf-8") as f:
        f.write(page)


def rebuild_metadata(out):
    """metadata.csv from every .tsv in out: kept clips, written text through f5fi.normalize_text."""
    n = 0
    with open(os.path.join(out, "metadata.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("audio_file|text\n")
        for tsv in sorted(glob.glob(os.path.join(out, "*.tsv"))):
            for r in csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t"):
                if r["file"] and r["status"].startswith("käytössä"):
                    text = f5fi.normalize_text(r["written"])
                    f.write(f"{os.path.abspath(os.path.join(out, 'wavs', r['file']))}|{text}\n")
                    n += 1
    return n


def report(rows, missing, n_sentences):
    kept = [r for r in rows if r["file"]]
    read = sorted({r["sentence"] for r in rows if r["status"] != kohdistus.EXTRA})
    span = f" (luettu virkkeet {read[0]}-{read[-1]} / {n_sentences})" if read else ""
    print(f"\nkäytössä {len(kept)}{span}, tarkistettavia {sum(r['status'] != 'käytössä' for r in kept)}, "
          f"hylättyjä pätkiä {len(rows) - len(kept)}" + (f", puuttuu: {missing}" if missing else ""))
    for r in rows:
        if r["status"] != "käytössä":
            print(f"  pätkä {r['piece']:3d}, virke {r['sentence']:3d}: {r['status']} ({r['score']:.0%}) {r['heard']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", nargs="?")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--sarja", type=int, help="series number in docs/lukulauseet.md")
    src.add_argument("--text", help="file with the sentences, one per line, in reading order")
    src.add_argument("--lukeminen", metavar="TEXT", help="continuous reading of this text (data/raw/aineisto/lukeminen_N.txt)")
    ap.add_argument("--out", default=os.path.join(f5fi.ROOT, "data", "aineisto"))
    ap.add_argument("--name", help="clip name prefix (default: recording file name)")
    ap.add_argument("--rebuild", action="store_true", help="only rebuild metadata.csv from the .tsv files")
    ap.add_argument("--drop", nargs="+", metavar="CLIP", help="drop kept clips, e.g. lauseet1_07 lauseet1_17")
    ap.add_argument("--set-text", nargs=2, metavar=("CLIP", "TEXT"), help="fix the text of a kept clip")
    ap.add_argument("--approve", nargs="+", metavar="CLIP", help="mark flagged clips checked by ear (clip or recording)")
    args = ap.parse_args()

    if args.drop:
        drop(args.out, args.drop)
    elif args.set_text:
        set_text(args.out, *args.set_text)
    elif args.approve:
        approve(args.out, args.approve)
    elif not args.rebuild:
        if not args.recording or not (args.sarja or args.text or args.lukeminen):
            ap.error("anna äänite ja --sarja, --text tai --lukeminen")
        name = args.name or os.path.splitext(os.path.basename(args.recording))[0].lower()
        if args.lukeminen:
            rows, missing, n_sent = process_reading(args.recording, args.lukeminen, args.out, name)
            report(rows, missing, n_sent)
            print(f"metadata.csv: {rebuild_metadata(args.out)} pätkää")
            return
        if args.sarja:
            sentences = sentences_from_lukulauseet(os.path.join(f5fi.ROOT, "docs", "lukulauseet.md"), args.sarja)
        else:
            sentences = [l.strip() for l in open(args.text, encoding="utf-8") if l.strip()]
        rows, missing = process(args.recording, sentences, args.out, name)
        kept = [r for r in rows if r["file"]]
        flagged = [r for r in kept if r["status"] != "käytössä"]
        print(f"\nkäytössä {len(kept)}/{len(sentences)}, tarkistettavia {len(flagged)}, "
              f"hylättyjä pätkiä {len(rows) - len(kept)}" + (f", puuttuu: {missing}" if missing else ""))
        for r in rows:
            if r["status"] != "käytössä":
                print(f"  pätkä {r['piece']:2d}, lause {r['sentence']:2d}: {r['status']} ({r['score']:.0%}) {r['heard']}")
    n = rebuild_metadata(args.out)
    print(f"metadata.csv: {n} pätkää")


if __name__ == "__main__":
    main()
