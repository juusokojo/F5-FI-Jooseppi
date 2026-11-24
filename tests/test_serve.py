"""Tests for scripts/serve.py with the fake backend: no model, no GPU. Starts real worker processes (spawn)."""
import asyncio
import functools
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import serve  # noqa: E402
import soundfile as sf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SERVE_PY = os.path.join(os.path.dirname(serve.__file__), "serve.py")
VOICES = {
    "voices": {
        "Jooseppi": {"default_emotion": "neutraali", "emotions": {
            "neutraali": {"ref": "a.wav", "seed": 1}, "Iloinen": {"ref": "b.wav", "seed": 4}}},
        "Valdemar": {"ckpt": "checkpoints/valdemar.safetensors", "emotions": {"neutraali": {"ref": "c.wav"}}},
    }
}


def write_voices(d, data=VOICES):
    path = os.path.join(d, "voices.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def wait_for(cond, timeout=30.0, step=0.1):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        v = cond()
        if v:
            return v
        time.sleep(step)
    raise AssertionError("ehto ei täyttynyt ajassa")


class Harness:
    """A Service with fake workers behind a TestClient."""

    def __init__(self, tmp, **kw):
        self.vpath = write_voices(tmp)
        kw.setdefault("workers", 1)
        kw.setdefault("fake_delay", 0.05)
        self.cfg = serve.Config(voices_path=self.vpath, state_dir=os.path.join(tmp, "state"), backend="fake",
                                addr_heartbeat_s=0.3, **kw)
        voices = serve.load_registry(self.vpath, check_files=False)
        factory = functools.partial(serve.FakeBackend, self.vpath, self.cfg.fake_delay, 0.0)
        self.svc = serve.Service(self.cfg, voices, factory)
        self.client = TestClient(serve.create_app(self.svc))

    def __enter__(self):
        self.client.__enter__()
        wait_for(lambda: self.client.get("/healthz").status_code == 200)
        return self

    def __exit__(self, *a):
        self.client.__exit__(*a)

    def session(self):
        r = self.client.post("/sessions")
        self.assertion = r
        return r.json().get("session_id")

    def speak(self, sid, text="Hei vaan.", **kw):
        return self.client.post("/speak", json={"voice": "Jooseppi", "text": text, "session_id": sid, **kw})


class TestText(unittest.TestCase):
    def test_clean_text_strips_what_cannot_be_spoken(self):
        self.assertEqual(serve.clean_text("*huokaisee* Kyllä **tiedän**, [naurahtaa] mutta 😀 ei!"), "Kyllä tiedän, mutta ei!")
        self.assertEqual(serve.clean_text("  Hei\n\n  maailma. "), "Hei maailma.")

    def test_split_sentences(self):
        self.assertEqual(serve.split_sentences("Hei. Mitä kuuluu? Hyvää!"), ["Hei.", "Mitä kuuluu?", "Hyvää!"])
        self.assertEqual(serve.split_sentences("No? hän kysyi."), ["No? hän kysyi."])  # same rule as read_text.py
        self.assertEqual(serve.split_sentences("..."), [])

    def test_same_split_as_read_text(self):
        try:
            import read_text
        except Exception as e:  # noqa: BLE001 - torch missing etc.
            self.skipTest(str(e))
        for t in ["Hei. Mitä kuuluu? Hyvää!", "– Kyllä. – Ei.", "No? hän kysyi. Sitten hän lähti."]:
            self.assertEqual(serve.split_sentences(t), read_text.sentences(t))


class TestRegistry(unittest.TestCase):
    def test_load_and_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            voices = serve.load_registry(write_voices(d), check_files=False)
        self.assertEqual(sorted(voices), ["jooseppi", "valdemar"])
        self.assertEqual(voices["jooseppi"].pick("ILOINEN")[0], "iloinen")
        self.assertEqual(voices["jooseppi"].pick("raivoisa")[0], "neutraali")  # unknown -> default
        self.assertEqual(voices["jooseppi"].pick(None)[0], "neutraali")
        self.assertEqual(voices["jooseppi"].emotions["iloinen"].seed, 4)
        self.assertEqual(voices["valdemar"].ckpt, os.path.join(serve.ROOT, "checkpoints/valdemar.safetensors"))
        self.assertEqual(voices["jooseppi"].ckpt, "default")

    def test_bad_default_emotion(self):
        bad = {"voices": {"X": {"default_emotion": "puuttuu", "emotions": {"a": {"ref": "a.wav"}}}}}
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            serve.load_registry(write_voices(d, bad), check_files=False)

    def test_missing_reference_is_caught_at_start(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            serve.load_registry(write_voices(d))


class TestSessions(unittest.TestCase):
    def test_capacity_touch_and_reap(self):
        s = serve.Sessions(2, ttl_s=0.2)
        a, b = s.open(), s.open()
        self.assertIsNone(s.open())  # full
        self.assertTrue(s.touch(a))
        time.sleep(0.25)
        self.assertEqual(s.reap(), 2)
        self.assertFalse(s.touch(b))
        self.assertIsNotNone(s.open())  # the places are free again
        self.assertTrue(s.close(s.open()))


class TestEngine(unittest.TestCase):
    def test_interactive_overtakes_batch_between_sentences(self):
        async def go():
            factory = functools.partial(serve.FakeBackend, None, 0.15, 0.0)
            eng = serve.Engine(factory, 1, {serve.INTERACTIVE: 8, serve.BATCH: 64})
            await eng.start()
            await asyncio.wait_for(eng.first_ready.wait(), 30)
            p = {"voice": "x", "emotion": "y", "text": "lause", "seed": 1, "nfe": 8}
            batch = eng.submit_many(serve.BATCH, [dict(p) for _ in range(6)])
            await asyncio.sleep(0.05)  # the first batch sentence is running
            inter = eng.submit_many(serve.INTERACTIVE, [dict(p)])
            order = []
            for name, jobs in (("inter", inter), ("batch", batch)):
                for j in jobs:
                    j.fut.add_done_callback(lambda f, n=name: order.append(n))
            await asyncio.gather(*(j.fut for j in batch + inter))
            await eng.stop()
            return order

        order = asyncio.run(go())
        self.assertLess(order.index("inter"), 3)  # after at most the running sentence and one more, not after all six

    def test_queue_limit(self):
        async def go():
            eng = serve.Engine(functools.partial(serve.FakeBackend, None, 0.3, 0.0), 1, {0: 2, 1: 2})
            await eng.start()
            await asyncio.wait_for(eng.first_ready.wait(), 30)
            p = {"voice": "x", "emotion": "y", "text": "lause", "seed": 1, "nfe": 8}
            jobs = eng.submit_many(0, [p, p])
            with self.assertRaises(serve.QueueFull) as cm:
                eng.submit_many(0, [p])
            self.assertGreaterEqual(cm.exception.retry_after, 1)
            await asyncio.gather(*(j.fut for j in jobs))
            await eng.stop()

        asyncio.run(go())


class TestHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.h = Harness(cls.tmp.name, workers=2, max_sessions=2, queue_interactive=4)
        cls.h.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.h.__exit__(None, None, None)
        cls.tmp.cleanup()

    def test_speak_returns_wav_with_headers(self):
        c = self.h.client
        sid = self.h.session()
        r = self.h.speak(sid, "Hei vaan. Mitä kuuluu?", emotion="iloinen")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["content-type"], "audio/wav")
        self.assertEqual((r.headers["x-voice"], r.headers["x-emotion"], r.headers["x-seed"]), ("jooseppi", "iloinen", "4"))
        self.assertEqual(r.headers["x-sentences"], "2")
        data, sr = sf.read(io.BytesIO(r.content))
        self.assertEqual(sr, 24000)
        self.assertAlmostEqual(len(data) / sr, float(r.headers["x-duration-s"]), places=1)
        one = self.h.speak(sid, "Hei vaan.").headers["x-duration-s"]
        self.assertGreater(float(r.headers["x-duration-s"]), float(one) + serve.SENTENCE_PAUSE_S)  # pause between sentences
        c.delete(f"/sessions/{sid}")

    def test_unknown_emotion_falls_back_unknown_voice_fails(self):
        sid = self.h.session()
        r = self.h.speak(sid, emotion="raivoisa")
        self.assertEqual((r.status_code, r.headers["x-emotion"]), (200, "neutraali"))
        r = self.h.client.post("/speak", json={"voice": "Kalle", "text": "Hei.", "session_id": sid})
        self.assertEqual(r.status_code, 404)
        self.assertIn("jooseppi", r.json()["detail"]["voices"])
        self.h.client.delete(f"/sessions/{sid}")

    def test_session_rules(self):
        c = self.h.client
        self.assertEqual(self.h.speak(None).status_code, 410)  # no session
        self.assertEqual(self.h.speak("olematon").status_code, 410)
        a, b = self.h.session(), self.h.session()
        r = c.post("/sessions")
        self.assertEqual(r.status_code, 429)  # max_sessions = 2
        self.assertIn("retry-after", r.headers)
        self.assertEqual(c.post(f"/sessions/{a}/heartbeat").status_code, 200)
        c.delete(f"/sessions/{a}")
        self.assertEqual(c.post(f"/sessions/{a}/heartbeat").status_code, 410)
        c2 = c.post("/sessions")
        self.assertEqual(c2.status_code, 201)  # the place was freed
        for s in (b, c2.json()["session_id"]):
            c.delete(f"/sessions/{s}")

    def test_text_limits_and_cleaning(self):
        sid = self.h.session()
        self.assertEqual(self.h.speak(sid, "*huokaisee* 😀").status_code, 422)  # nothing left to say
        self.assertEqual(self.h.speak(sid, "Hei. " * 9).status_code, 422)  # over max_sentences
        self.assertEqual(self.h.speak(sid, "a" * 700).status_code, 422)  # over max_chars
        self.assertEqual(self.h.speak(sid, "*huokaisee* Hei vaan.").status_code, 200)
        self.h.client.delete(f"/sessions/{sid}")

    def test_queue_full_is_429_with_retry_after(self):
        sid = self.h.session()
        r = self.h.speak(sid, "Yksi. Kaksi. Kolme. Neljä. Viisi.")  # 5 sentences > queue_interactive 4
        self.assertEqual(r.status_code, 429)
        self.assertGreaterEqual(int(r.headers["retry-after"]), 1)
        self.h.client.delete(f"/sessions/{sid}")

    def test_voices_and_status(self):
        v = self.h.client.get("/voices").json()
        self.assertEqual(v["jooseppi"]["emotions"], ["iloinen", "neutraali"])
        s = self.h.client.get("/status").json()
        self.assertEqual(s["state"], "ready")
        self.assertEqual(s["workers"], ["idle", "idle"])

    def test_worker_error_does_not_stop_service(self):
        sid = self.h.session()
        r = self.h.speak(sid, "Tässä on VIRHE.")
        self.assertEqual((r.status_code, r.json()["detail"]["detail"]), (503, "synthesis_failed"))
        self.assertEqual(self.h.speak(sid, "Tämä onnistuu.").status_code, 200)
        self.h.client.delete(f"/sessions/{sid}")

    def test_adaptive_admission_when_waiting_is_long(self):
        e = self.h.svc.engine
        e.recent[serve.INTERACTIVE].append((time.monotonic(), 5.0, 1.0))
        try:
            r = self.h.client.post("/sessions")
            self.assertEqual((r.status_code, r.json()["detail"]["detail"]), (429, "overloaded"))
        finally:
            e.recent[serve.INTERACTIVE].clear()
        sid = self.h.session()
        self.assertIsNotNone(sid)
        self.h.client.delete(f"/sessions/{sid}")


class TestFailureModes(unittest.TestCase):
    def test_crashed_worker_is_replaced(self):
        with tempfile.TemporaryDirectory() as d, Harness(d) as h:
            sid = h.session()
            self.assertEqual(h.speak(sid, "Kaadan KAATUMINEN prosessin.").status_code, 503)
            wait_for(lambda: h.svc.engine.slots[0].state == "idle")  # respawned and loaded again
            self.assertEqual(h.speak(sid, "Taas toimii.").status_code, 200)
            self.assertEqual(h.client.get("/status").json()["respawned"], 1)

    def test_hung_worker_is_killed_after_timeout(self):
        with tempfile.TemporaryDirectory() as d, Harness(d, gen_timeout_s=1.0) as h:
            sid = h.session()
            t0 = time.monotonic()
            self.assertEqual(h.speak(sid, "Tämä on JUMI.").status_code, 503)
            self.assertLess(time.monotonic() - t0, 10)
            wait_for(lambda: h.svc.engine.slots[0].state == "idle")
            self.assertEqual(h.speak(sid, "Taas toimii.").status_code, 200)

    def test_line_that_waited_too_long_is_dropped(self):
        with tempfile.TemporaryDirectory() as d, Harness(d, fake_delay=0.8, wait_deadline_s=0.3, max_sessions=3) as h:
            sids = [h.session() for _ in range(2)]
            with ThreadPoolExecutor(2) as ex:
                first = ex.submit(h.speak, sids[0])
                time.sleep(0.2)
                second = ex.submit(h.speak, sids[1])
                codes = (first.result().status_code, second.result().status_code)
            self.assertEqual(codes, (200, 503))  # the second line would have been late: not spoken
            self.assertEqual(h.client.get("/status").json()["expired"], 1)


class TestAuth(unittest.TestCase):
    def test_keys(self):
        with tempfile.TemporaryDirectory() as d:
            h = Harness(d)
            h.cfg.keys = {"interactive": "i" * 20, "batch": "b" * 20}
            with h:
                c = h.client
                self.assertEqual(c.get("/healthz").status_code, 200)  # open for monitoring
                self.assertEqual(c.get("/status").status_code, 401)
                self.assertEqual(c.get("/status", headers={"Authorization": "Bearer vaara"}).status_code, 401)
                inter, batch = {"Authorization": "Bearer " + "i" * 20}, {"Authorization": "Bearer " + "b" * 20}
                self.assertEqual(c.get("/status", headers=inter).status_code, 200)
                self.assertEqual(c.post("/sessions", headers=batch).status_code, 403)  # sessions are for the live key
                # the batch key needs no session and uses the batch queue
                r = c.post("/speak", headers=batch, json={"voice": "valdemar", "text": "Erä-ajo."})
                self.assertEqual((r.status_code, r.headers["x-voice"]), (200, "valdemar"))

    def test_server_refuses_to_start_without_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.run([sys.executable, SERVE_PY, "--voices", write_voices(d), "--backend", "fake"],
                               capture_output=True, text=True, timeout=60, env={**os.environ, "F5SERVE_KEYS_FILE": ""})
            self.assertEqual(p.returncode, 2)
            self.assertIn("avaimia ei löytynyt", p.stderr)


class TestContract(unittest.TestCase):
    """The interface Rooliharjoittelu expects: osoite.json, avain, GET /health, POST /synthesize."""

    @staticmethod
    def harness(d, **kw):
        h = Harness(d, **kw)
        h.cfg.contract_dir = os.path.join(d, ".f5-palvelu")
        h.key = serve.write_contract_key(h.cfg.contract_dir)
        h.cfg.keys = {"interactive": h.key}
        h.headers = {"Authorization": "Bearer " + h.key}
        return h

    def test_files_and_health(self):
        import datetime

        with tempfile.TemporaryDirectory() as d:
            h = self.harness(d)
            cdir = h.cfg.contract_dir
            key_file, addr_file = os.path.join(cdir, "avain"), os.path.join(cdir, "osoite.json")
            with h:
                with open(key_file, encoding="utf-8") as f:
                    self.assertEqual(f.read(), h.key)  # the key alone, no newline
                self.assertEqual(os.stat(key_file).st_mode & 0o777, 0o600)
                self.assertEqual(os.stat(addr_file).st_mode & 0o777, 0o600)
                with open(addr_file, encoding="utf-8") as f:
                    addr = json.load(f)
                self.assertEqual(sorted(addr), ["job", "started", "url"])
                self.assertTrue(addr["url"].startswith("http://"))
                datetime.datetime.fromisoformat(addr["started"])
                r = h.client.get("/health")  # no key needed
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json(), {"ok": True, "voices": ["jooseppi", "valdemar"], "queue": 0})
            self.assertFalse(os.path.exists(addr_file))  # removed on exit
            self.assertTrue(os.path.exists(key_file))  # the key stays

    def test_synthesize_returns_mono_16bit_24k_wav(self):
        with tempfile.TemporaryDirectory() as d, self.harness(d) as h:
            body = {"voice": "Jooseppi", "clip": "iloinen", "text": "Hei vaan. Mitä kuuluu?", "seed": 7}
            r = h.client.post("/synthesize", json=body, headers=h.headers)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.headers["content-type"], "audio/wav")
            info = sf.info(io.BytesIO(r.content))
            self.assertEqual((info.channels, info.samplerate, info.subtype), (1, 24000, "PCM_16"))
            self.assertEqual(r.headers["x-seed"], "7")
            del body["seed"]
            r = h.client.post("/synthesize", json=body, headers=h.headers)
            self.assertEqual(r.headers["x-seed"], "4")  # the clip's own default seed

    def test_errors_are_json_with_error_field(self):
        with tempfile.TemporaryDirectory() as d, self.harness(d, queue_interactive=3) as h:
            post = lambda body, headers=None: h.client.post("/synthesize", json=body, headers=h.headers if headers is None else headers)  # noqa: E731
            ok = {"voice": "jooseppi", "clip": "neutraali", "text": "Hei."}
            cases = [
                (401, post(ok, headers={})),
                (401, post(ok, headers={"Authorization": "Bearer vaara"})),
                (400, post({**ok, "voice": "kalle"})),  # unknown voice
                (400, post({**ok, "clip": "raivoisa"})),  # unknown clip is an error here, not a fallback
                (400, post({"voice": "jooseppi", "clip": "neutraali"})),  # no text
                (400, post({**ok, "seed": "yksi"})),
                (400, post({**ok, "text": "*huokaisee* 😀"})),  # nothing left to say
                (400, post({**ok, "text": "Yksi. Kaksi. Kolme. Neljä."})),  # more sentences than the queue holds
            ]
            for want, r in cases:
                self.assertEqual(r.status_code, want, r.text)
                self.assertIsInstance(r.json()["error"], str)
            r = h.client.post("/synthesize", content=b"ei json", headers=h.headers)
            self.assertEqual((r.status_code, "error" in r.json()), (400, True))
            self.assertIn("neutraali", post({**ok, "clip": "x"}).json()["error"])  # tells what exists

    def test_full_queue_is_503_with_retry_after(self):
        with tempfile.TemporaryDirectory() as d, self.harness(d, fake_delay=0.8, queue_interactive=1) as h:
            body = {"voice": "jooseppi", "clip": "neutraali", "text": "Hei vaan."}
            with ThreadPoolExecutor(3) as ex:
                futs = []
                for _ in range(3):  # one running, one waiting, the third finds the queue full
                    futs.append(ex.submit(h.client.post, "/synthesize", json=body, headers=h.headers))
                    time.sleep(0.2)
                rs = [f.result() for f in futs]
            self.assertEqual(sorted(r.status_code for r in rs), [200, 200, 503])
            busy = next(r for r in rs if r.status_code == 503)
            self.assertGreaterEqual(int(busy.headers["retry-after"]), 1)
            self.assertIsInstance(busy.json()["error"], str)

    def test_real_process_writes_and_removes_the_files(self):
        import httpx

        with tempfile.TemporaryDirectory() as d:
            cdir = os.path.join(d, ".f5-palvelu")
            proc = subprocess.Popen([sys.executable, SERVE_PY, "--voices", write_voices(d), "--backend", "fake",
                                     "--contract-dir", cdir, "--addr-heartbeat", "0.3"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    env={**os.environ, "F5SERVE_KEYS_FILE": "", "SLURM_JOB_ID": "4242"})
            self.addCleanup(lambda: proc.poll() is None and proc.kill())
            addr_file = os.path.join(cdir, "osoite.json")
            addr = wait_for(lambda: TestLifecycle.read(addr_file), 60)
            self.assertEqual(addr["job"], 4242)  # a number, as in {"url": ..., "job": <työnumero>, "started": ...}
            with open(os.path.join(cdir, "avain"), encoding="utf-8") as f:
                key = f.read()
            self.assertGreaterEqual(len(key), 32)
            self.assertEqual(httpx.get(addr["url"] + "/health").json()["ok"], True)
            body = {"voice": "valdemar", "clip": "neutraali", "text": "Moi."}
            self.assertEqual(httpx.post(addr["url"] + "/synthesize", json=body).status_code, 401)
            r = httpx.post(addr["url"] + "/synthesize", json=body, headers={"Authorization": f"Bearer {key}"})
            self.assertEqual(r.status_code, 200)
            proc.send_signal(signal.SIGTERM)
            self.assertEqual(proc.wait(30), 0)
            self.assertEqual(os.listdir(cdir), ["avain"])  # address and instance files gone, the key stays


class TestPuhepalveluClient(unittest.TestCase):
    """scripts/puhepalvelu_client.py against the real server process (fake backend)."""

    def start(self, d, *extra):
        cdir = os.path.join(d, ".f5-palvelu")
        proc = subprocess.Popen([sys.executable, SERVE_PY, "--voices", write_voices(d), "--backend", "fake",
                                 "--contract-dir", cdir, "--addr-heartbeat", "0.3", *extra],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                env={**os.environ, "F5SERVE_KEYS_FILE": ""})
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        wait_for(lambda: TestLifecycle.read(os.path.join(cdir, "osoite.json")), 60)
        return proc, cdir

    def test_speak_errors_and_voices(self):
        import puhepalvelu_client as pc

        with tempfile.TemporaryDirectory() as d:
            proc, cdir = self.start(d)
            c = pc.Puhepalvelu(cdir)
            self.assertEqual(c.health(), {"ok": True, "voices": ["jooseppi", "valdemar"], "queue": 0})
            self.assertEqual(c.voices()["jooseppi"]["emotions"], ["iloinen", "neutraali"])
            p = c.synthesize("Jooseppi", "iloinen", "Hei vaan. Mitä kuuluu?", seed=3)
            self.assertEqual((p.voice, p.clip, p.seed, p.sentences), ("jooseppi", "iloinen", 3, 2))
            info = sf.info(io.BytesIO(p.wav))
            self.assertEqual((info.channels, info.samplerate, info.subtype), (1, 24000, "PCM_16"))
            with self.assertRaises(pc.VirheellinenPyynto) as cm:
                c.synthesize("jooseppi", "raivoisa", "Hei.")
            self.assertIn("neutraali", str(cm.exception))  # the message lists what exists
            proc.send_signal(signal.SIGTERM)
            proc.wait(30)

    def test_no_service(self):
        import puhepalvelu_client as pc

        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(pc.EiKaytossa):
                pc.Puhepalvelu(os.path.join(d, "ei-ole")).health()

    def test_survives_a_restart_with_new_port_and_key(self):
        import puhepalvelu_client as pc

        with tempfile.TemporaryDirectory() as d:
            a, cdir = self.start(d)
            c = pc.Puhepalvelu(cdir)
            c.synthesize("valdemar", "neutraali", "Ensimmäinen.")
            old = (c.url, c.key)
            a.send_signal(signal.SIGTERM)
            self.assertEqual(a.wait(30), 0)
            with self.assertRaises(pc.EiKaytossa):  # nobody there now: osoite.json is gone
                c.synthesize("valdemar", "neutraali", "Ei kuulu.")
            b, _ = self.start(d)  # the next job: other port, new key
            p = c.synthesize("valdemar", "neutraali", "Toinen.")  # same client object, no reconfiguration
            self.assertEqual(p.voice, "valdemar")
            self.assertNotEqual((c.url, c.key), old)
            b.send_signal(signal.SIGTERM)
            b.wait(30)

    def test_busy_service_raises_or_waits(self):
        import puhepalvelu_client as pc

        with tempfile.TemporaryDirectory() as d:
            proc, cdir = self.start(d, "--fake-delay", "0.8", "--queue-interactive", "1")
            c = pc.Puhepalvelu(cdir)
            args = ("jooseppi", "neutraali", "Hei vaan.")

            def burst(**kw):
                with ThreadPoolExecutor(3) as ex:
                    futs = []
                    for _ in range(3):
                        futs.append(ex.submit(lambda: self._try(c, args, kw)))
                        time.sleep(0.2)
                    return [f.result() for f in futs]

            results = burst()  # one running, one waiting, the third finds the queue full
            self.assertEqual(sorted(results), ["ok", "ok", "varattu"])
            results = burst(wait_s=10)  # allowed to wait for a place: all three get their speech
            self.assertEqual(results, ["ok", "ok", "ok"])
            proc.send_signal(signal.SIGTERM)
            proc.wait(30)

    def test_guide_code_matches_file_and_snippets_work(self):
        """docs/rooliharjoittelu-ohje.md: Appendix A is the client file, and the example code in the steps runs."""
        import re

        import puhepalvelu_client as pc

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "docs", "rooliharjoittelu-ohje.md"), encoding="utf-8") as f:
            doc = f.read()
        with open(os.path.join(root, "scripts", "puhepalvelu_client.py"), encoding="utf-8") as f:
            self.assertIn(f.read().rstrip("\n"), doc)  # no drift between the guide and the file
        blocks = re.findall(r"```python\n(.*?)```", doc, re.S)
        find = lambda name: next(b for b in blocks if name in b)  # noqa: E731
        ns = {}
        exec(find("def tulkitse"), ns)  # noqa: S102
        äänet = {"justiina2": {"default_emotion": "neutraali", "emotions": ["neutraali", "tunne_artynyt_a"]}}
        t = ns["tulkitse"]
        self.assertEqual(t('{"teksti": "Hei.", "tunne": "Tunne_Artynyt_A"}', "justiina2", äänet), ("Hei.", "tunne_artynyt_a"))
        self.assertEqual(t('{"teksti": "Hei.", "tunne": "raivoisa"}', "justiina2", äänet), ("Hei.", "neutraali"))  # unknown
        self.assertEqual(t('{"teksti": "Hei."}', "justiina2", äänet), ("Hei.", "neutraali"))  # no emotion
        self.assertEqual(t("Pelkkä teksti.", "justiina2", äänet), ("Pelkkä teksti.", "neutraali"))  # not JSON
        exec(find("class Paikat"), ns)  # noqa: S102
        with tempfile.TemporaryDirectory() as d:
            proc, cdir = self.start(d)
            c = pc.Puhepalvelu(cdir)
            paikat = ns["Paikat"](2)
            self.assertEqual([ns["voiko_aloittaa"](c, paikat)[0] for _ in range(3)], [True, True, False])
            self.assertEqual(ns["voiko_aloittaa"](c, paikat)[1], "kaikki paikat ovat käytössä")
            paikat.vapauta()
            self.assertTrue(ns["voiko_aloittaa"](c, paikat)[0])  # the place was freed
            exec(find("def puhu_repliikki"), ns)  # noqa: S102
            soitetut = []
            ns["puhu_repliikki"](c, "jooseppi", "neutraali", 1, "Hei vaan. Mitä kuuluu? Hyvää!", soitetut.append)
            self.assertEqual(len(soitetut), 3)  # three sentences, three requests, in order
            self.assertTrue(all(sf.info(io.BytesIO(w)).samplerate == 24000 for w in soitetut))
            proc.send_signal(signal.SIGTERM)
            proc.wait(30)

    @staticmethod
    def _try(c, args, kw):
        import puhepalvelu_client as pc

        try:
            c.synthesize(*args, **kw)
            return "ok"
        except pc.Varattu:
            return "varattu"


