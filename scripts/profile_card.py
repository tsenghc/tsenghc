#!/usr/bin/env python3
"""Render the profile banner (SVG) from GitHub data.

Layout: name and role on the left, stars / public repos / language share on
the right, and a "signal" trace of weekly contributions for the last 52 weeks
across the bottom.

Usage:
    GITHUB_TOKEN=... python3 scripts/profile_card.py [--user tsenghc] [--out cards]

Only the Python standard library is used, so the workflow needs no install step.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from collections import defaultdict
from html import escape

QUERY = """
query($login: String!) {
  user(login: $login) {
    location
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount } }
      }
    }
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 20) { edges { size node { name color } } }
      }
    }
  }
}
"""

ROLE = "Site Reliability Engineer"
TOP_LANGS = 4

W, H = 800, 280
X0, X1 = 40, 760  # horizontal content bounds
RIGHT_W = 300  # width of the stars / languages block

C = {
    "bg": "#0b1220", "border": "#1e293b", "name": "#f1f5f9", "sub": "#94a3b8",
    "stat": "#e2e8f0", "dim": "#64748b", "grid": "#1e293b", "base": "#334155",
    "signal": "#38bdf8", "other": "#64748b",
}
SANS = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"


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
    weekly = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]][-52:]

    repos = user["repositories"]
    size: dict[str, int] = defaultdict(int)
    color: dict[str, str] = {}
    for r in repos["nodes"]:
        for e in r["languages"]["edges"]:
            size[e["node"]["name"]] += e["size"]
            color[e["node"]["name"]] = e["node"]["color"] or C["other"]
    total = sum(size.values()) or 1
    ranked = sorted(size.items(), key=lambda kv: -kv[1])
    langs = [(n, color[n], 100 * s / total) for n, s in ranked[:TOP_LANGS]]
    rest = sum(s for _, s in ranked[TOP_LANGS:])
    if rest:
        langs.append(("其他", C["other"], 100 * rest / total))

    return {
        "total": cal["totalContributions"],
        "weekly": weekly,
        "stars": sum(r["stargazerCount"] for r in repos["nodes"]),
        "repos": repos["totalCount"],
        "langs": langs,
        "location": user.get("location") or "",
    }


def text_width(s: str, size: float) -> float:
    """Rough monospace width; CJK glyphs are about twice as wide."""
    return sum(size * (1.0 if ord(ch) > 0x2E80 else 0.6) for ch in s)


def languages(s: dict) -> str:
    """Stacked share bar plus a right-aligned, wrapping legend."""
    x_left = X1 - RIGHT_W
    out = [f'<clipPath id="lb"><rect x="{x_left}" y="60" width="{RIGHT_W}" height="6" rx="3"/></clipPath><g clip-path="url(#lb)">']
    gap = 2
    usable = RIGHT_W - gap * (len(s["langs"]) - 1)
    x = x_left
    for _, col, pct in s["langs"]:
        w = usable * pct / 100
        out.append(f'<rect x="{x:.1f}" y="60" width="{w:.1f}" height="6" fill="{col}"/>')
        x += w + gap
    out.append("</g>")

    # Each row is one <text> starting under the bar, so the renderer flows the
    # items itself; the width estimate only decides where rows break.
    rows: list[list[tuple[str, str]]] = [[]]
    used = 0.0
    for n, col, p in s["langs"]:
        label = f"{n} {p:.1f}%"
        w = text_width("● " + label, 11)
        if rows[-1] and used + 14 + w > RIGHT_W:
            rows.append([])
            used = 0.0
        used += (14 if rows[-1] else 0) + w
        rows[-1].append((label, col))
    for r, row in enumerate(rows):
        spans = "".join(
            f'<tspan dx="{14 if i else 0}" fill="{col}">●</tspan><tspan dx="5">{escape(label)}</tspan>'
            for i, (label, col) in enumerate(row)
        )
        out.append(f'<text x="{x_left}" y="{86 + r * 17}" class="legend">{spans}</text>')
    return "".join(out)


def signal(s: dict) -> str:
    weekly = s["weekly"] or [0]
    n, peak = len(weekly), max(weekly) or 1
    step = (X1 - X0) / max(n - 1, 1)
    pts = [(X0 + i * step, 228 - 84 * v / peak) for i, v in enumerate(weekly)]
    line = " ".join(f"{'L' if i else 'M'}{x:.1f} {y:.1f}" for i, (x, y) in enumerate(pts))
    lx, ly = pts[-1]
    return (
        f'<line x1="{X0}" y1="150" x2="{X1}" y2="150" stroke="{C["grid"]}" stroke-dasharray="2 6"/>'
        f'<line x1="{X0}" y1="190" x2="{X1}" y2="190" stroke="{C["grid"]}" stroke-dasharray="2 6"/>'
        f'<line x1="{X0}" y1="230" x2="{X1}" y2="230" stroke="{C["base"]}"/>'
        f'<path d="{line} L{lx:.1f} 230 L{X0} 230 Z" fill="{C["signal"]}" fill-opacity="0.12"/>'
        f'<path d="{line}" fill="none" stroke="{C["signal"]}" stroke-width="2" stroke-linejoin="round"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="9" fill="{C["signal"]}" fill-opacity="0.2"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{C["signal"]}"/>'
        f'<text x="{X0}" y="253" class="foot">weekly contributions · last 52 weeks</text>'
        f'<text x="{X1}" y="253" class="foot hi" text-anchor="end">peak {peak} · now {weekly[-1]}</text>'
    )


def render(login: str, s: dict) -> str:
    sub = " · ".join(p for p in (ROLE, s["location"]) if p)
    stars = f'★ {s["stars"]:,} stars  ·  {s["repos"]} public repos'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(login)}: {s['total']:,} contributions in the last year, {s['stars']} stars, {s['repos']} public repos">
  <style>
    text {{ font-family: {SANS}; }}
    .name {{ font-size: 40px; font-weight: 700; letter-spacing: -0.8px; fill: {C['name']}; }}
    .sub {{ font-size: 15px; fill: {C['sub']}; }}
    .stat {{ font-family: {MONO}; font-size: 12px; fill: {C['stat']}; white-space: pre; }}
    .legend {{ font-family: {MONO}; font-size: 11px; fill: {C['sub']}; }}
    .foot {{ font-family: {MONO}; font-size: 11px; fill: {C['dim']}; }}
    .hi {{ fill: {C['sub']}; }}
  </style>
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="{C['bg']}" stroke="{C['border']}"/>
  <text x="{X0}" y="76" class="name">{escape(login)}</text>
  <text x="{X0}" y="110" class="sub">{escape(sub)}</text>
  <text x="{X1}" y="48" class="stat" text-anchor="end" xml:space="preserve">{escape(stars)}</text>
  {languages(s)}
  {signal(s)}
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
    path = os.path.join(args.out, "profile.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(args.user, s))
    print(f"wrote {path}")
    print(json.dumps({k: v for k, v in s.items() if k != "weekly"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
