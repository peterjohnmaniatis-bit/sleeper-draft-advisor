#!/usr/bin/env python3
"""A public link that is expected to survive a three-hour draft.

cloudflared quick tunnels are free and need no account, which is why this uses
one -- but Cloudflare calls them a testing convenience, not a service, and they
do drop. So the tunnel is supervised rather than merely started:

  * a health check fetches the PUBLIC url every 45s, because the failure that
    matters is invisible locally -- the tunnel stops forwarding while this
    machine keeps answering its own requests perfectly;
  * a failing check WARNS but does not kill: a restart hands out a brand new
    hostname, so a false positive destroys the link everyone is holding in
    order to repair one that worked. Genuine death is caught unambiguously by
    the supervisor, which restarts when cloudflared actually exits. Pass
    --watchdog if you want failed checks to force a restart anyway;
  * the current url is written to out/draft-link.txt, so recovering a changed
    link is reading a file rather than scrolling the console;
  * the machine is kept awake for the duration, since a laptop going to sleep
    takes the tunnel, the server and the poll thread with it.

A restarted quick tunnel gets a NEW hostname. That is the real limitation and
it is unavoidable without a Cloudflare account and a domain, so a change is
announced loudly instead of being papered over.
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
LINK_FILE = ROOT / "out" / "draft-link.txt"
URL_RE = re.compile(r"https://[-\w.]+\.trycloudflare\.com")
CHECK_EVERY = 45
FAILS_BEFORE_RESTART = 2


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
        print(f"  ! could not suppress sleep ({err}) -- check your power settings",
              flush=True)


CONTROL_URL = "https://api.sleeper.app/v1/state/nfl"


def _fetch_ok(url, timeout=20, want_json=True):
    try:
        req = urllib.request.Request(url,
                                     headers={"User-Agent": "ff-advisor/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                return False
            return json.loads(r.read()) is not None if want_json else True
    except Exception:                             # noqa: BLE001
        return False


def _probe(url, timeout=20):
    """Is the public url actually forwarding? Fetches the API, not the page,
    so a cached shell cannot pass for a working tunnel."""
    return _fetch_ok(url + "/api/state", timeout)


def _internet_ok(timeout=15):
    """Can this machine reach anything at all?

    The watchdog must not confuse "the tunnel is down" with "I cannot check".
    Without this control probe a local DNS hiccup reads as a dead tunnel, the
    watchdog kills a perfectly healthy cloudflared, and every guest gets a new
    hostname -- a link that churns every ninety seconds instead of one that
    lasts. This was not hypothetical: it is exactly what happened in testing.
    """
    return _fetch_ok(CONTROL_URL, timeout)


class Tunnel:
    def __init__(self, port, aggressive=False):
        self.port = port
        self.aggressive = aggressive
        self.url = None
        self.proc = None
        self.stopping = False
        self.exe = shutil.which("cloudflared") or shutil.which("cloudflared.exe")
        self.restarts = 0

    # -- lifecycle ------------------------------------------------------
    def start(self):
        if not self.exe:
            print("  ! cloudflared not found -- serving locally only", flush=True)
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

    # -- the supervisor -------------------------------------------------
    def _supervise(self):
        while not self.stopping:
            self.proc = subprocess.Popen(
                [self.exe, "tunnel", "--url", f"http://127.0.0.1:{self.port}",
                 "--no-autoupdate"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", bufsize=1)
            self.url = None
            # Drain for the whole run. Stopping early deadlocks cloudflared on a
            # full pipe, and the tunnel then stops forwarding while every local
            # request still succeeds -- the exact failure this class exists for.
            # Keep cloudflared's own log. Diagnosing a tunnel with its output
            # discarded means guessing; "Registered tunnel connection" is the
            # line that separates "printed a URL" from "actually serving".
            log = None
            try:
                LINK_FILE.parent.mkdir(exist_ok=True)
                log = open(ROOT / "out" / "tunnel.log", "a", encoding="utf-8")
            except OSError:
                pass
            for line in self.proc.stdout:
                if log:
                    log.write(line)
                    log.flush()
                if self.url is None:
                    m = URL_RE.search(line)
                    if m:
                        self.url = m.group(0)
                        self._announce()
            if log:
                log.close()
            self.proc.wait()
            if self.stopping:
                return
            self.restarts += 1
            print("", flush=True)
            print("  ! the public link dropped. Restarting the tunnel...",
                  flush=True)
            time.sleep(3)

    def _announce(self):
        first = self.restarts == 0
        LINK_FILE.parent.mkdir(exist_ok=True)
        LINK_FILE.write_text(self.url + "\n", encoding="utf-8")
        print("", flush=True)
        if first:
            print(f"  SHARE THIS: {self.url}", flush=True)
        else:
            print(f"  NEW LINK (the old one is dead): {self.url}", flush=True)
            print("  A restarted quick tunnel always gets a new address --",
                  flush=True)
            print("  you have to resend it.", flush=True)
        print(f"  also saved to {LINK_FILE}", flush=True)
        print("", flush=True)
        threading.Thread(target=self._first_check, daemon=True).start()

    def _first_check(self):
        url = self.url
        for wait in (3, 5, 8, 12):
            time.sleep(wait)
            if url != self.url:
                return
            if _probe(url):
                print(f"  link checked: reachable from the internet", flush=True)
                return
        print("  ! the link did not answer yet -- watching it; do not send it",
              flush=True)
        print("    out until you see 'link checked'.", flush=True)

    # -- the watchdog ---------------------------------------------------
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
                # This machine is offline, or its resolver is unhappy. Killing
                # cloudflared now would burn the hostname everyone is holding
                # and fix nothing, so say so and wait.
                print("  ! cannot reach the internet from here -- not touching",
                      flush=True)
                print("    the tunnel. The link is probably fine for others.",
                      flush=True)
                fails = 0
                continue
            fails += 1
            print(f"  ! public link check failed ({fails}) -- internet is up",
                  flush=True)
            if not self.aggressive:
                # Warn, do not kill. A restart is not free: the quick tunnel
                # gets a NEW hostname, so a false positive actively destroys
                # the link everyone is holding in order to fix a link that was
                # working. Testing produced exactly that -- a probe that failed
                # for a local resolver reason churned a healthy tunnel every
                # ninety seconds. Genuine death is caught unambiguously by the
                # supervisor, which restarts when cloudflared actually exits.
                if fails == FAILS_BEFORE_RESTART:
                    print("    Not restarting: that would change the address "
                          "everyone has.", flush=True)
                    print(f"    If guests really cannot load it, restart with "
                          f"--share for a new link.", flush=True)
                continue
            if fails >= FAILS_BEFORE_RESTART:
                fails = 0
                print("  ! restarting the tunnel (--watchdog)", flush=True)
                self._kill()          # the supervisor loop respawns it
