"""Client for the F5-fi puhepalvelu (Lehmus). Python standard library only, so the file can be copied as it is.

    from puhepalvelu_client import Puhepalvelu, EiKaytossa, Varattu, VirheellinenPyynto

    puhe = Puhepalvelu()                      # reads ~/.f5-palvelu/osoite.json and ~/.f5-palvelu/avain
    p = puhe.synthesize("justiina2", "tunne_artynyt_a", "Tämä on koe. Kuuluuko ääni?", wait_s=3)
    open("koe.wav", "wb").write(p.wav)        # mono, 16 bit, 24 kHz

Command line (a quick check that the connection works):

    python puhepalvelu_client.py --health
    python puhepalvelu_client.py --voices
    python puhepalvelu_client.py --voice justiina2 --clip neutraali -o koe.wav "Tämä on koe."

The service writes a new key and may move to a new node and port whenever its Slurm job is replaced. This client therefore
reads the two files again and tries once more when the connection fails or the key is refused, which is all an application
needs to survive a restart. Proxy settings from the environment are ignored on purpose: the service is on the cluster's
internal network.
"""
import argparse
import dataclasses
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

DEFAULT_DIR = os.path.expanduser(os.environ.get("F5_PALVELU_DIR", "~/.f5-palvelu"))  # F5_PALVELU_DIR: if elsewhere


class PuhepalveluError(Exception):
    pass


class EiKaytossa(PuhepalveluError):
    """The service is not running, not ready, or cannot be reached: use text only or tell the user."""


class Varattu(PuhepalveluError):
    """503: the queue is full, the line waited too long, or the service is starting. Try again after retry_after seconds."""

    def __init__(self, message, retry_after=5.0):
        super().__init__(message)
        self.retry_after = retry_after


class VirheellinenPyynto(PuhepalveluError):
    """400: unknown voice or clip, empty or too long text, bad JSON. The message says what is wrong and what exists."""


class Epaonnistui(PuhepalveluError):
    """401 after the files were read again, or 500: the synthesis itself failed."""


@dataclasses.dataclass
class Puhe:
    wav: bytes
    voice: str
    clip: str
    seed: int
    sentences: int
    duration_s: float
    wait_s: float  # time in the queue
    gen_s: float  # time spent generating


class Puhepalvelu:
    def __init__(self, directory=DEFAULT_DIR, timeout=60.0):
        self.dir, self.timeout = directory, timeout
        self.url = self.key = None
        self._lock = threading.Lock()
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    # -- address and key

    def _load(self):
        try:
            with open(os.path.join(self.dir, "osoite.json"), encoding="utf-8") as f:
                url = json.load(f)["url"].rstrip("/")
            with open(os.path.join(self.dir, "avain"), encoding="utf-8") as f:
                key = f.read().strip()
        except (OSError, ValueError, KeyError) as e:
            raise EiKaytossa(f"puhepalvelun osoitetta ei löydy ({self.dir}): {e}") from None
        with self._lock:
            self.url, self.key = url, key

    def _once(self, method, path, body=None, auth=True):
        if self.url is None:
            self._load()
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if auth:
            headers["Authorization"] = f"Bearer {self.key}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()
        except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError) as e:
            raise EiKaytossa(f"yhteys puhepalveluun ei onnistu ({self.url}): {e}") from None

    def _request(self, method, path, body=None, auth=True):
        """One request; if the connection fails or the key is refused, read the files again and try once more."""
        try:
            status, headers, data = self._once(method, path, body, auth)
            if status != 401:
                return status, headers, data
        except EiKaytossa:
            pass
        self._load()
        return self._once(method, path, body, auth)

    @staticmethod
    def _error(data):
        try:
            return json.loads(data)["error"]
        except (ValueError, KeyError, TypeError):
            return data[:200].decode("utf-8", "replace")

    # -- interface

    def health(self):
        """{"ok": bool, "voices": [...], "queue": n}. Raises EiKaytossa if nothing answers. ok is False while starting."""
        status, _, data = self._request("GET", "/health", auth=False)
        try:
            return json.loads(data)
        except ValueError:
            raise EiKaytossa(f"/health antoi vastauksen {status}, joka ei ole JSON") from None

    def voices(self):
        """{"justiina2": {"default_emotion": "neutraali", "emotions": ["neutraali", "tunne_artynyt_a", ...]}, ...}"""
        status, _, data = self._request("GET", "/voices")
        if status != 200:
            raise Epaonnistui(f"/voices: {status} {self._error(data)}")
        return json.loads(data)

    def synthesize(self, voice, clip, text, seed=None, wait_s=0.0):
        """Speak `text` (a few sentences) in `voice` with the reference clip `clip`. wait_s: how long in total this call
        may wait for a busy service (503) before it raises Varattu."""
        body = {"voice": voice, "clip": clip, "text": text}
        if seed is not None:
            body["seed"] = seed
        deadline = time.monotonic() + wait_s
        while True:
            status, headers, data = self._request("POST", "/synthesize", body)
            h = {k.lower(): v for k, v in headers.items()}
            if status == 200:
                return Puhe(data, h["x-voice"], h["x-emotion"], int(h["x-seed"]), int(h["x-sentences"]),
                            float(h["x-duration-s"]), float(h["x-wait-s"]), float(h["x-gen-s"]))
            if status == 503:
                retry = float(h.get("retry-after", 5))
                if time.monotonic() + retry <= deadline:
                    time.sleep(retry)
                    continue
                raise Varattu(self._error(data), retry)
            if status == 400:
                raise VirheellinenPyynto(self._error(data))
            raise Epaonnistui(f"{status}: {self._error(data)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="F5-fi puhepalvelun yhteyskoe")
    ap.add_argument("text", nargs="?")
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--health", action="store_true")
    ap.add_argument("--voices", action="store_true")
    ap.add_argument("--voice")
    ap.add_argument("--clip")
    ap.add_argument("--seed", type=int)
    ap.add_argument("-o", "--out", default="koe.wav")
    ap.add_argument("--wait", type=float, default=10.0, help="kauanko saa odottaa varattua palvelua (s)")
    a = ap.parse_args(argv)
    puhe = Puhepalvelu(a.dir)
    try:
        if a.health:
            print(json.dumps(puhe.health(), ensure_ascii=False))
        elif a.voices:
            print(json.dumps(puhe.voices(), ensure_ascii=False, indent=1))
        elif a.voice and a.clip and a.text:
            p = puhe.synthesize(a.voice, a.clip, a.text, a.seed, a.wait)
            with open(a.out, "wb") as f:
                f.write(p.wav)
            print(f"{a.out}: {p.duration_s:.2f} s, siemen {p.seed}, jonossa {p.wait_s:.2f} s, generointi {p.gen_s:.2f} s")
        else:
            ap.error("anna --health, --voices tai --voice, --clip ja teksti")
    except PuhepalveluError as e:
        sys.exit(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
