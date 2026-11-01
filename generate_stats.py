"""Gera assets/top-languages.svg e assets/stats.svg usando a API GraphQL do GitHub.

Precisa da variável de ambiente GH_TOKEN (token com escopo `repo` para
contar repositórios e linguagens privados).
"""
import json
import os
import urllib.request
from datetime import datetime, timezone
from html import escape

USER = os.environ.get("GH_USER", "analuizabirck")
TOKEN = os.environ["GH_TOKEN"]
API = "https://api.github.com/graphql"
PINK = "#fe428e"
BG = "#0d1117"
BORDER = "#ffffff"
FONT = "Segoe UI, Ubuntu, Helvetica, Arial, sans-serif"


def gql(query, variables=None):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-stats",
        },
    )
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


REPOS_QUERY = """
query($login:String!, $cursor:String) {
  user(login:$login) {
    createdAt
    followers { totalCount }
    all: repositories(ownerAffiliations: OWNER) { totalCount }
    repositories(first: 50, after: $cursor, ownerAffiliations: OWNER, isFork: false) {
      pageInfo { hasNextPage endCursor }
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
        releases(first: 50) {
          nodes { releaseAssets(first: 50) { nodes { downloadCount } } }
        }
      }
    }
  }
}
"""

COMMITS_QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""


def fetch_repos():
    cursor, nodes, info = None, [], None
    while True:
        user = gql(REPOS_QUERY, {"login": USER, "cursor": cursor})["user"]
        info = info or user
        page = user["repositories"]
        nodes += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return info, nodes
        cursor = page["pageInfo"]["endCursor"]


def fetch_commits(created_at):
    now = datetime.now(timezone.utc)
    total = 0
    for year in range(int(created_at[:4]), now.year + 1):
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = min(datetime(year + 1, 1, 1, tzinfo=timezone.utc), now)
        c = gql(COMMITS_QUERY, {
            "login": USER,
            "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })["user"]["contributionsCollection"]
        total += c["totalCommitContributions"] + c["restrictedContributionsCount"]
    return total


def card(width, height, title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect x="0.5" y="0.5" rx="8" width="{width - 1}" height="{height - 1}" fill="{BG}" stroke="{BORDER}"/>
  <text x="25" y="35" font-family="{FONT}" font-size="18" font-weight="600" fill="{PINK}">{escape(title)}</text>
{body}
</svg>
"""


def languages_svg(repos):
    sizes, colors = {}, {}
    for repo in repos:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            sizes[name] = sizes.get(name, 0) + e["size"]
            colors[name] = e["node"]["color"] or "#8b949e"
    total = sum(sizes.values()) or 1
    top = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)[:8]
    shown = sum(s for _, s in top)

    width, inner = 495, 445
    parts, x = [], 25.0
    for name, size in top:
        w = inner * size / shown
        parts.append(f'<rect x="{x:.2f}" y="55" width="{w:.2f}" height="10" fill="{colors[name]}"/>')
        x += w
    bar = (
        f'  <clipPath id="bar"><rect x="25" y="55" width="{inner}" height="10" rx="5"/></clipPath>\n'
        f'  <g clip-path="url(#bar)">' + "".join(parts) + "</g>"
    )

    legend, rows = [], (len(top) + 1) // 2
    for i, (name, size) in enumerate(top):
        col, row = divmod(i, rows)
        cx, cy = 25 + col * 225, 95 + row * 24
        pct = 100 * size / shown
        legend.append(
            f'  <circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{colors[name]}"/>\n'
            f'  <text x="{cx + 18}" y="{cy}" font-family="{FONT}" font-size="13" fill="#ffffff">'
            f'{escape(name)} <tspan fill="#8b949e">{pct:.1f}%</tspan></text>'
        )
    height = 95 + rows * 24 + 8
    return card(width, height, "Linguagens mais utilizadas", bar + "\n" + "\n".join(legend))


def stats_svg(stats):
    rows = [
        ("Repositórios (públicos + privados)", stats["repos"]),
        ("Commits", stats["commits"]),
        ("Seguidores", stats["followers"]),
        ("Downloads", stats["downloads"]),
    ]
    lines = []
    for i, (label, value) in enumerate(rows):
        y = 75 + i * 30
        lines.append(
            f'  <text x="25" y="{y}" font-family="{FONT}" font-size="14" fill="#ffffff">{escape(label)}</text>\n'
            f'  <text x="470" y="{y}" text-anchor="end" font-family="{FONT}" font-size="14" '
            f'font-weight="600" fill="{PINK}">{value:,}</text>'.replace(",", ".")
        )
    return card(495, 75 + len(rows) * 30, "Estatísticas do GitHub", "\n".join(lines))


def main():
    info, repos = fetch_repos()
    downloads = sum(
        a["downloadCount"]
        for r in repos for rel in r["releases"]["nodes"] for a in rel["releaseAssets"]["nodes"]
    )
    stats = {
        "repos": info["all"]["totalCount"],  # públicos + privados
        "followers": info["followers"]["totalCount"],
        "commits": fetch_commits(info["createdAt"]),
        "downloads": downloads,
    }
    os.makedirs("assets", exist_ok=True)
    with open("assets/top-languages.svg", "w", encoding="utf-8") as f:
        f.write(languages_svg(repos))
    with open("assets/stats.svg", "w", encoding="utf-8") as f:
        f.write(stats_svg(stats))
    print(stats)


if __name__ == "__main__":
    main()
