"""Client for scripts/serve.py. Only needs httpx, so it can be copied into another project (Rooliharjoittelu).

    import f5client
    addr = f5client.read_address("/polku/.f5-palvelu/current.json")   # None = no service available right now
    if addr is None: ...                                            # show "puhepalvelu ei käytössä", text only, etc.
    client = f5client.Client(addr["url"], key)
    try:
        with client.session() as s:                                 # takes a place, sends heartbeats, frees the place
            wav_bytes, info = s.speak("justiina", "Tervetuloa, istu vain.", emotion="iloinen")
    except f5client.ServiceBusy as e:                               # all places taken or the server is overloaded
        ...e.retry_after
    except f5client.ServiceDown:                                    # not ready, draining, died: try the address file again
        ...

Send one sentence at a time as the LLM produces them: audio starts when the first sentence is ready, not the last.
"""
import json
import threading
import time

import httpx


class ServiceBusy(Exception):
    def __init__(self, reason, retry_after=10):
        super().__init__(reason)
        self.reason, self.retry_after = reason, retry_after


class ServiceDown(Exception):
    pass


def read_address(path, max_age_s=45.0):
    """Address of a service that takes new sessions, or None. The file is rewritten every few seconds by the server;
    one that has not been touched for max_age_s is left behind by a job that was killed."""
    try:
        with open(path, encoding="utf-8") as f:
            addr = json.load(f)
    except (OSError, ValueError):
        return None
    if addr.get("status") != "ready" or time.time() - addr.get("updated_at", 0) > max_age_s:
        return None
    return addr


def _detail(r):
    try:
        d = r.json()["detail"]
        return d["detail"] if isinstance(d, dict) else str(d)
    except Exception:  # noqa: BLE001
        return r.text[:100]


class Client:
    def __init__(self, url, key=None, timeout=30.0):
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self.http = httpx.Client(base_url=url, headers=headers, timeout=timeout)

    def _check(self, r):
        if r.status_code == 429:
            raise ServiceBusy(_detail(r), int(r.headers.get("retry-after", 10)))
        if r.status_code == 503:
            raise ServiceDown(_detail(r))
        r.raise_for_status()
        return r

    def request(self, method, path, **kw):
        try:
            return self._check(self.http.request(method, path, **kw))
        except httpx.TransportError as e:
            raise ServiceDown(str(e)) from None

    def voices(self):
        return self.request("GET", "/voices").json()

    def status(self):
        return self.request("GET", "/status").json()

    def session(self):
        return Session(self)

    def speak_batch(self, voice, text, emotion=None, **kw):
        """For the batch key (own work, no session): returns (wav bytes, info)."""
        return _speak(self, None, voice, text, emotion, **kw)


def _speak(client, sid, voice, text, emotion, **kw):
    body = {"voice": voice, "text": text, "emotion": emotion, "session_id": sid, **kw}
    r = client.request("POST", "/speak", json=body)
    info = {k[2:].replace("-", "_"): v for k, v in r.headers.items() if k.startswith("x-")}
    return r.content, info  # info: voice, emotion, seed, sentences, duration_s, wait_s, gen_s


class Session:
    """A place on the server; use as a context manager."""

    def __init__(self, client):
        self.client = client
        d = client.request("POST", "/sessions").json()
        self.id, self.ttl = d["session_id"], d["ttl_s"]
        self._stop = threading.Event()
        self._beat = threading.Thread(target=self._heartbeat, args=(d["heartbeat_every_s"],), daemon=True)
        self._beat.start()

    def _heartbeat(self, every):
        while not self._stop.wait(every):
            try:
                self.client.request("POST", f"/sessions/{self.id}/heartbeat")
            except Exception:  # noqa: BLE001 - speak() reports a lost session
                pass

    def speak(self, voice, text, emotion=None, **kw):
        return _speak(self.client, self.id, voice, text, emotion, **kw)

    def close(self):
        self._stop.set()
        try:
            self.client.request("DELETE", f"/sessions/{self.id}")
        except Exception:  # noqa: BLE001 - the server frees the place by itself after the TTL
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
