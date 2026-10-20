"""Builds self-hosted GitHub stats cards (light + dark) for the profile README.

Runs in GitHub Actions with the built-in GITHUB_TOKEN, so the README never depends
on rate-limited public widget services.

    python profile_stats.py <username> <out_dir>        # live data
    python profile_stats.py <username> <out_dir> --demo # sample data, no network
"""
import datetime, json, os, sys, urllib.request
from collections import Counter
from html import escape

API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

# GitHub linguist colours for the languages most likely to appear; others fall back.
LANG_COLORS = {
    "Python": "#3572A5", "Jupyter Notebook": "#DA5B0B", "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a", "HTML": "#e34c26", "CSS": "#663399", "Java": "#b07219",
    "C++": "#f34b7d", "C": "#555555", "Shell": "#89e051", "Dockerfile": "#384d54",
    "R": "#198CE7", "Go": "#00ADD8", "Rust": "#dea584", "SCSS": "#c6538c",
    "Vue": "#41b883", "PHP": "#4F5D95", "Kotlin": "#A97BFF", "Swift": "#F05138",
}
FALLBACK = ["#3F74DD", "#63b3ed", "#8b949e", "#6E7888", "#a5b4fc", "#94a3b8"]
IGNORE_LANGS = {"Jupyter Notebook"}  # notebook output bytes swamp real code

THEMES = {
    "dark":  dict(bg="#0d1117", tile="#161b22", border="#30363d", text="#e6edf3", muted="#8b949e", track="#21262d"),
    "light": dict(bg="#ffffff", tile="#f6f8fa", border="#d0d7de", text="#1f2328", muted="#57606a", track="#eaeef2"),
}
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def get(path):
    req = urllib.request.Request(API + path, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-stats",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def collect(user):
    profile = get(f"/users/{user}")
    repos, page = [], 1
    while True:
        batch = get(f"/users/{user}/repos?per_page=100&type=owner&page={page}")
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    own = [r for r in repos if not r.get("fork")]
    langs = Counter()
    for r in own:
        try:
            for lang, size in get(r["languages_url"].replace(API, "")).items():
                if lang not in IGNORE_LANGS:
                    langs[lang] += size
        except Exception as exc:  # one bad repo shouldn't break the card
            print(f"warn: languages for {r['name']}: {exc}", file=sys.stderr)
    # Repos pushed to in the last 12 months — computed from the repo list itself,
    # because commit search and the contribution calendar aren't reliable with the
    # Actions token.
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)).isoformat()
    active = sum(1 for r in own if (r.get("pushed_at") or "") >= cutoff[:19])
    return {
        "repos": len(own),
        "stars": sum(r.get("stargazers_count", 0) for r in own),
        "followers": profile.get("followers", 0),
        "active": active,
        "languages": langs.most_common(),
    }


def demo():
    return {"repos": 27, "stars": 14, "followers": 31, "active": 18,
            "languages": [("Python", 520000), ("TypeScript", 210000), ("JavaScript", 150000),
                          ("HTML", 90000), ("CSS", 60000), ("Java", 30000), ("Shell", 8000)]}


def fmt(n):
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    return f"{n/1000:.1f}k" if n >= 10000 else f"{n:,}"


def render(data, t):
    W, H = 1000, 236
    tiles = [("Public repos", data["repos"]), ("Stars earned", data["stars"]),
             ("Followers", data["followers"]), ("Repos active · last 12 months", data["active"])]
    tw, th, gap = 104, 64, 12
    tile_svg = ""
    for i, (label, val) in enumerate(tiles):
        x = 32 + (i % 2) * (tw * 2 + gap)
        y = 62 + (i // 2) * (th + gap)
        w = tw * 2
        tile_svg += (f'<rect x="{x}" y="{y}" width="{w}" height="{th}" rx="10" fill="{t["tile"]}" stroke="{t["border"]}"/>'
                     f'<text x="{x+16}" y="{y+30}" class="v">{fmt(val)}</text>'
                     f'<text x="{x+16}" y="{y+50}" class="l">{escape(label)}</text>')

    langs = data["languages"]
    total = sum(s for _, s in langs) or 1
    top = langs[:6]
    other = total - sum(s for _, s in top)
    if other > 0 and len(langs) > 6:
        top.append(("Other", other))
    bx, by, bw = 512, 84, 456
    bar, legend, cx = "", "", bx
    for i, (lang, size) in enumerate(top):
        color = "#8b949e" if lang == "Other" else LANG_COLORS.get(lang, FALLBACK[i % len(FALLBACK)])
        w = bw * size / total
        bar += f'<rect x="{cx:.1f}" y="{by}" width="{max(w, 0.5):.1f}" height="12" fill="{color}"/>'
        cx += w
        col, row = i % 2, i // 2
        lx, ly = bx + col * 232, by + 42 + row * 26
        legend += (f'<circle cx="{lx+6}" cy="{ly-5}" r="5" fill="{color}"/>'
                   f'<text x="{lx+18}" y="{ly}" class="lg">{escape(lang)}</text>'
                   f'<text x="{lx+212}" y="{ly}" class="pc" text-anchor="end">{100*size/total:.1f}%</text>')
    if not langs:
        legend = f'<text x="{bx}" y="{by+42}" class="lg">No language data yet</text>'

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t">
<title id="t">GitHub stats: {data["repos"]} public repositories, {data["stars"]} stars, {data["followers"]} followers</title>
<style>
.h{{font:600 15px {FONT};fill:{t["text"]}}}
.v{{font:700 22px {FONT};fill:{t["text"]}}}
.l{{font:500 12px {FONT};fill:{t["muted"]}}}
.lg{{font:500 13px {FONT};fill:{t["text"]}}}
.pc{{font:500 13px {FONT};fill:{t["muted"]}}}
</style>
<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="16" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="2"/>
<text x="32" y="40" class="h">GitHub at a glance</text>
<text x="{bx}" y="40" class="h">Languages across my repositories</text>
<rect x="32" y="49" width="28" height="3" rx="1.5" fill="#3F74DD"/>
<rect x="{bx}" y="49" width="28" height="3" rx="1.5" fill="#3F74DD"/>
{tile_svg}
<clipPath id="bar"><rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6"/></clipPath>
<rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6" fill="{t["track"]}"/>
<g clip-path="url(#bar)">{bar}</g>
{legend}
</svg>
'''


def main():
    user, out = sys.argv[1], sys.argv[2]
    data = demo() if "--demo" in sys.argv else collect(user)
    os.makedirs(out, exist_ok=True)
    for name, theme in THEMES.items():
        with open(os.path.join(out, f"stats-{name}.svg"), "w") as f:
            f.write(render(data, theme))
    print(json.dumps({k: v for k, v in data.items() if k != "languages"}))


if __name__ == "__main__":
    main()
