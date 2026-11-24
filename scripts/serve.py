"""Puhepalvelu: HTTP-rajapinta F5-fi-mallille, tarkoitettu ajettavaksi Slurm-työnä GPU-solmulla.

    python scripts/serve.py --voices slurm/voices.json --state-dir $HOME/f5fi-tila --workers 2 --max-sessions 4

Rakenne (perustelut: docs/palvelin-lehmus.md):
- Yksi portti, yksi HTTP-prosessi (portinvartija), joka pitää jonon, istuntopaikat ja osoitetiedoston.
- N työläisprosessia (spawn), joista jokainen lataa kaikki mallit ja tekee yhden lauseen kerrallaan. F5 asettaa
  satunnaissiemenen koko prosessille (seed_everything), joten samassa prosessissa ei ajeta kahta generointia yhtä aikaa.
- Teksti jaetaan lauseiksi (kuten read_text.py), ja jokainen lause on oma tehtävänsä. Reaaliaikaiset (interactive)
  tehtävät ohittavat erä- (batch) tehtävät jonossa, ja yksi erätehtävä on enintään yhden lauseen mittainen.
- Istunnot: POST /sessions antaa paikan tai 429. Paikka vapautuu DELETE-kutsulla tai kun sydämenlyönti loppuu.
- Elinkaari: valmis -> osoite kirjoitetaan tiedostoon; SIGUSR1 (Slurmin --signal) = aikaraja lähestyy; SIGTERM = sammuta
  siististi (ei uusia istuntoja, kesken olevat lauseet valmiiksi).
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import functools
import heapq
import hmac
import io
import itertools
import json
import logging
import math
import multiprocessing as mp
import os
import re
import signal
import socket
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log = logging.getLogger("f5serve")

INTERACTIVE, BATCH = 0, 1
PRIO_NAME = {INTERACTIVE: "interactive", BATCH: "batch"}
SENTENCE_PAUSE_S = 0.3  # as read_text.py
# same rule as read_text.SPLIT: after . ! ? when the next sentence starts with a capital
SPLIT = re.compile(r"(?<=[.!?])\s+(?=(?:–\s+)?[A-ZÅÄÖ])")
BOLD = re.compile(r"\*\*([^*]+)\*\*")  # **korostus** is emphasis: the words are kept
STAGE = re.compile(r"\*[^*]+\*|\[[^\]]*\]|<[^>]*>")  # *huokaisee*, [naurahtaa], <b>
EMOJI = re.compile("[\U00010000-\U0010ffff☀-➿️‍]")


# ---------------------------------------------------------------- text

def clean_text(text: str) -> str:
    """Text as an LLM writes it -> text that can be spoken: no stage directions, markdown noise or emoji."""
    text = unicodedata.normalize("NFC", text)
    text = BOLD.sub(r"\1", text)
    text = STAGE.sub(" ", text)
    text = EMOJI.sub("", text)
    text = re.sub(r"[*`#_~|]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", text)  # a removed stage direction must not leave "word ,"


def split_sentences(text: str) -> list[str]:
    out = []
    for s in SPLIT.split(text):
        s = re.sub(r"^–\s+", "", s).strip()
        if s and re.search(r"\w", s):
            out.append(s)
    return out


# ---------------------------------------------------------------- voices

@dataclass
class Emotion:
    ref: str
    ref_text: str
    seed: int = 1
    nfe: int | None = None
    speed: float = 1.0


@dataclass
class Voice:
    name: str
    ckpt: str  # "default" (recommended fine-tuned model), "base", or a path
    default_emotion: str
    emotions: dict[str, Emotion]

    def pick(self, emotion: str | None) -> tuple[str, Emotion]:
        """The wanted emotion, or the voice's default when it is missing or unknown."""
        key = (emotion or "").strip().lower()
        if key not in self.emotions:
            key = self.default_emotion
        return key, self.emotions[key]


