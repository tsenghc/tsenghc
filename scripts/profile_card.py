#!/usr/bin/env python3
"""Render the terminal-style profile card (light and dark SVG) from GitHub data.

Usage:
    GITHUB_TOKEN=... python3 scripts/profile_card.py [--user tsenghc] [--out cards]

Only the Python standard library is used, so the workflow needs no install step.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.request
from html import escape

QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    location
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

ROLE = "SRE engineer"

THEMES = {
    "light": {
        "bg": "#ffffff", "bar": "#f6f8fa", "border": "#d0d7de", "title": "#57606a",
        "prompt": "#1a7f37", "cmd": "#24292f", "out": "#57606a", "accent": "#0969da",
        "spark": "#1a7f37", "spark_bg": "#eaeef2",
        "dots": ("#ff5f57", "#febc2e", "#28c840"),
    },
    "dark": {
        "bg": "#0d1117", "bar": "#161b22", "border": "#30363d", "title": "#8b949e",
        "prompt": "#3fb950", "cmd": "#e6edf3", "out": "#8b949e", "accent": "#58a6ff",
        "spark": "#3fb950", "spark_bg": "#21262d",
        "dots": ("#ff5f57", "#febc2e", "#28c840"),
    },
}

WIDTH, HEIGHT = 720, 326
FONT = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"


def fetch(login: str, token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    return data["data"]["user"]


def stats(user: dict) -> dict:
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    counts = [d["contributionCount"] for d in days]

    # Current streak: today may still be empty, so start from yesterday in that case.
    i = len(counts) - 1
    if i >= 0 and counts[i] == 0:
        i -= 1
    current = 0
    while i >= 0 and counts[i] > 0:
        current += 1
        i -= 1

    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)

    weekly = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]][-52:]
    return {
        "total": cal["totalContributions"],
        "current": current,
        "longest": longest,
        "active": sum(1 for c in counts if c > 0),
        "days": len(counts),
        "weekly": weekly,
        "since": user["createdAt"][:4],
        "location": user.get("location") or "",
    }


def render(login: str, s: dict, theme: dict) -> str:
    t = theme
    x0, line = 28, 24
    y = 74

    def prompt(cmd: str) -> str:
        return (
            f'<text x="{x0}" y="{y}"><tspan fill="{t["prompt"]}">$</tspan>'
            f'<tspan fill="{t["cmd"]}"> {escape(cmd)}</tspan></text>'
        )

    def out(text: str, color: str | None = None) -> str:
        return f'<text x="{x0}" y="{y}" fill="{color or t["out"]}">{text}</text>'

    parts = []
    parts.append(prompt("whoami"))
    y += line
    who = " · ".join(p for p in (login, ROLE, s["location"]) if p)
    parts.append(out(f'<tspan fill="{t["accent"]}">{escape(login)}</tspan>{escape(who[len(login):])}'))
    y += line + 12
    parts.append(prompt("uptime --contributions"))
    y += line
    parts.append(out(
        f'<tspan fill="{t["cmd"]}" font-weight="700">{s["total"]:,}</tspan> contributions in the last year'
    ))
    y += line
    parts.append(out(
        f'streak {s["current"]} days · longest {s["longest"]} days · since {s["since"]}'
    ))
    y += line + 12
    parts.append(prompt("sparkline --weeks 52"))

    # Sparkline: one bar per week, scaled to the busiest week.
    top = y + 12
    h = 44
    peak = max(s["weekly"]) or 1
    gap = 3
    step = (WIDTH - 2 * x0 + gap) / max(len(s["weekly"]), 1)
    bw = step - gap
    bars = []
    for k, v in enumerate(s["weekly"]):
        bx = round(x0 + k * step, 1)
        bh = max(2, round(h * v / peak)) if v else 2
        fill = t["spark"] if v else t["spark_bg"]
        bars.append(
            f'<rect x="{bx}" y="{top + h - bh}" width="{bw:.1f}" height="{bh}" rx="1.5" fill="{fill}">'
            f"<title>{v} contributions</title></rect>"
        )
    cursor_y = top + h + 34
    cursor = (
        f'<text x="{x0}" y="{cursor_y}"><tspan fill="{t["prompt"]}">$</tspan></text>'
        f'<rect class="cursor" x="{x0 + 16}" y="{cursor_y - 13}" width="9" height="16" fill="{t["cmd"]}"/>'
    )

    dots = "".join(
        f'<circle cx="{20 + n * 18}" cy="18" r="5.5" fill="{c}"/>' for n, c in enumerate(t["dots"])
    )
    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{escape(login)}: {s['total']:,} contributions in the last year">
  <style>
    text {{ font-family: {FONT}; font-size: 14px; }}
    .title {{ font-size: 12px; }}
    .cursor {{ animation: blink 1.1s steps(1) infinite; }}
    @keyframes blink {{ 50% {{ opacity: 0; }} }}
  </style>
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="10" fill="{t['bg']}" stroke="{t['border']}"/>
  <path d="M0.5 36 V10.5 a10 10 0 0 1 10 -10 H{WIDTH - 10.5} a10 10 0 0 1 10 10 V36 Z" fill="{t['bar']}"/>
  <line x1="0.5" y1="36" x2="{WIDTH - 0.5}" y2="36" stroke="{t['border']}"/>
  {dots}
  <text class="title" x="{WIDTH / 2}" y="22" text-anchor="middle" fill="{t['title']}">{escape(login)}@github: ~</text>
  <text class="title" x="{WIDTH - 16}" y="22" text-anchor="end" fill="{t['title']}">{updated}</text>
  {''.join(parts)}
  {''.join(bars)}
  {cursor}
</svg>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "tsenghc"))
    ap.add_argument("--out", default="cards")
    args = ap.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")

    s = stats(fetch(args.user, token))
    os.makedirs(args.out, exist_ok=True)
    for name, theme in THEMES.items():
        path = os.path.join(args.out, f"profile-{name}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(render(args.user, s, theme))
        print(f"wrote {path}")
    print(json.dumps({k: v for k, v in s.items() if k != "weekly"}))


if __name__ == "__main__":
    main()
