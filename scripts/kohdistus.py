"""Aligning a continuous reading (data/raw/aineisto/lukeminen_N.txt read aloud in one go) to its text.

Sentences in a reading follow each other with short pauses (0.3-1 s), so they cannot be found by pauses alone as
in the sentence series. Instead:

1. chunks(): the recording is cut at pauses into pieces of at most CHUNK_S, which Whisper transcribes with word
   timestamps (prepare_dataset.transcribe_words).
2. align(): the heard words are aligned to the written words with an edit-distance alignment. A retake leaves the
   earlier take as extra heard words; on equal cost the alignment takes the later take, since the reader rereads a
   sentence after a mistake (docs/nauhoitusohje.md, B2).
3. sentence_rows(): each sentence spans the heard words aligned to it. The clip is cut in the pause next to its
   first and last word, found from the loudness of the audio (find_pause), because Whisper's word times drift by a
   few tenths of a second. Heard words outside every sentence (false starts, repeated sentences, hesitations)
   become rows of their own with status EXTRA, for listening only.

Everything here works on word lists and frame loudness only, so it can be tested without audio or models.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f5fi  # noqa: E402

CHUNK_S = 28.0  # Whisper sees 30 s at a time
CHUNK_MIN_S = 8.0
CHUNK_PAUSE_S = 0.3
SENTENCE_PAUSE_S = 0.25  # a pause this long between sentences is trusted as the cut
SHORT_PAUSE_S = 0.12  # shorter quiet runs may be the closure of a double consonant (kk, tt) inside a word
EDGE_S = 0.2  # silence kept at both ends of a clip
SEARCH_S = 0.4  # how far past a word time a pause is looked for
EXTRA_GAP_S = 1.0  # extra heard words further apart than this are separate pieces
MAX_CLIP_S = 30.0  # F5 trains on clips up to about 30 s
MERGE_MAX_S = 20.0  # sentences read without a pause are joined into one clip up to this length

ACCEPT = 0.85
EXACT = 0.97
KEPT, CHECK, CHECK_CUT, EXTRA = "käytössä", "käytössä, tarkista", "käytössä, tarkista raja", "ylimääräinen"


def tokens(text):
    return f5fi._plain(text).split()


# ---- quiet runs ---------------------------------------------------------------------------------------------------

def quiet_runs(db, threshold, frame_s, lo_s=0.0, hi_s=None):
    """Quiet runs (start_s, end_s) of frames at or under threshold within [lo_s, hi_s]."""
    n = len(db)
    lo = max(0, int(lo_s / frame_s))
    hi = n if hi_s is None else min(n, int(np.ceil(hi_s / frame_s)))
    if hi <= lo:
        return []
    quiet = np.concatenate([[0], (db[lo:hi] <= threshold).astype(int), [0]])
    edges = np.flatnonzero(np.diff(quiet))
    return [((lo + a) * frame_s, (lo + b) * frame_s) for a, b in zip(edges[::2], edges[1::2])]


def chunks(db, threshold, frame_s):
    """(start_s, end_s) pieces of at most CHUNK_S covering the recording, cut in the middle of the longest pause
    available between CHUNK_MIN_S and CHUNK_S from the previous cut."""
    total = len(db) * frame_s
    pauses = [(b - a, (a + b) / 2) for a, b in quiet_runs(db, threshold, frame_s) if b - a >= CHUNK_PAUSE_S]
    out, pos = [], 0.0
    while total - pos > CHUNK_S:
        options = [(length, mid) for length, mid in pauses if pos + CHUNK_MIN_S < mid <= pos + CHUNK_S]
        cut = max(options)[1] if options else pos + CHUNK_S
        out.append((pos, cut))
        pos = cut
    out.append((pos, total))
    return out


def find_pause(runs, lo_s, hi_s, anchor_s, side):
    """The pause that ends a clip (side="end": first quiet run reaching past anchor_s) or starts one (side="start":
    last quiet run beginning before anchor_s), among the quiet runs `runs` of the whole recording that overlap
    [lo_s, hi_s]. A run is measured whole, also where it reaches outside the window. A run of SENTENCE_PAUSE_S is
    preferred; failing that one of SHORT_PAUSE_S. Returns ((start_s, end_s), sure) or (None, False)."""
    runs = [r for r in runs if r[1] > lo_s and r[0] < hi_s]
    if side == "end":
        runs = [r for r in runs if r[1] > anchor_s]
    else:
        runs = [r for r in runs if r[0] < anchor_s][::-1]
    for min_len, sure in ((SENTENCE_PAUSE_S, True), (SHORT_PAUSE_S, False)):
        for r in runs:
            if r[1] - r[0] >= min_len - 1e-9:
                return r, sure
    return None, False


# ---- word alignment -----------------------------------------------------------------------------------------------

def _sub_cost(written, heard):
    """Cost of aligning written word i with heard word j: 0 same word, 0.5 same beginning (a compound Whisper wrote
    as two words, an ending misheard) or heard digits (Whisper writes numbers as digits), else 1."""
    ids = {}
    w_id = np.array([ids.setdefault(w, len(ids)) for w in written])
    h_id = np.array([ids.setdefault(h, len(ids)) for h in heard])
    pre = {}
    w_pre = np.array([pre.setdefault(w[:4], len(pre)) for w in written])
    h_pre = np.array([pre.setdefault(h[:4], len(pre)) for h in heard])
    digits = np.array([h.isdigit() for h in heard])
    same_start = (w_pre[:, None] == h_pre[None, :]) & (np.array([len(w) >= 4 for w in written])[:, None])
    near = same_start | digits[None, :]
    return np.where(w_id[:, None] == h_id[None, :], 0.0, np.where(near, 0.5, 1.0))


def align(written, heard):
    """For each written word, the index of the heard word aligned to it, or None. Unread or skipped written words
    and extra heard words cost 1 each. On equal cost the later heard words are used."""
    n, m = len(written), len(heard)
    if not n or not m:
        return [None] * n
    cost = _sub_cost(written, heard)
    D = np.zeros((n + 1, m + 1))
    D[0] = np.arange(m + 1)
    steps = np.arange(m + 1)
    for i in range(1, n + 1):
        row = np.empty(m + 1)
        row[0] = i
        row[1:] = np.minimum(D[i - 1, 1:] + 1, D[i - 1, :-1] + cost[i - 1])
        D[i] = steps + np.minimum.accumulate(row - steps)  # extra heard words: row[j] = min(row[j], row[j-1] + 1)
    out = [None] * n
    i, j = n, m
    while i and j:  # backtrace from the end: a match first, so a repeated sentence keeps its last take
        if np.isclose(D[i, j], D[i - 1, j - 1] + cost[i - 1, j - 1]):
            # a misheard word ("Kulin" for "Kuljin") is linked too: it was said in its place, and leaving it out
            # would cut the clip short of it
            out[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif np.isclose(D[i, j], D[i, j - 1] + 1):
            j -= 1
        else:
            i -= 1
    return out


# ---- sentences ----------------------------------------------------------------------------------------------------

def _joined(words, a, b):
    return " ".join(w["word"].strip() for w in words[a:b + 1])


def _split_compound(heard_tok, h, matched, written_set):
    """True if extra heard token h is half of a written compound that Whisper wrote as two words."""
    for k in (h - 1, h + 1):
        if 0 <= k < len(heard_tok) and k in matched:
            pair = heard_tok[k] + heard_tok[h] if k < h else heard_tok[h] + heard_tok[k]
            if pair in written_set:
                return True
    return False


def sentence_rows(sentences, words, db, threshold, frame_s):
    """Rows for the reading: one per sentence that was read (sentence numbers from 1) and one per piece of extra
    speech. Each row has start, end (s), sentence, last, written, heard, score, status, sure_cut; rows are in time
    order. Sentences read one after another without a pause between them share one row (sentence..last).
    Sentences of which no word was heard are left out. `words` are Whisper's words: dicts with word, start, end."""
    total = len(db) * frame_s
    # heard tokens; a Whisper word may give several ("10.00", "lauantai-aamuna")
    heard_tok, tok_word = [], []
    for k, w in enumerate(words):
        for t in tokens(w["word"]):
            heard_tok.append(t)
            tok_word.append(k)
    written_tok, tok_sent = [], []
    for s_i, s in enumerate(sentences):
        for t in tokens(s):
            written_tok.append(t)
            tok_sent.append(s_i)
    links = align(written_tok, heard_tok)

    spans = {}  # sentence -> (first word, last word, matched heard tokens)
    for wt, ht in enumerate(links):
        if ht is None:
            continue
        s_i = tok_sent[wt]
        a, b, hs = spans.get(s_i, (tok_word[ht], tok_word[ht], set()))
        spans[s_i] = (min(a, tok_word[ht]), max(b, tok_word[ht]), hs | {ht})

    # a compound Whisper wrote as two words is aligned to one of them; take the other half in when it lies just
    # outside the span ("kaupungin | kirjastosta.")
    linked = {ht for ht in links if ht is not None}
    word_toks = {}
    for h, kw in enumerate(tok_word):
        word_toks.setdefault(kw, []).append(h)
    for s_i, (a, b, hs) in spans.items():
        written_set = set(tokens(sentences[s_i]))
        for step, edge in ((1, b), (-1, a)):
            nxt = edge + step
            toks = word_toks.get(nxt, [])
            if toks and not linked & set(toks) and all(_split_compound(heard_tok, h, hs, written_set) for h in toks):
                a, b = min(a, nxt), max(b, nxt)
                hs = hs | set(toks)
        spans[s_i] = (a, b, hs)

    runs = quiet_runs(db, threshold, frame_s)
    in_sentence = np.zeros(len(words), bool)
    for a, b, _ in spans.values():
        in_sentence[a:b + 1] = True

    def prev_end(k):  # end of the heard word before word k, or the start of the recording
        return words[k - 1]["end"] if k > 0 else 0.0

    def next_start(k):
        return words[k + 1]["start"] if k + 1 < len(words) else total

    # cut points of each sentence read
    units = []
    for s_i in sorted(spans):
        a, b, hs = spans[s_i]
        # Whisper often starts a word well inside the pause before it ("Uusi" from 0.0 s when the voice starts at
        # 1.2 s) but ends words close to the voice. The start is therefore looked for up to the middle of the first
        # word, the end from the end of the last word. The neighbouring word's time may itself lie inside the
        # pause, hence the extra SEARCH_S.
        first_mid = (words[a]["start"] + words[a]["end"]) / 2
        p_start, sure_a = find_pause(runs, prev_end(a) - SEARCH_S, first_mid, first_mid, "start")
        p_end, sure_b = find_pause(runs, words[b]["end"] - SEARCH_S, next_start(b) + SEARCH_S, words[b]["end"], "end")
        if p_start and p_start[1] < prev_end(a) - 0.1:  # quiet run inside the previous sentence, not between
            p_start, sure_a = None, False
        if p_end and p_end[0] > next_start(b) + 0.1:
            p_end, sure_b = None, False
        if p_start:
            start = max(p_start[1] - EDGE_S, (p_start[0] + p_start[1]) / 2)
        else:
            start = (prev_end(a) + words[a]["start"]) / 2
        if p_end:
            end = min(p_end[0] + EDGE_S, (p_end[0] + p_end[1]) / 2)
        else:
            end = (words[b]["end"] + next_start(b)) / 2
        units.append({"first": s_i, "last": s_i, "a": a, "b": b, "hs": hs, "start": max(0.0, start),
                      "end": min(total, end), "sure_a": sure_a, "sure_b": sure_b})

    # sentences read one after another without a pause ("On. Ainakin viisi.") become one clip
    merged = []
    for u in units:
        m = merged[-1] if merged else None
        if (m and u["first"] == m["last"] + 1 and u["a"] == m["b"] + 1 and not m["sure_b"]
                and u["end"] - m["start"] <= MERGE_MAX_S):
            m.update(last=u["last"], b=u["b"], hs=m["hs"] | u["hs"], end=u["end"], sure_b=u["sure_b"])
        else:
            merged.append(dict(u))

    rows = []
    for u in merged:
        a, b, hs = u["a"], u["b"], u["hs"]
        text = " ".join(sentences[u["first"]:u["last"] + 1])
        heard = _joined(words, a, b)
        score = f5fi.score(text, heard)
        # extra heard words inside the span: a repeated word or a mid-sentence repair, unless a split compound
        written_set = set(tokens(text))
        inner = [h for h in range(len(heard_tok)) if a <= tok_word[h] <= b and h not in hs]
        repaired = any(not _split_compound(heard_tok, h, hs, written_set) for h in inner)
        start, end = u["start"], u["end"]
        sure = u["sure_a"] and u["sure_b"]

        if score < ACCEPT:
            short = len(f5fi._plain(heard)) / max(1, len(f5fi._plain(text))) < 0.9
            status = "keskeneräinen" if short and score >= 0.4 else "ei vastaa lausetta"
        elif score < EXACT or repaired or end - start > MAX_CLIP_S:
            status = CHECK
        elif not sure:
            status = CHECK_CUT
        else:
            status = KEPT
        rows.append({"start": start, "end": end, "sentence": u["first"] + 1, "last": u["last"] + 1,
                     "written": text, "heard": heard, "score": score, "status": status, "sure_cut": sure,
                     "first_word": a})

    # extra speech: runs of heard words outside every sentence span
    k = 0
    while k < len(words):
        if in_sentence[k]:
            k += 1
            continue
        a = k
        while k + 1 < len(words) and not in_sentence[k + 1] and words[k + 1]["start"] - words[k]["end"] < EXTRA_GAP_S:
            k += 1
        b = k
        k += 1
        following = [r for r in rows if r["first_word"] > b]
        ref = following[0] if following else (rows[-1] if rows else None)
        heard = _joined(words, a, b)
        rows.append({"start": max(0.0, words[a]["start"] - EDGE_S), "end": min(total, words[b]["end"] + EDGE_S),
                     "sentence": ref["sentence"] if ref else 0, "written": ref["written"] if ref else "",
                     "last": ref["sentence"] if ref else 0,
                     "heard": heard, "score": f5fi.score(ref["written"], heard) if ref else 0.0, "status": EXTRA,
                     "sure_cut": False, "first_word": a})

    rows.sort(key=lambda r: r["first_word"])
    for r in rows:
        del r["first_word"]
    return rows


def missing_sentences(rows, n_sentences):
    """Sentences without a kept clip between the first and the last sentence read (a reading may stop mid-text)."""
    read = [r["sentence"] for r in rows if r["status"] != EXTRA]
    if not read:
        return []
    kept = {i for r in rows if r["status"].startswith(KEPT) for i in range(r["sentence"], r.get("last", r["sentence"]) + 1)}
    return [i for i in range(min(read), max(read) + 1) if i not in kept and i <= n_sentences]
