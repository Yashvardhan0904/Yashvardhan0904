#!/usr/bin/env python3
"""Generate a self-hosted GitHub profile statistics SVG."""

from __future__ import annotations

import html
import json
import os
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".github" / "generated" / "profile-stats.svg"
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    followers { totalCount }
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER, isFork: false, orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes { name stargazerCount forkCount primaryLanguage { name color } }
    }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions totalIssueContributions totalPullRequestContributions totalPullRequestReviewContributions
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def txt(x: int, y: int, value: object, size: int = 14, color: str = "#b8c0cc", weight: str = "400") -> str:
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}px" font-family="monospace" font-weight="{weight}">{esc(value)}</text>'


def box(x: int, y: int, width: int, height: int) -> str:
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" fill="#111820" stroke="#25303d"/>'


def fetch() -> dict:
    login = os.environ.get("GITHUB_USERNAME")
    token = os.environ.get("GITHUB_TOKEN")
    if not login or not token:
        raise SystemExit("GITHUB_USERNAME and GITHUB_TOKEN are required")
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=366)
    body = json.dumps({"query": QUERY, "variables": {"login": login, "from": f"{start}T00:00:00Z", "to": f"{end}T00:00:00Z"}}).encode()
    request = urllib.request.Request("https://api.github.com/graphql", data=body, headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "github-profile"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GitHub GraphQL request failed ({error.code}): {details}") from error
    if result.get("errors"):
        raise SystemExit(f"GitHub GraphQL returned errors: {json.dumps(result['errors'])}")
    return result["data"]["user"]


def render(user: dict) -> str:
    collection = user["contributionsCollection"]
    calendar = collection["contributionCalendar"]
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    repos = user["repositories"]["nodes"]
    languages = Counter(
        language["name"]
        for repo in repos
        if (language := repo.get("primaryLanguage") or {}).get("name")
    )
    stars = sum(repo["stargazerCount"] for repo in repos)
    forks = sum(repo["forkCount"] for repo in repos)
    active = {item["date"]: item["contributionCount"] for item in days}
    cursor = date.today()
    if active.get(str(cursor), 0) == 0:
        cursor -= timedelta(days=1)
    current = 0
    while active.get(str(cursor), 0) > 0:
        current += 1
        cursor -= timedelta(days=1)
    longest = active_days = run = 0
    for item in days:
        if item["contributionCount"]:
            active_days += 1
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 1260" role="img" aria-labelledby="title">', '<title id="title">Live GitHub statistics for Yashvardhan0904</title>', '<rect width="900" height="1260" rx="14" fill="#0d0d0d"/>']
    svg.append(txt(42, 48, "GITHUB STATISTICS / LIVE", 17, "#cc0000", "700"))
    svg.append(txt(858, 48, date.today().isoformat(), 12, "#6f7782", "700"))
    svg.append('<path d="M42 68H858" stroke="#26303c"/>')
    metrics = [("CONTRIBUTIONS", calendar["totalContributions"]), ("COMMITS", collection["totalCommitContributions"]), ("PULL REQUESTS", collection["totalPullRequestContributions"]), ("ISSUES", collection["totalIssueContributions"]), ("CODE REVIEWS", collection["totalPullRequestReviewContributions"]), ("PUBLIC REPOSITORIES", user["repositories"]["totalCount"]), ("STARS EARNED", stars), ("FORKS", forks), ("FOLLOWERS", user["followers"]["totalCount"])]
    for index, (label, value) in enumerate(metrics):
        x = 42 + (index % 3) * 274
        y = 92 + (index // 3) * 88
        svg.append(box(x, y, 252, 68))
        svg.append(txt(x + 16, y + 24, label, 10, "#6f7782", "700"))
        svg.append(txt(x + 16, y + 53, f"{value:,}", 24, "#ffffff", "700"))

    svg.append(txt(42, 380, "CONTRIBUTION ACTIVITY", 12, "#cc0000", "700"))
    svg.append(box(42, 398, 816, 186))
    palette = ["#17202a", "#3b1717", "#711717", "#a51e1e", "#cc0000"]
    for index, day in enumerate(days[-371:]):
        column, row = divmod(index, 7)
        level = min(4, day["contributionCount"] // 4 + (1 if day["contributionCount"] else 0))
        svg.append(f'<rect x="{68 + column * 16}" y="{425 + row * 16}" width="11" height="11" rx="2" fill="{palette[level]}"/>')
    svg.append(txt(68, 565, "LESS", 10, "#6f7782", "700"))
    for index, color in enumerate(palette):
        svg.append(f'<rect x="105" y="556" width="11" height="11" rx="2" fill="{color}" transform="translate({index * 17} 0)"/>')
    svg.append(txt(196, 565, "MORE", 10, "#6f7782", "700"))

    svg.append(txt(42, 636, "STREAKS", 12, "#cc0000", "700"))
    for index, (label, value) in enumerate([("CURRENT", current), ("LONGEST", longest), ("ACTIVE DAYS", active_days)]):
        x = 42 + index * 274
        svg.append(box(x, 654, 252, 92))
        svg.append(txt(x + 16, 682, label, 10, "#6f7782", "700"))
        svg.append(txt(x + 16, 720, f"{value:,} DAYS", 23, "#ffffff", "700"))

    svg.append(txt(42, 798, "LANGUAGE DISTRIBUTION", 12, "#cc0000", "700"))
    svg.append(box(42, 816, 816, 126))
    total = sum(languages.values()) or 1
    cursor_x = 68
    for language, count in languages.most_common(8):
        width = max(10, int(760 * count / total))
        color = next(
            (
                (repo.get("primaryLanguage") or {}).get("color")
                for repo in repos
                if (repo.get("primaryLanguage") or {}).get("name") == language
            ),
            "#cc0000",
        )
        svg.append(f'<rect x="{cursor_x}" y="845" width="{width}" height="16" rx="4" fill="{color or "#cc0000"}"/>')
        svg.append(txt(cursor_x, 886, f"{language} {count / total:.0%}", 10, "#b8c0cc", "700"))
        cursor_x += width + 12

    svg.append(txt(42, 1000, "TOP PUBLIC REPOSITORIES", 12, "#cc0000", "700"))
    svg.append(box(42, 1018, 816, 174))
    for index, repo in enumerate(repos[:5]):
        y = 1052 + index * 28
        svg.append(txt(68, y, repo["name"][:32], 12, "#ffffff", "700"))
        svg.append(txt(830, y, f"STARS {repo['stargazerCount']:,}  FORKS {repo['forkCount']:,}", 10, "#b8c0cc", "700"))
    svg.append(txt(42, 1230, "SOURCE: GITHUB GRAPHQL API / PUBLIC DATA", 10, "#4c5663", "700"))
    svg.append('</svg>')
    return "".join(svg)


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(fetch()), encoding="utf-8")
