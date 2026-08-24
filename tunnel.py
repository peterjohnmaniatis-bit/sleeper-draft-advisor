#!/usr/bin/env python3
"""A public link for the draft board that is expected to last three hours.

Two backends, tried in order:

  dev tunnels (Microsoft, via the `devtunnel` CLI) -- preferred. A NAMED tunnel
  tied to the signed-in account, so the address survives a restart. That is the
  whole reason it is first: a cloudflared quick tunnel hands out a brand new
  hostname every time it comes back, and re-sending a link to eleven people
  mid-draft is the failure this module exists to avoid. Anonymous access is on,
  so guests need no account -- but Microsoft shows them a one-time
  "you are about to connect to a developer tunnel" page they must click through.

  cloudflared quick tunnel -- fallback, zero setup, no account. The address
  changes on every restart, and on 24 Aug 2026 quick tunnels registered cleanly
  from this machine while the Cloudflare edge returned 404 for every hostname,
  so it is no longer the default.

Either way the machine is kept awake, the live URL is written to
out/draft-link.txt, and the backend's own log is kept for diagnosis.
"""

import json
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
LINK_FILE = OUT / "draft-link.txt"
CF_URL_RE = re.compile(r"https://[-\w.]+\.trycloudflare\.com")
DT_URL_RE = re.compile(r"https://[-\w.]+\.devtunnels\.ms")
DT_TUNNEL = "ff-draft"
CHECK_EVERY = 45
FAILS_BEFORE_WARN = 2
CONTROL_URL = "https://api.sleeper.app/v1/state/nfl"
# Microsoft's interstitial answers instead of the app unless a request opts out.
SKIP_INTERSTITIAL = {"X-Tunnel-Skip-AntiPhishing-Page": "true"}


