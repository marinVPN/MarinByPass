"""Проверка доступности сервисов через HTTPS."""
from __future__ import annotations

import queue
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request

SERVICES = [
    ("YouTube", "https://www.youtube.com/generate_204"),
    ("Discord", "https://discord.com/api/v10/gateway"),
    ("Google", "https://www.google.com/generate_204"),
]

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def _probe(url: str, timeout: float = 8.0):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Cache-Control": "no-cache"})
    ctx = ssl.create_default_context()
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            resp.read(64)
        ms = int((time.perf_counter() - t0) * 1000)
        return True, ms, "доступен"
    except urllib.error.HTTPError as exc:
        ms = int((time.perf_counter() - t0) * 1000)
        # любой HTTP-ответ означает, что соединение прошло
        return True, ms, f"HTTP {exc.code}"
    except socket.timeout:
        return False, None, "таймаут"
    except socket.gaierror:
        return False, None, "ошибка DNS"
    except ssl.SSLError:
        return False, None, "ошибка TLS"
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, socket.timeout):
            return False, None, "таймаут"
        if isinstance(reason, socket.gaierror):
            return False, None, "ошибка DNS"
        if isinstance(reason, ssl.SSLError):
            return False, None, "ошибка TLS"
        return False, None, "нет соединения"
    except Exception:
        return False, None, "нет соединения"


class NetChecker:
    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.busy = False

    def run(self):
        if self.busy:
            return
        self.busy = True
        for name, url in SERVICES:
            threading.Thread(target=self._one, args=(name, url), daemon=True).start()

    def _one(self, name: str, url: str):
        ok, ms, detail = _probe(url)
        self.q.put((name, ok, ms, detail))
