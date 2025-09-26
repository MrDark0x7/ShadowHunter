#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
- Deterministic sequential scanning by default (concurrency=1)
- Live Sherlock-like output + JSON/CSV output
- Banner: "ShadowHunter v2.0  —  by MrDark0x7"
"""

import argparse
import hashlib
import json
import os
import re
import signal
import sys
import time
from typing import Dict, Tuple, Any, List, Callable

import requests
from requests.adapters import HTTPAdapter, Retry
from lxml import html

# ---------- Config ----------
TOOL_NAME = "ShadowHunter v2.0"
DEFAULT_AUTHOR = "MrDark0x7"
UA = f"Mozilla/5.0 (OSINT-Collector; {TOOL_NAME})"
DEFAULT_TIMEOUT = 10
DEFAULT_DELAY = 0.15
DEFAULT_WORKERS = 1  # sequential by default for determinism

STOP = False

BANNER = r"""

  ___ _            _            _  _          _                 ___   __  
 / __| |_  __ _ __| |_____ __ _| || |_  _ _ _| |_ ___ _ _  __ _|_  ) /  \ 
 \__ \ ' \/ _` / _` / _ \ V  V / __ | || | ' \  _/ -_) '_| \ V // / | () |
 |___/_||_\__,_\__,_\___/\_/\_/|_||_|\_,_|_||_\__\___|_|    \_//___(_)__/ 

