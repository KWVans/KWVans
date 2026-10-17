#!/usr/bin/env python3
"""Build a private-safe language card from every accessible and contributed repo."""

from collections import defaultdict
from html import escape
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LOGIN = "KWVans"
API = "https://api.github.com"
GRAPHQL_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    topRepositories(
      first: 100
      after: $cursor
      orderBy: { field: PUSHED_AT, direction: DESC }
    ) {
      nodes { nameWithOwner }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

COLORS = ["#54d6ff", "#a78bfa", "#73ddb2", "#ffc078", "#f778ba", "#79c0ff", "#f85149", "#d2a8ff"]


def headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def api_json(url: str, token: str) -> dict | list:
    request = Request(url, headers=headers(token))
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def list_accessible_repositories(token: str) -> dict[str, str]:
    repositories = {}
    page = 1
    while True:
        query = urlencode({
            "affiliation": "owner,collaborator,organization_member",
            "visibility": "all",
            "per_page": 100,
            "page": page,
        })
        result = api_json(f"{API}/user/repos?{query}", token)
        if not isinstance(result, list):
            raise RuntimeError("GitHub did not return the accessible repository list.")
        for repo in result:
            repositories[repo["full_name"].lower()] = repo["full_name"]
        if len(result) < 100:
            return repositories
        page += 1


def list_contributed_repositories(token: str) -> dict[str, str]:
    repositories = {}
    cursor = None
    while True:
        payload = json.dumps({
            "query": GRAPHQL_QUERY,
            "variables": {"login": LOGIN, "cursor": cursor},
        }).encode("utf-8")
        request = Request(
            f"{API}/graphql",
            data=payload,
            headers={**headers(token), "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
        if result.get("errors"):
            raise RuntimeError("GitHub could not return the repositories with contributions.")
        connection = result.get("data", {}).get("user", {}).get("topRepositories")
        if connection is None:
            raise RuntimeError("GitHub did not return repositories with contributions for KWVans.")
        for repo in connection["nodes"]:
            repositories[repo["nameWithOwner"].lower()] = repo["nameWithOwner"]
        if not connection["pageInfo"]["hasNextPage"]:
            return repositories
        cursor = connection["pageInfo"]["endCursor"]


def fetch_language_bytes(full_name: str, token: str) -> dict[str, int]:
    owner, name = full_name.split("/", 1)
    result = api_json(f"{API}/repos/{owner}/{name}/languages", token)
    return {language: int(size) for language, size in result.items()}


def render_svg(language_bytes: dict[str, int]) -> str:
    ranked = sorted(language_bytes.items(), key=lambda item: item[1], reverse=True)[:8]
    total = sum(language_bytes.values())
    if not ranked or total == 0:
        raise RuntimeError("GitHub returned no language data for the accessible repositories.")

    width = 500
    row_height = 28
    height = 86 + row_height * len(ranked)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Most used languages across owned and contributed repositories</title>',
        '<desc id="desc">Top programming languages by GitHub-reported code size across all repositories accessible to KWVans and repositories where KWVans contributed.</desc>',
        '<rect width="100%" height="100%" rx="10" fill="#1a1b27" stroke="#30363d"/>',
        '<text x="22" y="31" fill="#70a5fd" font-family="Segoe UI,Arial,sans-serif" font-size="17" font-weight="600">Most Used Languages</text>',
        '<text x="22" y="51" fill="#8b949e" font-family="Segoe UI,Arial,sans-serif" font-size="10">Owned, private, organization, collaborator &amp; contributed repositories</text>',
    ]

    bar_x = 175
    bar_width = 230
    for index, (language, byte_count) in enumerate(ranked):
        y = 77 + index * row_height
        percent = byte_count * 100 / total
        filled = max(2, bar_width * percent / 100)
        color = COLORS[index % len(COLORS)]
        parts.extend([
            f'<text x="22" y="{y + 12}" fill="#c9d1d9" font-family="Segoe UI,Arial,sans-serif" font-size="11">{escape(language)}</text>',
            f'<rect x="{bar_x}" y="{y + 2}" width="{bar_width}" height="10" rx="5" fill="#30363d"/>',
            f'<rect x="{bar_x}" y="{y + 2}" width="{filled:.2f}" height="10" rx="5" fill="{color}"/>',
            f'<text x="{bar_x + bar_width + 14}" y="{y + 12}" fill="#c9d1d9" font-family="Segoe UI,Arial,sans-serif" font-size="11">{percent:.2f}%</text>',
        ])
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    token = os.environ.get("GH_STATS_TOKEN")
    if not token:
        raise SystemExit("GH_STATS_TOKEN is required to generate the top languages card.")

    repositories = list_accessible_repositories(token)
    repositories.update(list_contributed_repositories(token))
    totals = defaultdict(int)
    for full_name in repositories.values():
        for language, size in fetch_language_bytes(full_name, token).items():
            totals[language] += size

    output = Path("profile/top-langs.svg")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_svg(dict(totals)), encoding="utf-8")
    print(f"Generated language card from {len(repositories)} accessible or contributed repositories; repository names were not logged.")


if __name__ == "__main__":
    main()
