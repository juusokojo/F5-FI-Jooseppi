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


class TestLifecycle(unittest.TestCase):
    """The real process with real signals: what Slurm does to the job."""

    def start(self, d, *extra):
        self.state = os.path.join(d, "state")
        proc = subprocess.Popen([sys.executable, SERVE_PY, "--voices", write_voices(d), "--state-dir", self.state,
                                 "--backend", "fake", "--no-auth", "--addr-heartbeat", "0.3", "--max-sessions", "2",
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