class TestMakeRegistry(unittest.TestCase):
    def test_folder_to_registry_that_serve_accepts(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "slurm"))
        import make_registry

        with tempfile.TemporaryDirectory() as d:
            refs = os.path.join(d, "refs")
            for voice, clips in {"Jooseppi": ["neutraali", "tunne_artynyt_a"], "valdemar": ["lapsi_iloinen"]}.items():
                os.makedirs(os.path.join(refs, voice))
                for c in clips:
                    for ext in (".wav", ".txt"):
                        with open(os.path.join(refs, voice, c + ext), "w", encoding="utf-8") as f:
                            f.write("Viitteen sanat.")
            with open(os.path.join(refs, "Jooseppi", "ilman_tekstia.wav"), "w") as f:  # no .txt: skipped
                f.write("x")
            ck = os.path.join(d, "valdemar.safetensors")
            open(ck, "w").close()
            msgs = []
            reg = make_registry.build(refs, {"Valdemar": ck}, log=msgs.append)
            self.assertEqual(sorted(reg["voices"]), ["jooseppi", "valdemar"])
            self.assertEqual(sorted(reg["voices"]["jooseppi"]["emotions"]), ["neutraali", "tunne_artynyt_a"])
            self.assertEqual(reg["voices"]["jooseppi"]["ckpt"], "default")
            self.assertEqual(reg["voices"]["valdemar"]["default_emotion"], "lapsi_iloinen")
            self.assertTrue(any("ilman_tekstia" in m for m in msgs))
            path = os.path.join(d, "voices.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(reg, f)
            voices = serve.load_registry(path)  # with check_files: refs, transcripts and checkpoint exist
            self.assertEqual(voices["valdemar"].ckpt, ck)


class TestLifecycle(unittest.TestCase):
    """The real process with real signals: what Slurm does to the job."""

    def start(self, d, *extra):
        self.state = os.path.join(d, "state")
        proc = subprocess.Popen([sys.executable, SERVE_PY, "--voices", write_voices(d), "--state-dir", self.state,
                                 "--backend", "fake", "--no-auth", "--addr-heartbeat", "0.3", "--max-sessions", "2",
                                 "--drain-quiet", "1",
                                 *extra], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        cur = os.path.join(self.state, "current.json")
        addr = wait_for(lambda: (self.read(cur) or {}).get("status") == "ready" and self.read(cur), 60)
        return proc, addr

    @staticmethod
    def read(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def test_address_file_then_sigterm_cleans_up(self):
        import httpx

        with tempfile.TemporaryDirectory() as d:
            proc, addr = self.start(d)
            self.assertEqual(addr["version"], 1)
            self.assertGreater(addr["port"], 0)
            self.assertEqual(sorted(addr["voices"]), ["jooseppi", "valdemar"])
            self.assertEqual(httpx.get(addr["url"] + "/healthz").status_code, 200)
            first = addr["updated_at"]
            self.assertTrue(wait_for(lambda: self.read(os.path.join(self.state, "current.json"))["updated_at"] > first, 10))  # heartbeat
            sid = httpx.post(addr["url"] + "/sessions").json()["session_id"]
            r = httpx.post(addr["url"] + "/speak", json={"voice": "jooseppi", "text": "Hei.", "session_id": sid})
            self.assertEqual(r.status_code, 200)
            proc.send_signal(signal.SIGTERM)
            self.assertEqual(proc.wait(30), 0)
            self.assertEqual(os.listdir(self.state), [])  # both files removed, nothing stale left for the app to read

    def test_exits_by_itself_when_unused(self):
        with tempfile.TemporaryDirectory() as d:
            proc, _ = self.start(d, "--idle-exit", "2")
            self.assertEqual(proc.wait(30), 0)  # no sessions, no requests: the job would end and free the GPU
            self.assertEqual(os.listdir(self.state), [])

    def test_sigusr1_hands_over_to_successor_and_exits_when_idle(self):
        import httpx

        with tempfile.TemporaryDirectory() as d:
            proc, addr = self.start(d)
            url = addr["url"]
            sid = httpx.post(url + "/sessions").json()["session_id"]
            proc.send_signal(signal.SIGUSR1)  # time limit near, but no successor yet: carries on serving
            time.sleep(1)
            self.assertEqual(httpx.get(url + "/healthz").json()["status"], "ready")
            second = httpx.post(url + "/sessions")
            self.assertEqual(second.status_code, 201)
            sid2 = second.json()["session_id"]
            succ = {**addr, "job_id": "seuraaja-1", "status": "ready", "updated_at": time.time()}
            serve.write_json_atomic(os.path.join(self.state, "current.json"), succ)  # the next job became ready
            wait_for(lambda: httpx.get(url + "/healthz").json()["status"] == "draining", 10)
            httpx.delete(url + f"/sessions/{sid2}")
            self.assertEqual(httpx.post(url + "/sessions").status_code, 503)  # no new sessions while draining
            r = httpx.post(url + "/speak", json={"voice": "jooseppi", "text": "Hei.", "session_id": sid})
            self.assertEqual(r.status_code, 200)  # the session that was running is finished
            self.assertIsNone(proc.poll())
            httpx.delete(url + f"/sessions/{sid}")  # last session ends: the old instance leaves by itself
            self.assertEqual(proc.wait(30), 0)
            self.assertEqual(sorted(os.listdir(self.state)), ["current.json"])  # own file removed
            self.assertEqual(self.read(os.path.join(self.state, "current.json"))["job_id"], "seuraaja-1")  # successor's stays


if __name__ == "__main__":
    unittest.main()