def _path(p: str) -> str:
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def load_registry(path: str, check_files: bool = True) -> dict[str, Voice]:
    """voices.json -> {name: Voice}. See slurm/voices.example.json. Relative paths are relative to the repository."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    voices = {}
    for name, v in data["voices"].items():
        emotions = {}
        for ename, e in v["emotions"].items():
            ref = _path(e["ref"])
            text = e.get("ref_text")
            if check_files and not os.path.exists(ref):
                raise SystemExit(f"{name}/{ename}: viiteäänitettä ei ole: {ref}")
            if text is None and check_files:
                txt = os.path.splitext(ref)[0] + ".txt"
                if not os.path.exists(txt):
                    raise SystemExit(f"{name}/{ename}: viitteen litteraatti puuttuu: {txt} (tai anna ref_text)")
                with open(txt, encoding="utf-8") as f:
                    text = f.read().strip()
            emotions[ename.lower()] = Emotion(ref, text or "", int(e.get("seed", 1)), e.get("nfe"), float(e.get("speed", 1.0)))
        ckpt = v.get("ckpt", "default")
        if check_files and ckpt not in ("default", "base") and not os.path.exists(_path(ckpt)):
            raise SystemExit(f"{name}: mallitiedostoa ei ole: {_path(ckpt)}")
        default = v.get("default_emotion", next(iter(emotions)))
        if default.lower() not in emotions:
            raise SystemExit(f"{name}: oletustunnetta {default!r} ei ole tunteiden joukossa")
        voices[name.lower()] = Voice(name.lower(), ckpt if ckpt in ("default", "base") else _path(ckpt), default.lower(), emotions)
    if not voices:
        raise SystemExit("äänirekisteri on tyhjä")
    return voices


# ---------------------------------------------------------------- backends (run inside worker processes)

class F5Backend:
    """The real model. One F5 instance per distinct checkpoint; voices that share weights share the instance."""

    def __init__(self, voices_path: str, gpu_fraction: float = 0.0):
        self.voices_path, self.gpu_fraction = voices_path, gpu_fraction
        self.voices: dict[str, Voice] = {}
        self.models: dict[str, object] = {}

    def load(self):
        import f5fi
        import torch

        if self.gpu_fraction and torch.cuda.is_available():
            torch.cuda.set_per_process_memory_fraction(self.gpu_fraction)
        self.voices = load_registry(self.voices_path)
        for ckpt in sorted({v.ckpt for v in self.voices.values()}):
            self.models[ckpt] = f5fi.load_model(None if ckpt == "default" else ckpt)
        log.info("worker: %d model(s) loaded on %s", len(self.models), "cuda" if torch.cuda.is_available() else "cpu")

    def warmup(self):
        """One short line per voice: warms the GPU kernels and fails at start-up, not in the first request, if a
        reference clip or checkpoint is unusable."""
        for v in self.voices.values():
            self.synth(v.name, v.default_emotion, "Hei, tämä on koe.", 1, 8)

    def synth(self, voice: str, emotion: str, text: str, seed: int, nfe: int):
        import f5fi
        import torch

        v = self.voices[voice]
        e = v.emotions[emotion]
        try:
            with tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "o.wav")
                f5fi.synthesize(self.models[v.ckpt], e.ref, e.ref_text, text, out, nfe=nfe, speed=e.speed, seed=seed,
                                candidates=1)
                wave, sr = sf.read(out, dtype="float32")
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            raise
        return wave, sr


class FakeBackend:
    """For tests and for trying the service without a GPU: a tone whose length follows the text."""

    def __init__(self, voices_path: str | None = None, delay: float = 0.2, load_delay: float = 0.0):
        self.delay, self.load_delay = delay, load_delay

    def load(self):
        time.sleep(self.load_delay)

    def warmup(self):
        pass

    def synth(self, voice, emotion, text, seed, nfe):
        if "KAATUMINEN" in text:
            os._exit(1)
        if "VIRHE" in text:
            raise RuntimeError("CUDA out of memory (fake)")
        if "JUMI" in text:
            time.sleep(60)
        time.sleep(self.delay)
        sr = 24000
        t = np.arange(int(sr * 0.04 * max(len(text), 1))) / sr
        return (0.1 * np.sin(2 * np.pi * (180 + 20 * (seed % 10)) * t)).astype(np.float32), sr


def _worker_main(idx, gen, factory, task_q, result_q):
    logging.basicConfig(level=logging.INFO, format=f"%(asctime)s %(levelname)s worker{idx}: %(message)s")
    try:
        backend = factory()
        backend.load()
        backend.warmup()
    except BaseException as e:  # noqa: BLE001 - reported to the parent, which decides what to do
        result_q.put(("failed", idx, gen, None, repr(e)))
        return
    result_q.put(("ready", idx, gen, None, None))
    while True:
        item = task_q.get()
        if item is None:
            return
        tid, p = item
        t0 = time.monotonic()
        try:
            wave, sr = backend.synth(p["voice"], p["emotion"], p["text"], p["seed"], p["nfe"])
            result_q.put(("done", idx, gen, tid, (wave, sr, time.monotonic() - t0)))
        except Exception as e:  # noqa: BLE001
            result_q.put(("error", idx, gen, tid, repr(e)))


# ---------------------------------------------------------------- engine: queue, workers, metrics

class QueueFull(Exception):
    def __init__(self, retry_after):
        self.retry_after = retry_after


class JobExpired(Exception):
    pass


class WorkerError(Exception):
    pass


@dataclass
class Job:
    tid: int
    prio: int
    payload: dict
    fut: asyncio.Future
    t_enq: float
    deadline: float | None
    cancelled: bool = False
    wait_s: float = 0.0
    gen_s: float = 0.0


@dataclass
class Slot:
    idx: int
    gen: int = 0
    proc: mp.Process | None = None
    task_q: object = None
    state: str = "starting"  # starting | idle | busy | dead
    job: Job | None = None
    t_busy: float = 0.0
    respawns: int = 0


class Engine:
    def __init__(self, factory, n_workers, limits, gen_timeout_s=60.0, max_respawns=3):
        self.factory, self.n, self.limits = factory, n_workers, limits
        self.gen_timeout_s, self.max_respawns = gen_timeout_s, max_respawns
        self.heap: list = []
        self.seq = itertools.count()
        self.tids = itertools.count(1)
        self.recent = {p: deque(maxlen=200) for p in (INTERACTIVE, BATCH)}  # (t_done, wait_s, gen_s)
        self.counters = {"done": 0, "errors": 0, "expired": 0, "rejected": 0, "respawned": 0}
        self.startup_error: str | None = None

    async def start(self):
        self.loop = asyncio.get_running_loop()
        self.ctx = mp.get_context("spawn")
        self.result_q = self.ctx.Queue()
        self.wake_ev = asyncio.Event()
        self.first_ready = asyncio.Event()
        self.slots = [Slot(i) for i in range(self.n)]
        for s in self.slots:
            self._spawn(s)
        self.reader = threading.Thread(target=self._read_results, daemon=True)
        self.reader.start()
        self.tasks = [asyncio.create_task(self._dispatcher()), asyncio.create_task(self._watchdog())]

    def _spawn(self, s: Slot):
        s.gen += 1
        s.state, s.job = "starting", None
        s.task_q = self.ctx.Queue()
        s.proc = self.ctx.Process(target=_worker_main, args=(s.idx, s.gen, self.factory, s.task_q, self.result_q),
                                  daemon=True, name=f"f5fi-worker-{s.idx}")
        s.proc.start()

    def _read_results(self):
        while True:
            msg = self.result_q.get()
            if msg is None:
                return
            try:
                self.loop.call_soon_threadsafe(self._on_msg, msg)
            except RuntimeError:  # loop closed during shutdown
                return

    def _on_msg(self, msg):
        kind, idx, gen, tid, data = msg
        s = self.slots[idx]
        if gen != s.gen:
            return  # from a worker that has been replaced
        if kind == "ready":
            s.state = "idle"
            if all(x.state != "starting" for x in self.slots):
                self.first_ready.set()
        elif kind == "failed":
            s.state = "dead"
            self.startup_error = data
            log.error("worker %d failed to start: %s", idx, data)
            self.first_ready.set()
        elif s.job is not None and s.job.tid == tid:
            job, s.job, s.state = s.job, None, "idle"
            if kind == "done":
                wave, sr, job.gen_s = data
                self.counters["done"] += 1
                self.recent[job.prio].append((time.monotonic(), job.wait_s, job.gen_s))
                if not job.fut.done():
                    job.fut.set_result((wave, sr))
            else:
                self.counters["errors"] += 1
                log.warning("worker %d: %s", idx, data)
                if not job.fut.done():
                    job.fut.set_exception(WorkerError(data))
        self.wake_ev.set()

    # -- scheduling

    def alive(self) -> int:
        return sum(1 for s in self.slots if s.state != "dead")

    def waiting(self, prio=None) -> int:
        return sum(1 for _, _, j in self.heap if not j.cancelled and (prio is None or j.prio == prio))

    def busy(self) -> int:
        return sum(1 for s in self.slots if s.state == "busy")

    def avg_gen_s(self) -> float:
        xs = [g for q in self.recent.values() for _, _, g in q]
        return sum(xs) / len(xs) if xs else 2.0

    def submit_many(self, prio, payloads, deadline_s=None) -> list[Job]:
        if self.waiting(prio) + len(payloads) > self.limits[prio]:
            self.counters["rejected"] += 1
            raise QueueFull(max(1, math.ceil(self.avg_gen_s() * (self.waiting() + 1) / max(1, self.alive()))))
        now = time.monotonic()
        jobs = []
        for p in payloads:
            j = Job(next(self.tids), prio, p, self.loop.create_future(), now, now + deadline_s if deadline_s else None)
            heapq.heappush(self.heap, (prio, next(self.seq), j))
            jobs.append(j)
        self.wake_ev.set()
        return jobs

    def cancel(self, job: Job):
        job.cancelled = True
        if not job.fut.done():
            job.fut.cancel()

    async def _dispatcher(self):
        while True:
            await self.wake_ev.wait()
            self.wake_ev.clear()
            while self.heap:
                slot = next((s for s in self.slots if s.state == "idle"), None)
                if slot is None:
                    break
                _, _, job = heapq.heappop(self.heap)
                now = time.monotonic()
                if job.cancelled or job.fut.done():
                    continue
                if job.deadline is not None and now > job.deadline:
                    self.counters["expired"] += 1
                    job.fut.set_exception(JobExpired())
                    continue
                job.wait_s = now - job.t_enq
                slot.state, slot.job, slot.t_busy = "busy", job, now
                slot.task_q.put((job.tid, job.payload))

    async def _watchdog(self):
        while True:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            for s in self.slots:
                if s.state == "dead" or s.proc is None:
                    continue
                if s.state == "busy" and now - s.t_busy > self.gen_timeout_s:
                    log.error("worker %d: generation over %.0f s, killing it", s.idx, self.gen_timeout_s)
                    s.proc.kill()
                if not s.proc.is_alive():
                    job = s.job
                    log.error("worker %d died (exit code %s)", s.idx, s.proc.exitcode)
                    if s.state == "starting":  # a crash while loading is a broken installation: do not retry
                        s.state = "dead"
                        self.startup_error = f"työläinen {s.idx} kaatui käynnistyksessä (koodi {s.proc.exitcode})"
                        self.first_ready.set()
                        continue
                    if job is not None and not job.fut.done():
                        job.fut.set_exception(WorkerError("worker died"))
                    if s.respawns < self.max_respawns:
                        s.respawns += 1
                        self.counters["respawned"] += 1
                        self._spawn(s)
                    else:
                        s.state, s.job = "dead", None
            if self.alive() == 0 and self.first_ready.is_set() and not self.startup_error:
                self.startup_error = "kaikki työläiset kaatuneet"

    async def stop(self):
        for t in self.tasks:
            t.cancel()
        for s in self.slots:
            if s.proc is not None and s.proc.is_alive():
                with contextlib.suppress(Exception):
                    s.task_q.put(None)
        deadline = time.monotonic() + 5
        for s in self.slots:
            if s.proc is not None:
                s.proc.join(max(0.0, deadline - time.monotonic()))
                if s.proc.is_alive():
                    s.proc.kill()
        self.result_q.put(None)

    # -- numbers for /status and admission control

    def recent_wait_p95(self, prio, window_s=60.0):
        now = time.monotonic()
        xs = sorted(w for t, w, _ in self.recent[prio] if now - t <= window_s)
        return xs[min(len(xs) - 1, int(0.95 * len(xs)))] if xs else None

    def stats(self) -> dict:
        def summary(prio):
            xs = list(self.recent[prio])
            if not xs:
                return None
            w, g = sorted(x[1] for x in xs), sorted(x[2] for x in xs)
            q = lambda a, f: round(a[min(len(a) - 1, int(f * len(a)))], 3)  # noqa: E731
            return {"n": len(xs), "wait_p50": q(w, .5), "wait_p95": q(w, .95), "gen_p50": q(g, .5), "gen_p95": q(g, .95)}

        return {"workers": [s.state for s in self.slots], "waiting": {PRIO_NAME[p]: self.waiting(p) for p in PRIO_NAME},
                "recent": {PRIO_NAME[p]: summary(p) for p in PRIO_NAME}, **self.counters}


# ---------------------------------------------------------------- sessions

class Sessions:
    def __init__(self, max_sessions, ttl_s):
        self.max, self.ttl = max_sessions, ttl_s
        self.items: dict[str, float] = {}

    def count(self):
        return len(self.items)

    def open(self) -> str | None:
        if len(self.items) >= self.max:
            return None
        sid = uuid.uuid4().hex
        self.items[sid] = time.monotonic()
        return sid

    def touch(self, sid) -> bool:
        if sid in self.items:
            self.items[sid] = time.monotonic()
            return True
        return False

    def close(self, sid) -> bool:
        return self.items.pop(sid, None) is not None

    def reap(self) -> int:
        now = time.monotonic()
        dead = [s for s, t in self.items.items() if now - t > self.ttl]
        for s in dead:
            del self.items[s]
        return len(dead)


# ---------------------------------------------------------------- configuration and address files

@dataclass
class Config:
    voices_path: str = ""
    state_dir: str = ""
    backend: str = "f5"
    host: str = "0.0.0.0"
    port: int = 0
    advertise_host: str = ""
    workers: int = 1
    max_sessions: int = 4
    session_ttl_s: float = 120.0
    queue_interactive: int = 8
    queue_batch: int = 64
    wait_deadline_s: float = 10.0  # an interactive line that has waited this long is useless: fail it
    admit_wait_limit_s: float = 2.0  # no new sessions while recent interactive waiting is above this
    gen_timeout_s: float = 60.0
    max_chars: int = 600
    max_sentences: int = 8
    batch_max_chars: int = 5000
    keys: dict = field(default_factory=dict)  # role -> key; empty = no authentication (development only)
    addr_heartbeat_s: float = 10.0
    idle_exit_s: float = 0.0  # >0: exit (and free the GPU) after this many seconds without sessions or requests
    term_grace_s: float = 15.0
    drain_max_s: float = 780.0
    gpu_fraction: float = 0.0
    fake_delay: float = 0.2
    fake_load_delay: float = 0.0
    require_voikko: bool = True


def write_json_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- the service

class Service:
    def __init__(self, cfg: Config, voices: dict[str, Voice], factory):
        self.cfg, self.voices = cfg, voices
        self.engine = Engine(factory, cfg.workers, {INTERACTIVE: cfg.queue_interactive, BATCH: cfg.queue_batch},
                             cfg.gen_timeout_s)
        self.sessions = Sessions(cfg.max_sessions, cfg.session_ttl_s)
        self.state = "loading"  # loading | ready | draining | failed
        self.job_id = os.environ.get("SLURM_JOB_ID") or f"local-{os.getpid()}"
        self.started_at = time.time()
        self.expiring = False  # SIGUSR1: the time limit is near
        self.drain_since: float | None = None
        self.exit_code = 0
        self.server = None
        self.tasks: list[asyncio.Task] = []
        self.published = False
        self.last_activity = time.monotonic()

    # -- life cycle

    async def start(self):
        await self.engine.start()
        self.tasks = [asyncio.create_task(self._lifecycle()), asyncio.create_task(self._reaper())]

    async def stop(self):
        for t in self.tasks:
            t.cancel()
        await self.engine.stop()
        if self.cfg.state_dir:
            with contextlib.suppress(OSError):
                os.remove(self._instance_file())
            cur = read_json(self._current_file())
            if cur and cur.get("job_id") == self.job_id:
                with contextlib.suppress(OSError):
                    os.remove(self._current_file())

    def request_exit(self, code=0):
        self.exit_code = code
        if self.server is not None:
            self.server.should_exit = True

    async def _lifecycle(self):
        await self.engine.first_ready.wait()
        if self.engine.startup_error:
            self.state = "failed"
            log.error("käynnistys epäonnistui: %s", self.engine.startup_error)
            self.request_exit(2)
            return
        self.state = "ready"
        self.publish(force=True)
        log.info("valmis: %s (job %s)", self.address()["url"], self.job_id)
        while True:
            await asyncio.sleep(self.cfg.addr_heartbeat_s)
            if self.state == "ready" and self.successor_ready():  # next job (or a manual restart) took over
                self.begin_drain("seuraaja on valmis")
            if (self.state == "ready" and self.cfg.idle_exit_s and self._idle()
                    and time.monotonic() - self.last_activity > self.cfg.idle_exit_s):
                log.info("ei käyttöä %.0f sekuntiin: sammutaan ja vapautetaan GPU", self.cfg.idle_exit_s)
                self.begin_drain("ei käyttöä")
                self.request_exit(0)
            if self.state == "draining" and self._idle() and time.monotonic() - self.drain_since > 3:
                log.info("tyhjä ja tyhjennystilassa: sammutaan")
                self.request_exit(0)
            if self.state == "draining" and time.monotonic() - self.drain_since > self.cfg.drain_max_s:
                log.info("tyhjennysaika täynnä: sammutaan")
                self.request_exit(0)
            if self.engine.startup_error:  # all workers lost later on
                self.state = "failed"
                self.request_exit(3)
                return
            self.publish()

    async def _reaper(self):
        while True:
            await asyncio.sleep(5)
            n = self.sessions.reap()
            if n:
                log.info("%d istuntoa vanheni (ei sydämenlyöntiä)", n)

    def _idle(self) -> bool:
        return self.sessions.count() == 0 and self.engine.busy() == 0 and self.engine.waiting() == 0

    def begin_drain(self, reason):
        if self.state != "ready":
            return
        self.state = "draining"
        self.drain_since = time.monotonic()
        log.info("tyhjennystila: %s", reason)
        self.publish()

    def on_usr1(self):
        """Slurm warns that the time limit is near (--signal=B:USR1@...)."""
        self.expiring = True
        log.info("SIGUSR1: aikaraja lähestyy%s", "" if self.successor_ready() else " (seuraajaa ei ole vielä valmiina)")
        if self.successor_ready():
            self.begin_drain("seuraaja on valmis")

    def on_term(self):
        """scancel or the time limit: finish what is running, then stop. Slurm kills after KillWait (30 s by default)."""
        log.info("SIGTERM: sammutetaan")
        if self.state in ("ready", "loading"):
            self.state = "draining" if self.state == "ready" else "failed"
            self.drain_since = time.monotonic()
            self.publish()
        asyncio.get_running_loop().create_task(self._term_wait())

    async def _term_wait(self):
        t0 = time.monotonic()
        while time.monotonic() - t0 < self.cfg.term_grace_s and (self.engine.busy() or self.engine.waiting()):
            await asyncio.sleep(0.2)
        self.request_exit(0)

    # -- address files

    def _instance_file(self):
        return os.path.join(self.cfg.state_dir, f"{self.job_id}.json")

    def _current_file(self):
        return os.path.join(self.cfg.state_dir, "current.json")

    def address(self) -> dict:
        host = self.cfg.advertise_host or os.environ.get("SLURMD_NODENAME") or socket.gethostname()
        return {"version": 1, "job_id": self.job_id, "status": self.state, "host": host, "port": self.cfg.port,
                "url": f"http://{host}:{self.cfg.port}", "pid": os.getpid(), "started_at": self.started_at,
                "updated_at": time.time(), "max_sessions": self.cfg.max_sessions, "voices": sorted(self.voices)}

    def publish(self, force=False):
        """Instance file always; current.json (the one clients read) only at the first time, then only while it is
        still ours, so that an old instance never overwrites its successor."""
        if not self.cfg.state_dir or self.state not in ("ready", "draining"):
            return
        addr = self.address()
        write_json_atomic(self._instance_file(), addr)
        cur = read_json(self._current_file())
        if force or cur is None or cur.get("job_id") == self.job_id:
            write_json_atomic(self._current_file(), addr)

    def successor_ready(self) -> bool:
        if not self.cfg.state_dir:
            return False
        cur = read_json(self._current_file())
        return bool(cur and cur.get("job_id") != self.job_id and cur.get("status") == "ready"
                    and time.time() - cur.get("updated_at", 0) < 3 * self.cfg.addr_heartbeat_s + 5)

    # -- numbers

    def status(self) -> dict:
        return {"state": self.state, "job_id": self.job_id, "sessions": self.sessions.count(),
                "max_sessions": self.cfg.max_sessions, "expiring": self.expiring, **self.engine.stats()}


# ---------------------------------------------------------------- HTTP

class SpeakReq(BaseModel):
    voice: str
    text: str
    emotion: str | None = None
    session_id: str | None = None
    seed: int | None = None
    nfe: int | None = Field(None, ge=4, le=64)


def create_app(svc: Service) -> FastAPI:
    cfg = svc.cfg

    @contextlib.asynccontextmanager
    async def lifespan(app):
        await svc.start()
        try:
            yield
        finally:
            await svc.stop()

    app = FastAPI(title="F5-fi puhepalvelu", lifespan=lifespan)

    def auth(request: Request) -> str:
        if not cfg.keys:
            return request.headers.get("x-role", "interactive")
        header = request.headers.get("authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else ""
        for role, key in cfg.keys.items():
            if hmac.compare_digest(token.encode(), key.encode()):
                return role
        raise HTTPException(401, "virheellinen tai puuttuva avain", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/healthz")
    async def healthz(response: Response):
        ok = svc.state in ("ready", "draining") and svc.engine.alive() > 0
        response.status_code = 200 if ok else 503
        return {"status": svc.state}

    @app.get("/status")
    async def status(request: Request):
        auth(request)
        return svc.status()

    @app.get("/voices")
    async def voices(request: Request):
        auth(request)
        return {n: {"default_emotion": v.default_emotion, "emotions": sorted(v.emotions)} for n, v in svc.voices.items()}

    @app.post("/sessions", status_code=201)
    async def open_session(request: Request):
        if auth(request) != "interactive":
            raise HTTPException(403, "istunnot ovat reaaliaikaiselle avaimelle")
        if svc.state != "ready":
            raise HTTPException(503, {"detail": svc.state})
        if svc.engine.alive() == 0:
            raise HTTPException(503, {"detail": "no_workers"})
        p95 = svc.engine.recent_wait_p95(INTERACTIVE)
        if p95 is not None and p95 > cfg.admit_wait_limit_s:
            raise HTTPException(429, {"detail": "overloaded", "wait_p95": round(p95, 2)}, headers={"Retry-After": "10"})
        svc.last_activity = time.monotonic()
        sid = svc.sessions.open()
        if sid is None:
            raise HTTPException(429, {"detail": "full", "active": svc.sessions.count(), "max": cfg.max_sessions},
                                headers={"Retry-After": "15"})
        return {"session_id": sid, "ttl_s": cfg.session_ttl_s, "heartbeat_every_s": cfg.session_ttl_s / 3}

    @app.post("/sessions/{sid}/heartbeat")
    async def heartbeat(sid: str, request: Request):
        auth(request)
        if not svc.sessions.touch(sid):
            raise HTTPException(410, "istunto on päättynyt")
        return {"ok": True}

    @app.delete("/sessions/{sid}")
    async def close_session(sid: str, request: Request):
        auth(request)
        svc.sessions.close(sid)
        return {"ok": True}

    @app.post("/speak")
    async def speak(req: SpeakReq, request: Request):
        role = auth(request)
        if svc.state not in ("ready", "draining"):
            raise HTTPException(503, {"detail": svc.state})
        voice = svc.voices.get(req.voice.strip().lower())
        if voice is None:
            raise HTTPException(404, {"detail": "unknown_voice", "voices": sorted(svc.voices)})
        emo_name, emo = voice.pick(req.emotion)
        prio = INTERACTIVE if role == "interactive" else BATCH
        if prio == INTERACTIVE and not (req.session_id and svc.sessions.touch(req.session_id)):
            raise HTTPException(410, {"detail": "no_session"})
        svc.last_activity = time.monotonic()
        text = clean_text(req.text)
        max_chars = cfg.max_chars if prio == INTERACTIVE else cfg.batch_max_chars
        sentences = split_sentences(text)
        if not sentences:
            raise HTTPException(422, {"detail": "empty_text"})
        if len(text) > max_chars or (prio == INTERACTIVE and len(sentences) > cfg.max_sentences):
            raise HTTPException(422, {"detail": "too_long", "max_chars": max_chars, "max_sentences": cfg.max_sentences})
        seed = emo.seed if req.seed is None else req.seed
        nfe = req.nfe or emo.nfe or 32
        payloads = [{"voice": voice.name, "emotion": emo_name, "text": s, "seed": seed, "nfe": nfe} for s in sentences]
        try:
            jobs = svc.engine.submit_many(prio, payloads, cfg.wait_deadline_s if prio == INTERACTIVE else None)
        except QueueFull as e:
            raise HTTPException(429, {"detail": "queue_full"}, headers={"Retry-After": str(e.retry_after)}) from None
        try:
            results = await asyncio.gather(*(j.fut for j in jobs), return_exceptions=True)
        finally:
            for j in jobs:
                if not j.fut.done():
                    svc.engine.cancel(j)
        for r in results:
            if isinstance(r, JobExpired):
                raise HTTPException(503, {"detail": "waited_too_long"}, headers={"Retry-After": "2"})
            if isinstance(r, BaseException):
                raise HTTPException(503, {"detail": "synthesis_failed"}, headers={"Retry-After": "2"})
        sr = results[0][1]
        parts = []
        for k, (wave, _) in enumerate(results):
            if k:
                parts.append(np.zeros(int(SENTENCE_PAUSE_S * sr), np.float32))
            parts.append(wave)
        audio = np.concatenate(parts)
        buf = io.BytesIO()
        sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
        wait, gen = max(j.wait_s for j in jobs), sum(j.gen_s for j in jobs)
        log.info("speak %s/%s %d merkkiä, %d lausetta, odotus %.2f s, generointi %.2f s", voice.name, emo_name, len(text),
                 len(sentences), wait, gen)
        return Response(buf.getvalue(), media_type="audio/wav", headers={
            "X-Voice": voice.name, "X-Emotion": emo_name, "X-Seed": str(seed), "X-Sentences": str(len(sentences)),
            "X-Duration-S": f"{len(audio) / sr:.2f}", "X-Wait-S": f"{wait:.3f}", "X-Gen-S": f"{gen:.3f}"})

    return app


# ---------------------------------------------------------------- start-up

class _Server(uvicorn.Server):
    def capture_signals(self):  # we handle SIGTERM/SIGINT/SIGUSR1 ourselves (Service.on_term, on_usr1)
        return contextlib.nullcontext()


def check_voikko() -> bool:
    import rajageminaatio

    return rajageminaatio._analyzer() is not None


def load_keys(path: str | None) -> dict:
    if path:
        with open(path, encoding="utf-8") as f:
            keys = json.load(f)
    else:
        keys = {r: os.environ[f"F5SERVE_KEY_{r.upper()}"] for r in ("interactive", "batch")
                if os.environ.get(f"F5SERVE_KEY_{r.upper()}")}
    return {r: k for r, k in keys.items() if r in ("interactive", "batch") and len(k) >= 16}


def parse_args(argv=None) -> tuple[Config, argparse.Namespace]:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    d = Config()
    ap.add_argument("--voices", required=True, help="äänirekisteri (JSON), katso slurm/voices.example.json")
    ap.add_argument("--state-dir", default=os.environ.get("F5SERVE_STATE_DIR", ""), help="kansio, johon osoite kirjoitetaan")
    ap.add_argument("--keys-file", default=os.environ.get("F5SERVE_KEYS_FILE"), help='JSON {"interactive": "...", "batch": "..."}')
    ap.add_argument("--no-auth", action="store_true", help="ei avaimia (vain kehitys)")
    ap.add_argument("--backend", choices=["f5", "fake"], default="f5")
    ap.add_argument("--host", default=d.host)
    ap.add_argument("--port", type=int, default=d.port, help="0 = vapaa portti")
    ap.add_argument("--advertise-host", default="", help="osoitetiedostoon kirjoitettava nimi (oletus: solmun nimi)")
    ap.add_argument("--workers", type=int, default=d.workers, help="työläisiä (malli ladataan jokaiselle)")
    ap.add_argument("--max-sessions", type=int, default=d.max_sessions)
    ap.add_argument("--session-ttl", type=float, default=d.session_ttl_s, dest="session_ttl_s")
    ap.add_argument("--queue-interactive", type=int, default=d.queue_interactive)
    ap.add_argument("--queue-batch", type=int, default=d.queue_batch)
    ap.add_argument("--wait-deadline", type=float, default=d.wait_deadline_s, dest="wait_deadline_s")
    ap.add_argument("--admit-wait-limit", type=float, default=d.admit_wait_limit_s, dest="admit_wait_limit_s")
    ap.add_argument("--gen-timeout", type=float, default=d.gen_timeout_s, dest="gen_timeout_s")
    ap.add_argument("--addr-heartbeat", type=float, default=d.addr_heartbeat_s, dest="addr_heartbeat_s",
                    help="osoitetiedoston päivitysväli sekunteina (asiakas pitää yli 3× vanhaa tiedostoa vanhentuneena)")
    ap.add_argument("--gpu-fraction", type=float, default=0.0, help="GPU-muistin osuus per työläinen (0 = ei rajaa)")
    ap.add_argument("--term-grace", type=float, default=d.term_grace_s, dest="term_grace_s")
    ap.add_argument("--drain-max", type=float, default=d.drain_max_s, dest="drain_max_s")
    ap.add_argument("--idle-exit", type=float, default=0.0, dest="idle_exit_s",
                    help="sammu, kun palvelua ei ole käytetty näin moneen sekuntiin (0 = ei koskaan)")
    ap.add_argument("--allow-no-voikko", action="store_true", help="käynnistä vaikka Voikkoa ei löydy (kahdennussäännöt jäävät pois)")
    ap.add_argument("--fake-delay", type=float, default=d.fake_delay)
    ap.add_argument("--fake-load-delay", type=float, default=d.fake_load_delay)
    a = ap.parse_args(argv)
    cfg = Config(voices_path=a.voices, state_dir=a.state_dir, backend=a.backend, host=a.host, port=a.port,
                 advertise_host=a.advertise_host, workers=a.workers, max_sessions=a.max_sessions,
                 session_ttl_s=a.session_ttl_s, queue_interactive=a.queue_interactive, queue_batch=a.queue_batch,
                 wait_deadline_s=a.wait_deadline_s, admit_wait_limit_s=a.admit_wait_limit_s, gen_timeout_s=a.gen_timeout_s,
                 term_grace_s=a.term_grace_s, drain_max_s=a.drain_max_s, gpu_fraction=a.gpu_fraction,
                 addr_heartbeat_s=a.addr_heartbeat_s, idle_exit_s=a.idle_exit_s,
                 fake_delay=a.fake_delay, fake_load_delay=a.fake_load_delay, require_voikko=not a.allow_no_voikko)
    cfg.keys = {} if a.no_auth else load_keys(a.keys_file)
    if not a.no_auth and not cfg.keys:
        ap.error("avaimia ei löytynyt: anna --keys-file (tai F5SERVE_KEY_INTERACTIVE/_BATCH, vähintään 16 merkkiä) tai --no-auth")
    return cfg, a


def main(argv=None) -> int:
    cfg, _ = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    fake = cfg.backend == "fake"
    voices = load_registry(cfg.voices_path, check_files=not fake)
    if not fake and cfg.require_voikko and not check_voikko():
        log.error("Voikko ei ole käytettävissä: kahdennussäännöt jäisivät hiljaa pois. Aseta VOIKKO_LIB_DIR ja "
                  "VOIKKO_DICT_DIR (slurm/install.sh) tai käytä --allow-no-voikko.")
        return 2
    if fake:
        factory = functools.partial(FakeBackend, cfg.voices_path, cfg.fake_delay, cfg.fake_load_delay)
    else:
        factory = functools.partial(F5Backend, cfg.voices_path, cfg.gpu_fraction)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((cfg.host, cfg.port))
    cfg.port = sock.getsockname()[1]
    svc = Service(cfg, voices, factory)
    server = _Server(uvicorn.Config(create_app(svc), log_level="info", access_log=False, timeout_graceful_shutdown=5))
    svc.server = server

    async def run():
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, svc.on_term)
        loop.add_signal_handler(signal.SIGINT, svc.on_term)
        loop.add_signal_handler(signal.SIGUSR1, svc.on_usr1)
        await server.serve(sockets=[sock])

    log.info("kuuntelee %s:%d, %d työläistä, %d ääntä", cfg.host, cfg.port, cfg.workers, len(voices))
    asyncio.run(run())
    return svc.exit_code


if __name__ == "__main__":
    sys.exit(main())
