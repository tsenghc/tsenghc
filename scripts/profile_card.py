#!/usr/bin/env python3
"""Render the profile card (light and dark SVG) from GitHub contribution data.

Layout: name, role and three headline numbers on the left; a radial
"year ring" on the right, one spoke per week for the last 52 weeks.

Usage:
    GITHUB_TOKEN=... python3 scripts/profile_card.py [--user tsenghc] [--out cards]

Only the Python standard library is used, so the workflow needs no install step.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
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

ROLE = "SRE Engineer"

# One accent colour per theme; spokes blend from `track` to `accent` by intensity.
THEMES = {
    "light": {
        "bg": "#ffffff", "border": "#e5e7eb", "text": "#0f172a", "muted": "#64748b",
        "faint": "#94a3b8", "track": "#e2e8f0", "accent": "#0d9488", "glow": "#5eead4",
        "rule": "#e2e8f0",
    },
    "dark": {
        "bg": "#0d1117", "border": "#30363d", "text": "#f0f6fc", "muted": "#8b949e",
        "faint": "#6e7681", "track": "#21262d", "accent": "#2dd4bf", "glow": "#99f6e4",
        "rule": "#21262d",
    },
}

WIDTH, HEIGHT = 720, 260
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"


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
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    counts = [d["contributionCount"] for d in days]

    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)

    weekly = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks][-52:]
    first_days = [w["contributionDays"][0]["date"] for w in weeks][-52:]
    return {
        "total": cal["totalContributions"],
        "longest": longest,
        "active": sum(1 for c in counts if c > 0),
        "days": len(counts),
        "weekly": weekly,
        "week_start": first_days,
        "since": user["createdAt"][:4],
        "location": user.get("location") or "",
    }


def mix(a: str, b: str, t: float) -> str:
    """Linear blend between two #rrggbb colours."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def ring(s: dict, t: dict, cx: float, cy: float) -> str:
    """52 spokes around a circle, starting at 12 o'clock, oldest week first."""
    inner, span = 46, 50
    weekly = s["weekly"]
    n = len(weekly) or 1
    peak = max(weekly) or 1
    out = [f'<circle cx="{cx}" cy="{cy}" r="{inner - 8}" fill="none" stroke="{t["rule"]}"/>']

    for k, v in enumerate(weekly):
        ang = -math.pi / 2 + 2 * math.pi * k / n
        level = v / peak
        length = 3 + span * math.sqrt(level)  # sqrt keeps quiet weeks visible
        x1, y1 = cx + inner * math.cos(ang), cy + inner * math.sin(ang)
        x2, y2 = cx + (inner + length) * math.cos(ang), cy + (inner + length) * math.sin(ang)
        color = mix(t["track"], t["accent"], 0.25 + 0.75 * level) if v else t["track"]
        out.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" '
            f'stroke-width="4.2" stroke-linecap="round"><title>week of {s["week_start"][k]}: {v}</title></line>'
        )
        if k == n - 1:  # mark the current week
            out.append(f'<circle cx="{x2:.1f}" cy="{y2:.1f}" r="4" fill="{t["glow"]}"/>')

    # Quarter labels: the month of the week sitting at each quarter of the ring.
    for q in range(4):
        k = min(n - 1, q * n // 4)
        month = dt.date.fromisoformat(s["week_start"][k]).strftime("%b").upper()
        ang = -math.pi / 2 + 2 * math.pi * k / n
        r = inner - 20
        x, y = cx + r * math.cos(ang), cy + r * math.sin(ang) + 3.5
        out.append(f'<text x="{x:.1f}" y="{y:.1f}" class="tick" text-anchor="middle">{month}</text>')
    return "".join(out)


def render(login: str, s: dict, t: dict) -> str:
    x0 = 40
    sub = " · ".join(p for p in (ROLE, s["location"]) if p)
    metrics = [
        (f'{s["total"]:,}', "CONTRIBUTIONS"),
        (f'{s["longest"]}d', "LONGEST STREAK"),
        (f'{s["active"]}/{s["days"]}', "ACTIVE DAYS"),
    ]
    cols = "".join(
        f'<text x="{x0 + i * 140}" y="178" class="num">{escape(v)}</text>'
        f'<text x="{x0 + i * 140}" y="200" class="label">{label}</text>'
        for i, (v, label) in enumerate(metrics)
    )
    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{escape(login)}: {s['total']:,} contributions in the last year">
  <style>
    text {{ font-family: {SANS}; }}
    .name {{ font-size: 34px; font-weight: 700; letter-spacing: -0.5px; fill: {t['text']}; }}
    .sub {{ font-size: 15px; fill: {t['muted']}; }}
    .num {{ font-size: 26px; font-weight: 650; fill: {t['text']}; font-variant-numeric: tabular-nums; }}
    .label {{ font-size: 10.5px; font-weight: 600; letter-spacing: 1.4px; fill: {t['muted']}; }}
    .foot {{ font-size: 11px; fill: {t['faint']}; }}
    .tick {{ font-size: 9px; font-weight: 600; letter-spacing: 0.8px; fill: {t['faint']}; }}
  </style>
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="14" fill="{t['bg']}" stroke="{t['border']}"/>
  <rect x="{x0}" y="44" width="28" height="4" rx="2" fill="{t['accent']}"/>
  <text x="{x0}" y="92" class="name">{escape(login)}</text>
  <text x="{x0}" y="118" class="sub">{escape(sub)}</text>
  <line x1="{x0}" y1="140" x2="{x0 + 400}" y2="140" stroke="{t['rule']}"/>
  {cols}
  <text x="{x0}" y="232" class="foot">last 52 weeks · on GitHub since {s['since']} · updated {updated}</text>
  {ring(s, t, cx=585, cy=HEIGHT / 2)}
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
    print(json.dumps({k: v for k, v in s.items() if k not in ("weekly", "week_start")}))


if __name__ == "__main__":
    main()