def keep_awake():
    """Stop Windows sleeping mid-draft. ctypes is standard library."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000041)
        print("  sleep suppressed for the duration", flush=True)
    except Exception as err:                      # noqa: BLE001
        print(f"  ! could not suppress sleep ({err}) -- check power settings",
              flush=True)


def _fetch_ok(url, timeout=20, headers=None):
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "ff-advisor/1.0", **(headers or {})})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200 and json.loads(r.read()) is not None
    except Exception:                             # noqa: BLE001
        return False


def _probe(url, timeout=20):
    """Is the public url really forwarding to us? Fetches the API rather than
    the page, so an interstitial or a cached shell cannot pass for success."""
    return _fetch_ok(url + "/api/state", timeout, SKIP_INTERSTITIAL)


def _internet_ok(timeout=15):
    """Can this machine reach anything at all?

    The health check must never confuse "the tunnel is down" with "I cannot
    check". Without this control probe a local DNS hiccup reads as a dead
    tunnel; the first version of this file then killed a perfectly healthy
    cloudflared and churned the link every ninety seconds.
    """
    return _fetch_ok(CONTROL_URL, timeout)


def _which_devtunnel():
    exe = shutil.which("devtunnel") or shutil.which("devtunnel.exe")
    if exe:
        return exe
    guess = (Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
             / "Microsoft.devtunnel_Microsoft.Winget.Source_8wekyb3d8bbwe"
             / "devtunnel.exe")
    return str(guess) if guess.exists() else None


def _run(cmd, timeout=60):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout)
    except Exception:                             # noqa: BLE001
        return None


class Tunnel:
    """Owns whichever backend is available and keeps it alive."""

    def __init__(self, port, aggressive=False):
        self.port = port
        self.aggressive = aggressive
        self.url = None
        self.proc = None
        self.stopping = False
        self.restarts = 0
        self.backend = None
        self.dt = _which_devtunnel()
        self.cf = shutil.which("cloudflared") or shutil.which("cloudflared.exe")

    # -- lifecycle ------------------------------------------------------
    def start(self):
        if self._devtunnel_ready():
            self.backend = "devtunnel"
        elif self.cf:
            self.backend = "cloudflared"
            print("  ! dev tunnel unavailable -- falling back to cloudflared.",
                  flush=True)
            print("    The address will change if the tunnel restarts.",
                  flush=True)
        else:
            print("  ! no tunnel tool found -- serving locally only", flush=True)
            return False
        keep_awake()
        threading.Thread(target=self._supervise, daemon=True).start()
        threading.Thread(target=self._health, daemon=True).start()
        return True

    def stop(self):
        self.stopping = True
        self._kill()

    def _kill(self):
        p = self.proc
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:                     # noqa: BLE001
                try:
                    p.kill()
                except Exception:                 # noqa: BLE001
                    pass

    # -- dev tunnels ----------------------------------------------------
    def _devtunnel_ready(self):
        """Signed in, and a named tunnel exists with this port open to guests.

        Creating both is idempotent, so this doubles as setup: a machine that
        is merely signed in ends up correctly configured.
        """
        if not self.dt:
            return False
        who = _run([self.dt, "user", "show"], 20)
        if not who or "Logged in" not in (who.stdout or ""):
            print("  ! dev tunnel not signed in. Run:", flush=True)
            print(f'      "{self.dt}" user login -g -d', flush=True)
            return False
        _run([self.dt, "create", DT_TUNNEL, "--allow-anonymous"], 40)
        _run([self.dt, "port", "create", DT_TUNNEL,
              "-p", str(self.port), "--protocol", "http"], 40)
        return True

    # -- the supervisor -------------------------------------------------
    def _cmd(self):
        if self.backend == "devtunnel":
            return [self.dt, "host", DT_TUNNEL]
        return [self.cf, "tunnel", "--url", f"http://127.0.0.1:{self.port}",
                "--no-autoupdate"]

    def _supervise(self):
        pattern = DT_URL_RE if self.backend == "devtunnel" else CF_URL_RE
        while not self.stopping:
            self.proc = subprocess.Popen(
                self._cmd(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1)
            self.url = None
            log = None
            try:
                OUT.mkdir(exist_ok=True)
                log = open(OUT / "tunnel.log", "a", encoding="utf-8")
            except OSError:
                pass
            # Drain for the whole run. Stopping early deadlocks the child on a
            # full pipe, and it then stops forwarding while every local request
            # still succeeds -- exactly the invisible failure to avoid.
            for line in self.proc.stdout:
                if log:
                    log.write(line)
                    log.flush()
                if self.url is None:
                    m = pattern.search(line)
                    # The inspect URL is printed alongside the real one and is
                    # not the board; skip it.
                    if m and "-inspect." not in m.group(0):
                        self.url = m.group(0)
                        self._announce()
            if log:
                log.close()
            self.proc.wait()
            if self.stopping:
                return
            self.restarts += 1
            print("", flush=True)
            print("  ! the tunnel exited. Restarting...", flush=True)
            time.sleep(3)

    def _announce(self):
        OUT.mkdir(exist_ok=True)
        LINK_FILE.write_text(self.url + "\n", encoding="utf-8")
        stable = self.backend == "devtunnel"
        print("", flush=True)
        if self.restarts == 0:
            print(f"  SHARE THIS: {self.url}", flush=True)
        elif stable:
            print(f"  tunnel restarted -- same address: {self.url}", flush=True)
        else:
            print(f"  NEW LINK (the old one is dead): {self.url}", flush=True)
            print("  A restarted quick tunnel always gets a new address, so you",
                  flush=True)
            print("  have to resend it.", flush=True)
        if stable and self.restarts == 0:
            print("  Guests see a one-time Microsoft 'developer tunnel' warning",
                  flush=True)
            print("  page first -- that is expected. They click Continue once.",
                  flush=True)
        print(f"  saved to {LINK_FILE}", flush=True)
        print("", flush=True)
        threading.Thread(target=self._first_check, daemon=True).start()

    def _first_check(self):
        url = self.url
        for wait in (3, 5, 8, 12):
            time.sleep(wait)
            if url != self.url:
                return
            if _probe(url):
                print("  link checked: reachable from the internet", flush=True)
                return
        print("  ! the link has not answered yet -- do not send it out until",
              flush=True)
        print("    you see 'link checked'.", flush=True)

    # -- the health check -----------------------------------------------
    def _health(self):
        fails = 0
        while not self.stopping:
            time.sleep(CHECK_EVERY)
            url = self.url
            if not url:
                continue
            if _probe(url, timeout=15):
                if fails:
                    print("  public link recovered", flush=True)
                fails = 0
                continue
            if not _internet_ok():
                print("  ! this machine cannot reach the internet -- leaving",
                      flush=True)
                print("    the tunnel alone. The link is likely fine for others.",
                      flush=True)
                fails = 0
                continue
            fails += 1
            print(f"  ! public link check failed ({fails}) -- internet is up",
                  flush=True)
            if not self.aggressive:
                # Warn, never kill. On cloudflared a restart changes the
                # address, so a false positive destroys a working link in order
                # to repair one that was fine. Real death is caught by the
                # supervisor, which sees the process actually exit.
                if fails == FAILS_BEFORE_WARN:
                    print("    Not restarting on a check alone; --watchdog "
                          "forces it.", flush=True)
                continue
            if fails >= FAILS_BEFORE_WARN:
                fails = 0
                print("  ! restarting the tunnel (--watchdog)", flush=True)
                self._kill()
