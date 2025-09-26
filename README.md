ShadowHunter 2.0

by MrDark0x7

Sleek · Conservative · Auditable
An OSINT username & email scanner designed for accuracy (minimizes false positives) and reproducible results.

ShadowHunter 2.0 scans a username (or derives usernames from an email) across many social, code and media platforms and reports which ones exist. It’s intentionally conservative — when in doubt, it prefers NOTFOUND to avoid false positives. Every positive hit includes a meta.source explaining why it was accepted.

<img width="790" height="489" alt="image" src="https://github.com/user-attachments/assets/a49d5573-dfe7-4fa3-8894-5f0b9c50a680" />

✨ Highlights

Author: MrDark0x7

Deterministic by default (sequential requests) for consistent results

Conservative, site-specific heuristics (uses APIs / embedded JSON where available)

Outputs: JSON (primary) and optional CSV — both are auditable (meta.source)

Twitch removed (per preference) — not checked by default

✅ Features

Scan by username or email (auto-detects).

Derive likely usernames from an email local-part (--also-derive) and scan them.

Site-specific checkers: GitHub (API), Reddit (about.json), GitLab, StackOverflow, HackerNews, X (Twitter), YouTube, Instagram, Steam, LinkedIn, and more.

JSON output contains meta.source for every found record (audit trail).

CLI banner shows tool name & author.

Single-file Python script, minimal deps.

⚙️ Requirements

Python 3.8+

Install dependencies:

pip install requests lxml

🧭 Quickstart

Save the script as ShadowHunter.py, make it executable:

chmod +x ShadowHunter.py


Run a username scan:

python3 ShadowHunter.py MrDark0x7 --summary --out MrDark0x7.json


Run an email scan and derive usernames:

python3 ShadowHunter.py alice@example.com --also-derive --summary --out alice.json --csv alice.csv

🧾 CLI Summary
usage: ShadowHunter.py target [--type auto|username|email] [--platforms ...]
                             [--timeout N] [--delay SECONDS] [--concurrency N]
                             [--also-derive] [--out PATH] [--csv PATH]
                             [--name TOOLNAME] [--author AUTHOR]
                             [--summary] [--only-found]


Key flags:

target — username or email (auto-detected by @)

--also-derive — when target is an email, derive username candidates

--out — JSON output path (default shodowhunter_results.json)

--csv — optional CSV output

--summary — short final summary of positives

--only-found — write only positives to output (useful for reports)

--delay / --timeout — tune pacing to avoid blocks

🔍 Output format (JSON)

Top-level fields:

name, author, tool, version, timestamp, params

If username mode: username, hits (array)

If email mode: email, email_scan with gravatar, username_candidates, platform_hits

Example hit:

{
  "platform": "github",
  "url": "https://github.com/MrDark0x7",
  "exists": true,
  "meta": {
    "source": "api.github.com",
    "name": "MrDark0x7",
    "bio": "Example bio"
  }
}


meta.source = audit trail (e.g. api.github.com, reddit-about-json, instagram-embedded-json, gitlab-html-marker, x-og).

🧩 Platforms (defaults)

Includes: github, gitlab, reddit, x (Twitter), youtube, instagram, tiktok, steam, hackernews, stack_overflow, linkedin, medium, devto, pinterest, soundcloud, vimeo, kaggle, keybase, facebook, etc.

Note: twitch is intentionally not included.

⚖️ Accuracy & Ethics

Accuracy approach: Prefer strong signals (APIs, embedded JSON, known DOM markers). When a page is ambiguous (login-gated, heavy JS, Cloudflare), ShadowHunter does not assume a match.

Ethics: Use responsibly. Only scan accounts you are authorized to investigate (research, pentest with permission, triage). Respect platform ToS and privacy. The tool author is not responsible for misuse.

🛠️ Troubleshooting

False NOTFOUND: could be a login-gated page or regional block. Try a higher timeout, lower concurrency (--concurrency 1), or API tokens where available.

Cloudflare / 429s: increase --delay, decrease --concurrency.

Inconsistent runs: run with --concurrency 1 for deterministic behavior.

🔧 Extending ShadowHunter

Add a check_<platform> function for new platforms and register it in the platform map.

Add API token support (env vars or CLI flags) to improve reliability and rate limits (GitHub, X, YouTube).

Optional: add a headless-browser fallback for JS-heavy pages (Selenium/Playwright) — note this increases complexity and fragility.

🧪 Contribution

Fork the repo.

Create a feature branch.

Add tests / mocks for any new site-checker.

Open a PR with a clear description and examples.

Please include JSON output samples when reporting false positives/negatives so maintainers can audit meta.source.

📄 LICENSE

Suggested: MIT License
(Place an actual LICENSE in your repository if you accept these terms.)