{tool_name}  —  y {author}
"""

# ---------- Signal ----------
def _sigint(signum, frame):
    global STOP
    STOP = True
    print("\n\033[93m[!] SIGINT received — finishing current request then saving partial results...\033[0m")
signal.signal(signal.SIGINT, _sigint)

# ---------- HTTP session builder ----------
def build_session(timeout: int = DEFAULT_TIMEOUT) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    retries = Retry(total=2, backoff_factor=0.5, status_forcelist=(429,500,502,503,504), allowed_methods=frozenset(["GET"]))
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter); s.mount("https://", adapter)
    orig = s.request
    def wrapped(method, url, **kwargs):
        if "timeout" not in kwargs:
            kwargs["timeout"] = timeout
        return orig(method, url, **kwargs)
    s.request = wrapped
    return s

# ---------- Utilities ----------
def _title_from_html(content: bytes) -> str:
    try:
        tree = html.fromstring(content)
        return tree.xpath("string(//title)").strip()
    except Exception:
        return ""

def _print_found(text: str):
    print(f"\033[92m[FOUND]   {text}\033[0m")

def _print_notfound(text: str):
    print(f"\033[91m[NOTFOUND] {text}\033[0m")

def _print_info(text: str):
    print(f"\033[94m[INFO]    {text}\033[0m")

# ---------- Generic fallback checker ----------
def check_generic(session: requests.Session, url_template: str, username: str) -> Tuple[bool, Dict[str,Any]]:
    url = url_template.format(u=username)
    meta: Dict[str,Any] = {}
    try:
        r = session.get(url)
        if r.status_code == 404:
            return False, {}
        txt = (r.text or "").lower()
        for p in ("not found", "page not found", "user not found", "no such user", "sorry, this page"):
            if p in txt:
                return False, {}
        title = _title_from_html(r.content)
        if title:
            meta["title"] = title
            meta["source"] = "generic-title"
            return True, meta
        return r.status_code == 200, {}
    except requests.RequestException:
        return False, {}

# ---------- Platform-specific checkers ----------
def check_github(session: requests.Session, username: str) -> Tuple[bool, Dict[str,Any]]:
    api = f"https://api.github.com/users/{username}"
    try:
        r = session.get(api)
        if r.status_code == 200:
            j = r.json()
            return True, {"source":"api.github.com", "name": j.get("name"), "bio": j.get("bio")}
        if r.status_code == 404:
            return False, {}
    except Exception:
        pass
    return check_generic(session, "https://github.com/{u}", username)

def check_reddit(session: requests.Session, username: str) -> Tuple[bool, Dict[str,Any]]:
    about = f"https://www.reddit.com/user/{username}/about.json"
    profile = f"https://www.reddit.com/user/{username}/"
    try:
        r = session.get(about)
        if r.status_code == 200:
            try:
                j = r.json()
                if isinstance(j, dict) and j.get("data") and j["data"].get("name"):
                    return True, {"source":"reddit-about-json", "data": j["data"]}
            except Exception:
                pass
        if r.status_code in (403,404,410):
            return False, {}
    except Exception:
        pass
    try:
        r2 = session.get(profile)
        if r2.status_code == 404:
            return False, {}
        txt = (r2.text or "").lower()
        if "sorry, nobody on reddit goes by that name" in txt or "account suspended" in txt or "this account may have been banned" in txt:
            return False, {}
        title = _title_from_html(r2.content)
        if title and "reddit" not in title.lower():
            return True, {"source":"reddit-html-title", "title": title}
        return True, {}
    except Exception:
        return False, {}

def check_stackoverflow(session: requests.Session, username: str) -> Tuple[bool, Dict[str,Any]]:
    # user pages use numeric ID. If username is not digits -> not found.
    if not username.isdigit():
        return False, {}
    url = f"https://stackoverflow.com/users/{username}"
    try:
        r = session.get(url)
        if r.status_code == 404:
            return False, {}
        txt = (r.text or "").lower()
        for p in ("user deleted", "page not found", "profile not found"):
            if p in txt:
                return False, {}
        title = _title_from_html(r.content)
        return True, {"source":"stackoverflow-html", "title": title} if title else (True, {})
    except Exception:
        return False, {}

def check_hackernews(session: requests.Session, username: str) -> Tuple[bool, Dict[str,Any]]:
    url = f"https://news.ycombinator.com/user?id={username}"
    try:
        r = session.get(url)
        if r.status_code == 404:
            return False, {}
        txt = (r.text or "").lower()
        if "no such user." in txt or "no such user" in txt:
            return False, {}
        return True, {"source":"hackernews-html"}
    except Exception:
        return False, {}

def check_gitlab(session: requests.Session, username: str) -> Tuple[bool, Dict[str,Any]]:
    url = f"https://gitlab.com/{username}"
    try:
        r = session.get(url)
        if r.status_code == 404:
            return False, {}
        txt = (r.text or "").lower()
        for neg in ("page not found", "just a moment", "404"):
            if neg in txt:
                return False, {}
        if "profile-header" in txt or "user-show" in txt or "projects" in txt or "activity" in txt:
            title = _title_from_html(r.content)
            return True, {"source":"gitlab-html-marker", "title": title}
        return False, {}
    except Exception:
        return False, {}

def check_x(session: requests.Session, username: str) -> Tuple[bool, Dict[str,Any]]:
    url = f"https://x.com/{username}"
    try:
        r = session.get(url)
        if r.status_code == 404:
            return False, {}
        txt = (r.text or "").lower()
        for neg in ("account suspended", "this account doesn’t exist", "this account doesn't exist", "user not found"):
            if neg in txt:
                return False, {}
        if 'property="og:description"' in r.text or 'name="twitter:description"' in r.text:
            return True, {"source":"x-og"}
        if "followers" in txt or "following" in txt or "tweets" in txt:
            return True, {"source":"x-text-hint"}
        return False, {}
    except Exception:
        return False, {}

def check_youtube(session: requests.Session, username: str) -> Tuple[bool, Dict[str,Any]]:
    url = f"https://www.youtube.com/@{username}"
    try:
        r = session.get(url)
        if r.status_code == 404:
            return False, {}
        txt = (r.text or "").lower()
        if "channel does not exist" in txt or "no longer available" in txt:
            return False, {}
        if "channelid" in txt.lower() or "subscribercounttext" in txt.lower():
            return True, {"source":"youtube-html"}
        title = _title_from_html(r.content)
        if title and "youtube" not in title.lower():
            return True, {"source":"youtube-title", "title": title}
        return False, {}
    except Exception:
        return False, {}

def check_instagram(session: requests.Session, username: str) -> Tuple[bool, Dict[str,Any]]:
    url = f"https://www.instagram.com/{username}/"
    try:
        r = session.get(url)
        if r.status_code == 404:
            return False, {}
        txt = (r.text or "").lower()
        if "sorry, this page isn't available" in txt or "page isn't available" in txt:
            return False, {}
        if '"is_private":' in txt or '"graphql"' in txt or 'window._sharedData' in txt:
            return True, {"source":"instagram-embedded-json", "title": _title_from_html(r.content)}
        title = _title_from_html(r.content)
        if title and 'instagram' not in title.lower():
            return True, {"source":"instagram-title", "title": title}
        return False, {}
    except Exception:
        return False, {}

def check_tiktok(session: requests.Session, username: str) -> Tuple[bool, Dict[str,Any]]:
    url = f"https://www.tiktok.com/@{username}"
    try:
        r = session.get(url)
        if r.status_code == 404:
            return False, {}
        txt = (r.text or "").lower()
        if "page not found" in txt or "user not found" in txt or "couldn't find this account" in txt:
            return False, {}
        if "window.__INIT_PROPS" in txt or '"userInfo"' in txt:
            return True, {"source":"tiktok-html-json"}
        title = _title_from_html(r.content)
        if title:
            return True, {"title": title}
        return False, {}
    except Exception:
        return False, {}

def check_steam(session: requests.Session, username: str) -> Tuple[bool, Dict[str,Any]]:
    try:
        r = session.get(f"https://steamcommunity.com/id/{username}/?xml=1")
        if r.status_code == 200 and "<error>" in (r.text or ""):
            return False, {}
        if r.status_code == 200:
            return True, {"source":"steam-xml"}
        r2 = session.get(f"https://steamcommunity.com/id/{username}")
        if r2.status_code == 200:
            txt = (r2.text or "").lower()
            if "error" in txt and "profile" in txt:
                return False, {}
            return True, {"source":"steam-html"}
        return False, {}
    except Exception:
        return False, {}

def check_linkedin(session: requests.Session, username: str) -> Tuple[bool, Dict[str,Any]]:
    """
    Conservative LinkedIn checker:
    - Many LinkedIn pages are login-gated and return 200.
    - Treat pages with explicit "profile not found" / 404 as NOT FOUND.
    - If title looks like a real profile (and not a generic sign-in page), return FOUND.
    - Otherwise return NOT FOUND to avoid false positives.
    """
    url = f"https://www.linkedin.com/in/{username}/"
    try:
        r = session.get(url)
        if r.status_code == 404:
            return False, {}
        txt = (r.text or "").lower()
        if "profile not found" in txt or "profile not available" in txt:
            return False, {}
        title = _title_from_html(r.content)
        if "sign in" in txt and "linkedin" in (title or "").lower():
            return False, {}
        if title and "linkedin" not in title.lower() and len(title.split()) >= 2:
            return True, {"source":"linkedin-title", "title": title}
        if 'property="og:title"' in r.text or 'name="og:title"' in r.text:
            return True, {"source":"linkedin-og", "title": title}
        return False, {}
    except Exception:
        return False, {}

# ---------- Platform map (Twitch intentionally omitted) ----------
GENERIC_TEMPLATES: Dict[str,str] = {
    "github":"https://github.com/{u}", "gitlab":"https://gitlab.com/{u}", "reddit":"https://www.reddit.com/user/{u}/",
    "stack_overflow":"https://stackoverflow.com/users/story/{u}", "tiktok":"https://www.tiktok.com/@{u}",
    "youtube":"https://www.youtube.com/@{u}", "medium":"https://medium.com/@{u}", "devto":"https://dev.to/{u}", "pinterest":"https://www.pinterest.com/{u}/",
    "soundcloud":"https://soundcloud.com/{u}", "vimeo":"https://vimeo.com/{u}", "steam":"https://steamcommunity.com/id/{u}",
    "keybase":"https://keybase.io/{u}", "instagram":"https://www.instagram.com/{u}/", "facebook":"https://www.facebook.com/{u}",
    "x":"https://x.com/{u}", "kaggle":"https://www.kaggle.com/{u}", "hackernews":"https://news.ycombinator.com/user?id={u}", "linkedin":"https://www.linkedin.com/in/{u}/"
}

PLATFORM_CHECKERS: Dict[str, Callable[[requests.Session,str], Tuple[bool,Dict[str,Any]]]] = {
    "github": check_github, "gitlab": check_gitlab, "reddit": check_reddit, "stack_overflow": check_stackoverflow,
    "tiktok": check_tiktok, "youtube": check_youtube, "medium": lambda s,u: check_generic(s, "https://medium.com/@{u}", u),
    "devto": lambda s,u: check_generic(s, "https://dev.to/{u}", u), "pinterest": lambda s,u: check_generic(s, "https://www.pinterest.com/{u}/", u),
    "soundcloud": lambda s,u: check_generic(s, "https://soundcloud.com/{u}", u), "vimeo": lambda s,u: check_generic(s, "https://vimeo.com/{u}", u),
    "steam": check_steam, "keybase": lambda s,u: check_generic(s, "https://keybase.io/{u}", u), "instagram": check_instagram,
    "facebook": lambda s,u: check_generic(s, "https://www.facebook.com/{u}", u), "x": check_x, "kaggle": lambda s,u: check_generic(s, "https://www.kaggle.com/{u}", u),
    "hackernews": check_hackernews, "linkedin": check_linkedin
}

# ---------- Worker (sequential by default for determinism) ----------
def worker_check(session: requests.Session, platform: str, username: str, delay: float) -> Dict[str,Any]:
    url = GENERIC_TEMPLATES.get(platform, "{u}").format(u=username)
    if STOP:
        return {"platform": platform, "url": url, "exists": None, "meta": {}, "skipped": True}
    checker = PLATFORM_CHECKERS.get(platform)
    try:
        if checker:
            exists, meta = checker(session, username)
        else:
            exists, meta = check_generic(session, GENERIC_TEMPLATES.get(platform, "{u}"), username)
        if exists:
            _print_found(f"{platform:15s} : {url}")
        else:
            _print_notfound(f"{platform:15s} : {url}")
        out = {"platform": platform, "url": url, "exists": exists, "meta": meta}
    except Exception as e:
        _print_notfound(f"{platform:15s} : error {e}")
        out = {"platform": platform, "url": url, "exists": False, "meta": {"error": str(e)}}
    time.sleep(delay)
    return out

# ---------- Scan orchestration ----------
def scan_username(session: requests.Session, username: str, platforms: List[str], delay: float) -> List[Dict[str,Any]]:
    results: List[Dict[str,Any]] = []
    for p in platforms:
        results.append(worker_check(session, p, username, delay))
        if STOP:
            break
    return results

def scan_email(session: requests.Session, email: str, platforms: List[str], delay: float, also_derive: bool) -> Dict[str,Any]:
    out: Dict[str,Any] = {"email": email, "gravatar": {}, "platform_hits": {}}
    try:
        h = hashlib.md5(email.strip().lower().encode()).hexdigest()
        jurl = f"https://www.gravatar.com/{h}.json"
        img = f"https://www.gravatar.com/avatar/{h}?d=404"
        out["gravatar"]["gravatar_json_url"] = jurl
        out["gravatar"]["gravatar_img_url"] = img
        r = session.get(jurl)
        if r.status_code == 200:
            out["gravatar"]["profile"] = r.json()
    except Exception:
        pass
    candidates: List[str] = []
    if also_derive:
        local = email.split("@",1)[0]
        parts = re.split(r"[.\-_+]", local)
        cands = {local}
        if len(parts) >= 2:
            first, *rest = parts
            last = rest[-1]
            if first and last:
                cands.update([f"{first}{last}", f"{first}_{last}", f"{first}.{last}", f"{first[0]}{last}"])
        candidates = sorted(list(cands))[:8]
    out["username_candidates"] = candidates
    for u in candidates:
        _print_info(f"[DERIVE] trying: {u}")
        out["platform_hits"][u] = scan_username(session, u, platforms, delay)
        if STOP:
            break
    return out

# ---------- IO helpers ----------
def write_json(path: str, obj: Dict[str,Any]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def flatten_csv(results: Dict[str,Any]) -> List[Dict[str,Any]]:
    rows: List[Dict[str,Any]] = []
    ts = results.get("timestamp")
    if "hits" in results:
        uname = results.get("username","")
        for h in results["hits"]:
            rows.append({"timestamp": ts, "mode":"username", "subject": uname, "platform": h.get("platform"), "url": h.get("url"), "exists": h.get("exists"), "title": (h.get("meta") or {}).get("title",""), "source": (h.get("meta") or {}).get("source","")})
    elif "email_scan" in results:
        grav = results["email_scan"].get("gravatar", {})
        rows.append({"timestamp": ts, "mode":"email", "subject": results.get("email"), "platform":"gravatar", "url": grav.get("gravatar_img_url",""), "exists": bool(grav.get("profile")), "title":"", "source":"gravatar"})
        for u,hits in results["email_scan"].get("platform_hits",{}).items():
            for h in hits:
                rows.append({"timestamp": ts, "mode":"email-derived", "subject": u, "platform": h.get("platform"), "url": h.get("url"), "exists": h.get("exists"), "title": (h.get("meta") or {}).get("title",""), "source": (h.get("meta") or {}).get("source","")})
    return rows

# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser(description="ShadowHunter v2.0 — high-accuracy OSINT username/email scanner (Twitch removed)")
    p.add_argument("target", help="username or email (auto-detected)")
    p.add_argument("--type", choices=["auto","username","email"], default="auto")
    p.add_argument("--platforms", nargs="*", default=list(GENERIC_TEMPLATES.keys()), help="List of platforms to check (defaults to built-in list). Twitch is not included.")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Per-request timeout (seconds)")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Delay between requests (seconds)")
    p.add_argument("--concurrency", type=int, default=DEFAULT_WORKERS, help="Number of concurrent workers (1 = sequential/deterministic)")
    p.add_argument("--also-derive", action="store_true", help="When target is an email, derive username candidates from local-part")
    p.add_argument("--out", default="shadowhunter_results.json", help="Output JSON path")
    p.add_argument("--csv", default=None, help="Optional CSV path")
    p.add_argument("--name", default=TOOL_NAME, help="Tool name to show in banner")
    p.add_argument("--author", default=DEFAULT_AUTHOR, help="Author name to show in banner")
    p.add_argument("--summary", action="store_true", help="Print concise final summary of positives")
    p.add_argument("--only-found", action="store_true", help="Write only positive hits into JSON/CSV")
    return p.parse_args()

# ---------- Main ----------
def main():
    global STOP
    args = parse_args()
    print(BANNER.format(tool_name=args.name, author=args.author))
    session = build_session(args.timeout)
    target = args.target.strip()
    mode_email = ("@" in target) if args.type == "auto" else (args.type == "email")
    platforms = args.platforms[:]
    if "twitch" in platforms:
        platforms = [p for p in platforms if p != "twitch"]

    results: Dict[str,Any] = {"name": args.name, "author": args.author, "tool":"ShadowHunter", "version":"2.0", "timestamp": int(time.time()), "params": {"platforms": platforms, "timeout": args.timeout, "delay": args.delay, "concurrency": args.concurrency}}

    try:
        if mode_email:
            results["email"] = target
            results["email_scan"] = scan_email(session, target, platforms, args.delay, args.also_derive)
            if args.only_found:
                filt = {"gravatar": results["email_scan"].get("gravatar",{}), "username_candidates": results["email_scan"].get("username_candidates",[])}
                ph = {}
                for u, hits in results["email_scan"].get("platform_hits", {}).items():
                    pos = [h for h in hits if h.get("exists") is True]
                    if pos:
                        ph[u] = pos
                filt["platform_hits"] = ph
                results["email_scan"] = filt
            if args.summary:
                grav = results["email_scan"].get("gravatar", {})
                if "profile" in grav:
                    _print_found(f"gravatar : {grav.get('gravatar_img_url')}")
                for u, hits in results["email_scan"].get("platform_hits", {}).items():
                    for h in hits:
                        if h.get("exists"):
                            _print_found(f"{u}@{h.get('platform')} : {h.get('url')}")
        else:
            results["username"] = target
            # sequential scan for stable, reproducible results (concurrency ignored by default)
            hits = scan_username(session, target, platforms, args.delay)
            results["hits"] = hits
            positives = [h for h in hits if h.get("exists") is True]
            results["found"] = positives
            if args.only_found:
                results["hits"] = positives
            if args.summary:
                if not positives:
                    _print_info(f"No public hits for username: {target}")
                else:
                    _print_found(f"Found username '{target}' on {len(positives)} platform(s):")
                    for h in positives:
                        print(f"   - {h.get('platform')}: {h.get('url')} (via { (h.get('meta') or {}).get('source') })")
    finally:
        out_json = os.path.abspath(args.out)
        write_json(out_json, results)
        _print_info(f"JSON written: {out_json}")
        if args.csv:
            rows = flatten_csv(results)
            if args.only_found:
                rows = [r for r in rows if r.get("exists") is True or r.get("platform") == "gravatar"]
            out_csv = os.path.abspath(args.csv)
            keys = list(rows[0].keys()) if rows else ["timestamp","mode","subject","platform","url","exists","title","source"]
            import csv as _csv
            with open(out_csv, "w", newline="", encoding="utf-8") as fh:
                w = _csv.DictWriter(fh, fieldnames=keys)
                w.writeheader()
                for r in rows:
                    w.writerow(r)
            _print_info(f"CSV written: {out_csv}")
        if STOP:
            print("\033[93m[!] Interrupted by user. Partial results saved.\033[0m")

if __name__ == "__main__":
    main()
