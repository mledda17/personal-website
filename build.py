#!/usr/bin/env python3
"""Static site generator for marcoledda.it.

Only the Python standard library is needed (Python 3.11+).

    python3 build.py            # build the site into _site/
    python3 build.py serve      # build and preview at http://localhost:8000
    python3 build.py serve 8080 # ... on another port

Content lives in content/*.toml, the page layout in templates/base.html,
styles and scripts in assets/.  See README.md for the editing guide.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import math
import re
import shutil
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "templates"
OUT = ROOT / "_site"
STATIC = ["assets", "files", "CNAME"]

TODAY = dt.date.today()
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
NAV = [("Home", ""), ("Publications", "publications/"), ("Talks", "talks/"),
       ("Teaching", "teaching/"), ("News", "news/")]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def esc(value) -> str:
    return html.escape(str(value), quote=True)


def load(name: str) -> dict:
    with open(CONTENT / f"{name}.toml", "rb") as fh:
        return tomllib.load(fh)


def is_external(url: str) -> bool:
    return re.match(r"^(https?:|mailto:|#)", url) is not None


def href(url: str, root: str) -> str:
    return url if is_external(url) else root + url


def ext_attrs(url: str) -> str:
    return ' target="_blank" rel="noopener"' if url.startswith("http") else ""


def inline(text: str, root: str) -> str:
    """Escape text and apply the tiny markup used in the .toml files."""
    s = esc(text.strip())
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<em>\1</em>", s)
    s = re.sub(r"\[\[([A-Z]\d+)\]\]",
               lambda m: f'<a class="ref" href="{root}publications/#{m[1]}">[{m[1]}]</a>', s)

    def link(m):
        url = href(html.unescape(m[2]), root)
        return f'<a href="{esc(url)}"{ext_attrs(url)}>{m[1]}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)


def paragraphs(text: str, root: str) -> str:
    return "\n".join(f"<p>{inline(p, root)}</p>"
                     for p in re.split(r"\n\s*\n", text.strip()) if p.strip())


def parse_date(value) -> tuple[dt.date, str, str]:
    """'2026-08-23' | '2026-08' | '2026' -> (start date, label, iso string)."""
    parts = [int(x) for x in str(value).split("-")]
    y, m, d = (parts + [None, None])[:3]
    if d:
        label = f"{d} {MONTHS[m - 1]} {y}"
    elif m:
        label = f"{MONTHS[m - 1]} {y}"
    else:
        label = str(y)
    return dt.date(y, m or 1, d or 1), label, str(value)


def sort_key_date(value) -> str:
    parts = str(value).split("-")
    return "-".join(p.zfill(2) for p in parts) + "-00" * (3 - len(parts))


def label_num(pub: dict) -> int:
    return int(re.sub(r"\D", "", pub["id"]) or 0)


# --------------------------------------------------------------------------
# Icons (simple stroke icons, drawn for this site)
# --------------------------------------------------------------------------

ICONS = {
    "pdf": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    "slides": '<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M12 16v4M8 20h8M7.5 12l3-3 2.5 2 3.5-4"/>',
    "code": '<path d="M8.5 7.5 4 12l4.5 4.5M15.5 7.5 20 12l-4.5 4.5M13.5 5l-3 14"/>',
    "bib": '<path d="M8 4c-1.8 0-2.8 1-2.8 2.8v2.4c0 1.4-.7 2.3-2 2.8 1.3.5 2 1.4 2 2.8v2.4C5.2 19 6.2 20 8 20M16 4c1.8 0 2.8 1 2.8 2.8v2.4c0 1.4.7 2.3 2 2.8-1.3.5-2 1.4-2 2.8v2.4c0 1.8-1 2.8-2.8 2.8"/>',
    "abstract": '<path d="M4 6h16M4 10h16M4 14h16M4 18h9"/>',
    "doi": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.8 6.5 8.2 6.3 8.2-6.3"/>',
    "scholar": '<path d="m2 9.5 10-5.5 10 5.5-10 5.5z"/><path d="M6 11.7V16c2.4 2.4 9.6 2.4 12 0v-4.3M22 9.5V15"/>',
    "orcid": '<circle cx="12" cy="12" r="9"/><path d="M9 10.5V16M9 7.8v.1M12.2 10.5V16h1.6a2.75 2.75 0 0 0 0-5.5z"/>',
    "github": '<path d="M9 19c-4 1.3-4-2-6-2.5M15 21v-3.4a3 3 0 0 0-.8-2.3c2.8-.3 5.8-1.4 5.8-6.2a4.8 4.8 0 0 0-1.3-3.3 4.5 4.5 0 0 0-.1-3.3s-1-.3-3.4 1.3a11.6 11.6 0 0 0-6.2 0C6.6 2.2 5.6 2.5 5.6 2.5a4.5 4.5 0 0 0-.1 3.3 4.8 4.8 0 0 0-1.3 3.3c0 4.8 3 5.9 5.8 6.2a3 3 0 0 0-.8 2.3V21"/>',
    "linkedin": '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M8 10.5V17M8 7.4v.1M12 17v-6.5M12 13.6c0-1.8 1-3.1 2.5-3.1S17 11.4 17 13v4"/>',
    "scopus": '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    "institution": '<path d="M3 21h18M5 21V10.5M19 21V10.5M9.5 21v-6h5v6M2.5 10 12 4.5l9.5 5.5z"/>',
    "cv": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><circle cx="12" cy="12.5" r="2"/><path d="M8.5 18c.6-1.7 2-2.6 3.5-2.6s2.9.9 3.5 2.6"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "pin": '<path d="M12 21s-6.5-6-6.5-11a6.5 6.5 0 0 1 13 0c0 5-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
    "copy": '<rect x="8.5" y="8.5" width="11.5" height="11.5" rx="2"/><path d="M15.5 8.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.5a2 2 0 0 0 2 2h2.5"/>',
    "download": '<path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "book": '<path d="M12 6.5C10 5 7 4.5 3.5 5v13c3.5-.5 6.5 0 8.5 1.5 2-1.5 5-2 8.5-1.5V5C17 4.5 14 5 12 6.5zM12 6.5v13"/>',
}


def icon(name: str) -> str:
    return f'<svg class="i" viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'


# --------------------------------------------------------------------------
# Background schematics.  Everything is drawn from actual math so that the
# curves are the real step response, Bode plot, phase portrait, ...
# --------------------------------------------------------------------------

def pts(points) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def marker_defs(uid: str) -> str:
    return (f'<defs><marker id="{uid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0 1 9 5 0 9z" class="ah"/></marker></defs>')


def art_loop(uid: str = "loop") -> str:
    """Closed loop with a learned correction: r -> K -> (inverse + NN) -> plant, delta on y."""
    a = f'marker-end="url(#{uid})"'
    nn_layers = [(336, [164, 180, 196]), (364, [158, 172, 186, 200]), (392, [172, 188])]
    edges, nodes = [], []
    for (x1, ys1), (x2, ys2) in zip(nn_layers, nn_layers[1:]):
        for y1 in ys1:
            for y2 in ys2:
                edges.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>')
    for x, ys in nn_layers:
        for y in ys:
            nodes.append(f'<circle cx="{x}" cy="{y}" r="3.4" class="node"/>')

    def junction(cx, cy):
        d = 9.9
        return (f'<circle cx="{cx}" cy="{cy}" r="14" class="node"/>'
                f'<path d="M{cx - d} {cy - d}L{cx + d} {cy + d}M{cx + d} {cy - d}L{cx - d} {cy + d}"/>')

    return f'''<svg class="art art-loop" viewBox="0 0 760 320" aria-hidden="true" focusable="false">
{marker_defs(uid)}
<g class="ink">
  <path d="M22 120H82" {a}/>{junction(98, 120)}
  <path d="M112 120H168" {a}/>
  <rect x="170" y="96" width="64" height="48" rx="6"/>
  <path d="M234 120H280M280 120V64H314" {a}/>
  <path d="M280 120V180H314" {a}/>
  <circle cx="280" cy="120" r="3" class="dot"/>
  <rect x="316" y="42" width="96" height="44" rx="6"/>
  <rect x="316" y="148" width="96" height="64" rx="6" class="dashed"/>
  <g class="thin">{"".join(edges)}</g>{"".join(nodes)}
  <path d="M412 64H470V104" {a}/>
  <path d="M412 180H470V136" {a}/>{junction(470, 120)}
  <path d="M484 120H538" {a}/>
  <rect x="540" y="96" width="76" height="48" rx="6"/>
  <path d="M616 120H740" {a}/>
  <circle cx="676" cy="120" r="3" class="dot"/>
  <path d="M676 120V260" {a}/>{junction(676, 276)}
  <path d="M744 276H692" {a}/>
  <path d="M662 276H98V136" {a}/>
  <path d="M578 144V240H364V214" class="dashed" {a}/>
  <path class="tilde" d="M348.5 55q3.2-4 6.4 0t6.4 0"/>
</g>
<g class="flow"><path d="M22 120H168"/><path d="M234 120H280V64H314"/><path d="M412 64H470V120H538"/><path d="M616 120H740"/><path d="M676 120V276H98V120"/></g>
<g class="lbl">
  <text x="34" y="108">r</text><text x="202" y="127" text-anchor="middle">K</text>
  <text x="252" y="110">v</text><text x="502" y="110">u</text><text x="716" y="108">y</text>
  <text x="726" y="264">δ</text><text x="590" y="200">x</text>
  <text x="347" y="74">Σ<tspan dy="-9" font-size="12">−1</tspan></text>
  <text x="578" y="127" text-anchor="middle">Σ</text>
  <text x="66" y="110" class="sm">+</text><text x="104" y="156" class="sm">−</text>
  <text x="446" y="102" class="sm">+</text><text x="446" y="150" class="sm">+</text>
  <text x="318" y="229" class="sm mono">NN</text>
</g>
</svg>'''


def art_nn(uid: str = "nn") -> str:
    """Fully connected network 3-5-5-2 with one highlighted activation path."""
    layers = [3, 5, 5, 2]
    xs = [40, 100, 160, 220]
    H = 250

    def ys(n):
        gap = 40
        top = (H - gap * (n - 1)) / 2
        return [top + i * gap for i in range(n)]

    out = []
    hot = {(0, 1, 2), (1, 2, 1), (2, 1, 0)}  # (layer, i, j) edges on the highlighted path
    for li in range(len(layers) - 1):
        for i, y1 in enumerate(ys(layers[li])):
            for j, y2 in enumerate(ys(layers[li + 1])):
                cls = "hot" if (li, i, j) in hot else "thin"
                out.append(f'<line x1="{xs[li]}" y1="{y1:.1f}" x2="{xs[li + 1]}" y2="{y2:.1f}" class="{cls}"/>')
    for li, n in enumerate(layers):
        for y in ys(n):
            out.append(f'<circle cx="{xs[li]}" cy="{y:.1f}" r="6" class="node"/>')
    arrows = "".join(f'<path d="M4 {y:.1f}H30" marker-end="url(#{uid})"/>' for y in ys(3))
    arrows += "".join(f'<path d="M230 {y:.1f}H256" marker-end="url(#{uid})"/>' for y in ys(2))
    return f'''<svg class="art art-nn" viewBox="0 0 270 250" aria-hidden="true" focusable="false">
{marker_defs(uid)}<g class="ink">{"".join(out)}{arrows}</g>
<g class="lbl"><text x="160" y="244" text-anchor="middle" class="sm mono">ReLU</text></g></svg>'''


def art_phase(uid: str = "phase") -> str:
    """Phase portrait of a stable focus with a Lyapunov sublevel set."""
    cx, cy = 130, 120
    curves = []
    for phase, r0 in [(0.0, 104), (math.pi, 92), (math.pi / 2, 70)]:
        p = []
        t = 0.0
        while t < 14:
            r = r0 * math.exp(-0.17 * t)
            p.append((cx + r * math.cos(t + phase), cy - 0.72 * r * math.sin(t + phase)))
            t += 0.06
        curves.append(f'<polyline points="{pts(p)}"/>')
    # small chevrons along the first spiral to show the direction of motion
    chev = []
    for t in (0.9, 3.9, 6.9):
        r = 104 * math.exp(-0.17 * t)
        x, y = cx + r * math.cos(t), cy - 0.72 * r * math.sin(t)
        dx = -r * math.sin(t) - 0.17 * r * math.cos(t)
        dy = -0.72 * (r * math.cos(t) - 0.17 * r * math.sin(t))
        ang = math.degrees(math.atan2(dy, dx))
        chev.append(f'<path d="M-5 -4 1 0 -5 4" transform="translate({x:.1f} {y:.1f}) rotate({ang:.1f})"/>')
    return f'''<svg class="art art-phase" viewBox="0 0 260 240" aria-hidden="true" focusable="false">
{marker_defs(uid)}<g class="ink">
<path d="M10 {cy}H250" marker-end="url(#{uid})" class="thin"/><path d="M{cx} 232V10" marker-end="url(#{uid})" class="thin"/>
<ellipse cx="{cx}" cy="{cy}" rx="78" ry="46" transform="rotate(-18 {cx} {cy})" class="dashed"/>
{"".join(curves)}{"".join(chev)}<circle cx="{cx}" cy="{cy}" r="3" class="dot"/></g>
<g class="lbl"><text x="236" y="{cy - 8}" class="sm">x₁</text><text x="{cx + 8}" y="20" class="sm">x₂</text>
<text x="196" y="66" class="sm">V(x) ≤ c</text></g></svg>'''


def art_step(uid: str = "step") -> str:
    """Underdamped second-order step response with its samples (sampled-data)."""
    zeta, wn, T = 0.28, 1.0, 22.0
    wd = wn * math.sqrt(1 - zeta ** 2)

    def y(t):
        return 1 - math.exp(-zeta * wn * t) * (math.cos(wd * t) + zeta / math.sqrt(1 - zeta ** 2) * math.sin(wd * t))

    X0, X1, Y0, A = 60, 1180, 122, 62

    def mx(t):
        return X0 + t / T * (X1 - X0)

    def my(v):
        return Y0 - v * A

    curve = [(mx(t / 10), my(y(t / 10))) for t in range(0, int(T * 10) + 1)]
    samples = "".join(f'<line x1="{mx(k):.1f}" y1="{Y0}" x2="{mx(k):.1f}" y2="{my(y(k)):.1f}" class="thin"/>'
                      f'<circle cx="{mx(k):.1f}" cy="{my(y(k)):.1f}" r="3" class="node"/>' for k in range(1, int(T)))
    return f'''<svg class="art art-step" viewBox="0 0 1240 140" preserveAspectRatio="xMidYMax meet" aria-hidden="true" focusable="false">
{marker_defs(uid)}<g class="ink">
<path d="M30 {Y0}H1210" marker-end="url(#{uid})" class="thin"/>
<path d="M{X0} {my(1):.1f}H{X1}" class="dashed"/>
{samples}<polyline points="{pts(curve)}"/></g>
<g class="lbl"><text x="1194" y="{Y0 - 8}" class="sm">t</text><text x="{X1 - 6}" y="{my(1) - 8:.1f}" class="sm" text-anchor="end">y(t) → 1</text></g></svg>'''


def art_bode(uid: str = "bode") -> str:
    """Bode magnitude and phase of a lightly damped second-order system."""
    zeta = 0.15
    x0, x1 = 30, 310
    mag, ph = [], []
    n = 220
    for i in range(n + 1):
        lw = -2 + 4 * i / n
        w = 10 ** lw
        re_, im_ = 1 - w * w, 2 * zeta * w
        db = -10 * math.log10(re_ * re_ + im_ * im_)
        phase = -math.degrees(math.atan2(im_, re_))
        x = x0 + (lw + 2) / 4 * (x1 - x0)
        mag.append((x, 34 - db * 0.95))
        ph.append((x, 150 + (-phase) * 0.42))
    grid = "".join(f'<path d="M{x0 + k * (x1 - x0) / 4:.1f} 12V112M{x0 + k * (x1 - x0) / 4:.1f} 140V230" class="thin"/>'
                   for k in range(5))
    asym = f'<path d="M{x0} 34H{(x0 + x1) / 2:.1f}L{x1} {34 + 76:.1f}" class="dashed"/>'
    return f'''<svg class="art art-bode" viewBox="0 0 340 240" aria-hidden="true" focusable="false">
{marker_defs(uid)}<g class="ink">{grid}
<path d="M{x0} 112H{x1 + 14}" marker-end="url(#{uid})" class="thin"/><path d="M{x0} 230H{x1 + 14}" marker-end="url(#{uid})" class="thin"/>
{asym}<polyline points="{pts(mag)}"/><polyline points="{pts(ph)}"/></g>
<g class="lbl"><text x="{x0 + 4}" y="22" class="sm">|G(jω)|</text><text x="{x0 + 4}" y="134" class="sm">∠G(jω)</text>
<text x="{x1 + 4}" y="128" class="sm">ω</text></g></svg>'''


def art_nyquist(uid: str = "nyq") -> str:
    """Nyquist plot of G(s) = 2 / ((s+1)(0.5s+1)(0.2s+1)) with the critical point."""
    def G(w):
        s = complex(0, w)
        return 2 / ((s + 1) * (0.5 * s + 1) * (0.2 * s + 1))

    ox, oy, k = 120, 110, 62
    upper, lower = [], []
    w = 0.0
    while w < 60:
        g = G(w)
        upper.append((ox + g.real * k, oy - g.imag * k))
        lower.append((ox + g.real * k, oy + g.imag * k))
        w += 0.02 if w < 6 else 0.4
    return f'''<svg class="art art-nyq" viewBox="0 0 300 220" aria-hidden="true" focusable="false">
{marker_defs(uid)}<g class="ink">
<path d="M10 {oy}H290" marker-end="url(#{uid})" class="thin"/><path d="M{ox} 210V10" marker-end="url(#{uid})" class="thin"/>
<polyline points="{pts(upper)}"/><polyline points="{pts(lower)}" class="dashed"/>
<path d="M{ox - k - 5} {oy - 5}l10 10m0-10-10 10"/></g>
<g class="lbl"><text x="{ox - k - 12}" y="{oy + 22}" class="sm">−1</text><text x="276" y="{oy - 8}" class="sm">Re</text>
<text x="{ox + 8}" y="20" class="sm">Im</text></g></svg>'''


def art_cpwa(uid: str = "cpwa") -> str:
    """Polyhedral partition induced by three ReLU neurons, with a ReLU inset."""
    lines = [((0, 70), (240, 178)), ((52, 230), (178, 0)), ((0, 196), (240, 46))]

    def inter(l1, l2):
        (x1, y1), (x2, y2) = l1
        (x3, y3), (x4, y4) = l2
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        return x1 + t * (x2 - x1), y1 + t * (y2 - y1)

    tri = [inter(lines[0], lines[1]), inter(lines[1], lines[2]), inter(lines[2], lines[0])]
    segs = "".join(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}"/>' for a, b in lines)
    return f'''<svg class="art art-cpwa" viewBox="0 0 330 240" aria-hidden="true" focusable="false">
<defs><clipPath id="{uid}-c"><rect x="0" y="0" width="240" height="230" rx="8"/></clipPath>
<pattern id="{uid}-h" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" class="hatch"/></pattern></defs>
<g class="ink"><rect x="0.5" y="0.5" width="239" height="229" rx="8" class="thin"/>
<g clip-path="url(#{uid}-c)">{segs}<polygon points="{pts(tri)}" fill="url(#{uid}-h)" class="nostroke"/></g>
<path d="M262 200H326M270 200H292L322 150" class="thin"/><path d="M270 200H292L322 150"/></g>
<g class="lbl"><text x="22" y="32" class="sm">Ω₁</text><text x="196" y="38" class="sm">Ω₂</text><text x="22" y="222" class="sm">Ω₃</text>
<text x="200" y="212" class="sm">Ω₄</text><text x="270" y="140" class="sm mono">ReLU</text></g></svg>'''


def art_stems(uid: str = "stems") -> str:
    """Discrete-time signal x[k] (damped cosine) as a stem plot."""
    X0, Y0 = 20, 110
    out = []
    for k in range(17):
        v = math.exp(-0.16 * k) * math.cos(0.75 * k)
        x, y = X0 + 18 * k, Y0 - v * 78
        out.append(f'<line x1="{x}" y1="{Y0}" x2="{x}" y2="{y:.1f}"/><circle cx="{x}" cy="{y:.1f}" r="4.2" class="node"/>')
    return f'''<svg class="art art-stems" viewBox="0 0 330 200" aria-hidden="true" focusable="false">
{marker_defs(uid)}<g class="ink"><path d="M8 {Y0}H322" marker-end="url(#{uid})" class="thin"/>{"".join(out)}</g>
<g class="lbl"><text x="306" y="{Y0 + 22}" class="sm">k</text><text x="20" y="22" class="sm">x[k]</text></g></svg>'''


# Mini illustrations for the research-interest cards (48x48, current colour).
MINI = {
    "certify": '<path d="M5 41h38M5 41V6"/><path d="M5 33c5-1 7-12 12-12s6 9 11 9 6-17 10-17" class="m-curve"/><path d="M5 13h38" class="m-dash"/><circle cx="38" cy="13" r="2.6" class="m-dot"/>',
    "adversarial": '<path d="M4 24c5-12 9-12 14 0s9 12 14 0 7-9 12-8"/><path d="M4 27c5-12 9-6 14 3s9 14 14-6 7-5 12-8" class="m-dash"/><path d="M27 9v9" class="m-arrow"/><text x="29" y="11" class="m-txt">δ</text>',
    "sysid": '<path d="M2 24h9"/><rect x="11" y="12" width="26" height="24" rx="4"/><circle cx="19" cy="20" r="2.2" class="m-dot"/><circle cx="19" cy="28" r="2.2" class="m-dot"/><circle cx="29" cy="24" r="2.2" class="m-dot"/><path d="M21 20l6 3.4M21 28l6-3.4" class="m-thin"/><path d="M37 24h9"/>',
}


def mini(name: str) -> str:
    return f'<svg class="mini" viewBox="0 0 48 48" aria-hidden="true">{MINI[name]}</svg>'


# --------------------------------------------------------------------------
# Rendering of shared components
# --------------------------------------------------------------------------

class Site:
    def __init__(self):
        self.cfg = load("site")
        self.pubs_cfg = load("publications")
        self.news = load("news").get("news", [])
        self.talks = load("talks").get("talk", [])
        self.teaching = load("teaching")
        self.people = self.cfg.get("people", {})
        self.pubs = self.pubs_cfg.get("publication", [])
        self.categories = self.pubs_cfg.get("category", [])
        self.by_id = {p["id"]: p for p in self.pubs}
        self.slides_for = {t["paper"]: t for t in self.talks if t.get("paper") and t.get("slug")}
        self.template = (TEMPLATES / "base.html").read_text("utf-8")
        digest = hashlib.md5()
        for f in ("assets/css/style.css", "assets/js/site.js"):
            digest.update((ROOT / f).read_bytes())
        self.version = digest.hexdigest()[:8]
        self.pages: list[str] = []
        self.validate()

    # ---- checks -------------------------------------------------------
    def validate(self):
        keys = {c["key"] for c in self.categories}
        seen = set()
        for p in self.pubs:
            for field in ("id", "category", "title", "authors", "venue", "year"):
                if field not in p:
                    sys.exit(f"publications.toml: '{p.get('id', '?')}' is missing '{field}'")
            if p["id"] in seen:
                sys.exit(f"publications.toml: duplicate id {p['id']}")
            seen.add(p["id"])
            if p["category"] not in keys:
                sys.exit(f"publications.toml: {p['id']} has unknown category {p['category']}")
            for f in ("manuscript", "logo", "thumbnail"):
                if p.get(f) and not (ROOT / p[f]).exists():
                    sys.exit(f"publications.toml: {p['id']}: file not found: {p[f]}")
        for t in self.talks:
            if t.get("slides") and not (ROOT / t["slides"]).exists():
                sys.exit(f"talks.toml: file not found: {t['slides']}")
            if t.get("paper") and t["paper"] not in self.by_id:
                sys.exit(f"talks.toml: unknown paper {t['paper']}")
        refs = re.findall(r"\[\[([A-Z]\d+)\]\]", json.dumps([self.news, self.pubs_cfg, self.cfg]))
        for r in refs:
            if r not in self.by_id:
                sys.exit(f"Reference [[{r}]] does not match any publication id")

    # ---- generic bits ------------------------------------------------
    def authors(self, names, root="") -> str:
        out = []
        for n in names:
            url = self.people.get(n)
            if url == "me":
                out.append(f'<span class="me">{esc(n)}</span>')
            elif url:
                out.append(f'<a class="coauthor" href="{esc(url)}" target="_blank" rel="noopener">{esc(n)}</a>')
            else:
                out.append(esc(n))
        return ", ".join(out)

    def nav(self, active: str, root: str) -> str:
        items = []
        for label, path in NAV:
            cur = ' aria-current="page"' if path == active else ""
            items.append(f'          <li><a href="{root}{path}"{cur}>{label}</a></li>')
        return "\n".join(items)

    @staticmethod
    def status_tag(status: str | None) -> str:
        if not status:
            return ""
        cls = "tag-review" if "review" in status else "tag-ok"
        return f'<span class="tag {cls}">{esc(status.capitalize())}</span>'

    def venue_line(self, p: dict) -> str:
        venue = esc(p["venue"])
        if p.get("status") == "under review":
            venue = f"Submitted to {venue}"
        bits = [venue]
        if p.get("place"):
            bits.append(esc(p["place"]))
        bits.append(str(p["year"]))
        if p.get("pages"):
            bits.append(f"pp. {esc(p['pages'])}")
        return ", ".join(bits)

    def pub_actions(self, p: dict, root: str, prefix: str = "") -> str:
        uid = f"{prefix}{p['id']}"
        acts, panels = [], []
        if p.get("bibtex"):
            acts.append(f'<button type="button" class="act" data-panel aria-expanded="false" '
                        f'aria-controls="{uid}-bib">{icon("bib")}BibTeX</button>')
            panels.append(f'<div class="panel panel-bib" id="{uid}-bib" hidden>'
                          f'<pre><code>{esc(p["bibtex"].strip())}</code></pre>'
                          f'<button type="button" class="copy-bib">{icon("copy")}<span>Copy</span></button></div>')
        if p.get("abstract"):
            acts.append(f'<button type="button" class="act" data-panel aria-expanded="false" '
                        f'aria-controls="{uid}-abs">{icon("abstract")}Abstract</button>')
            panels.append(f'<div class="panel panel-abs" id="{uid}-abs" hidden>{paragraphs(p["abstract"], root)}</div>')
        if p.get("reader"):
            acts.append(f'<a class="act" href="{root}{esc(p["reader"])}/">{icon("book")}Read online</a>')
        if p.get("manuscript"):
            acts.append(f'<a class="act" href="{root}{esc(p["manuscript"])}" target="_blank" rel="noopener">'
                        f'{icon("pdf")}Manuscript</a>')
        talk = self.slides_for.get(p["id"])
        if talk:
            acts.append(f'<a class="act" href="{root}slides/{esc(talk["slug"])}/">{icon("slides")}Slides</a>')
        if p.get("code"):
            acts.append(f'<a class="act" href="{esc(p["code"])}" target="_blank" rel="noopener">{icon("code")}Code</a>')
        if p.get("doi"):
            acts.append(f'<a class="act" href="https://doi.org/{esc(p["doi"])}" target="_blank" rel="noopener">'
                        f'{icon("doi")}DOI</a>')
        return f'<div class="pub-actions">{"".join(acts)}</div>{"".join(panels)}'

    def venue_tile(self, p: dict, root: str) -> str:
        if p.get("logo"):
            inner = f'<img src="{root}{esc(p["logo"])}" alt="{esc(p.get("short") or p["venue"])}" loading="lazy">'
        elif p.get("logo_text"):
            lines = p["logo_text"].split("|")
            inner = '<span class="tile-text">' + "".join(f"<span>{esc(x)}</span>" for x in lines) + "</span>"
        else:
            inner = f'<span class="tile-text"><span>{esc(p.get("short") or p["venue"])}</span></span>'
        note = f'<span class="tile-note">{esc(p["logo_note"])}</span>' if p.get("logo_note") else ""
        cls = "venue-tile" + (" is-pending" if p.get("logo_note") else "") + (" is-fill" if p.get("logo_fill") else "")
        if p.get("logo_url"):
            return (f'<a class="{cls}" href="{esc(p["logo_url"])}" target="_blank" rel="noopener" '
                    f'aria-label="{esc(p.get("short") or p["venue"])} website">{inner}{note}</a>')
        return f'<span class="{cls}">{inner}{note}</span>'

    def pub_entry(self, p: dict, root: str) -> str:
        title = esc(p["title"])
        link = f"https://doi.org/{p['doi']}" if p.get("doi") else p.get("url")
        if link:
            title = f'<a href="{esc(link)}" target="_blank" rel="noopener">{title}</a>'
        return f'''      <article class="pub" id="{esc(p["id"])}" data-category="{esc(p["category"])}" data-year="{p["year"]}">
        <div class="pub-label">[{esc(p["id"])}]</div>
        <div class="pub-main">
          <h3 class="pub-title">{title}</h3>
          <p class="pub-authors">{self.authors(p["authors"], root)}</p>
          <p class="pub-venue">{self.venue_line(p)} {self.status_tag(p.get("status"))}</p>
          {f'<p class="pub-note-line">{inline(p["note"], root)}</p>' if p.get("note") else ""}
          {self.pub_actions(p, root)}
        </div>
        {self.venue_tile(p, root)}
      </article>'''

    def paper_card(self, p: dict, root: str) -> str:
        thumb_target = f"{root}publications/#{esc(p['id'])}"
        if p.get("thumbnail"):
            thumb = (f'<a class="paper-thumb" href="{thumb_target}" tabindex="-1" aria-hidden="true">'
                     f'<img src="{root}{esc(p["thumbnail"])}" alt="" width="309" height="400" loading="lazy" decoding="async"></a>')
        else:
            thumb = f'<span class="paper-thumb paper-thumb-empty" aria-hidden="true"><span>{esc(p["id"])}</span></span>'
        short = p.get("short") or p["venue"]
        year = "" if str(p["year"]) in short else f'<span class="paper-year">{p["year"]}</span>'
        return f'''        <article class="paper-card">
          {thumb}
          <div class="paper-body">
            <p class="paper-meta"><span class="paper-venue">{esc(short)}</span>{year}{self.status_tag(p.get("status"))}</p>
            <h3 class="paper-title"><a href="{root}publications/#{esc(p["id"])}">{esc(p["title"])}</a></h3>
            <p class="pub-authors">{self.authors(p["authors"], root)}</p>
            <p class="paper-venue-line">{self.venue_line(p)}</p>
          </div>
        </article>'''

    def news_list(self, items, root: str, cls: str = "") -> str:
        rows = []
        for n in items:
            start, label, iso = parse_date(n["date"])
            upcoming = start > TODAY
            tag = '<span class="tag tag-ok">Upcoming</span> ' if upcoming else ""
            rows.append(f'          <li class="stem{" is-upcoming" if upcoming else ""}"><time datetime="{esc(iso)}">{label}</time>'
                        f'<p>{tag}{inline(n["text"], root)}</p></li>')
        return f'<ol class="stem-list {cls}">\n' + "\n".join(rows) + "\n        </ol>"

    def sorted_news(self):
        return sorted(self.news, key=lambda n: sort_key_date(n["date"]), reverse=True)

    def section_head(self, index: str, title: str, more: tuple[str, str] | None = None, hid: str = "") -> str:
        link = ""
        if more:
            link = f'<a class="more" href="{more[1]}">{more[0]} {icon("arrow")}</a>'
        return (f'<div class="sec-head"><span class="sec-index">{index}</span>'
                f'<h2 id="{hid}">{title}</h2>{link}</div>')

    def page_head(self, eyebrow: str, title: str, lede: str, art: str) -> str:
        return f'''    <section class="page-head">
      <div class="container page-head-inner">
        <div class="page-head-text">
          <p class="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p class="lede">{lede}</p>
        </div>
        <div class="page-head-art" aria-hidden="true">{art}</div>
      </div>
    </section>'''

    # ---- page assembly -----------------------------------------------
    def write(self, path: str, *, title: str, content: str, active: str | None = None,
              description: str | None = None, body_class: str = "", head_extra: str = "",
              og_type: str = "website", absolute_root: bool = False):
        depth = path.count("/")
        root = "/" if absolute_root else "../" * depth
        url_path = re.sub(r"index\.html$", "", path)
        canonical = f'{self.cfg["base_url"]}/{url_path}'
        values = {
            "title": esc(title),
            "description": esc(description or self.cfg["description"]),
            "canonical": esc(canonical),
            "og_type": og_type,
            "og_image": esc(f'{self.cfg["base_url"]}/{self.cfg["profile"]["photo"]}'),
            "root": root,
            "version": self.version,
            "head_extra": head_extra,
            "body_class": body_class,
            "nav": self.nav(active if active is not None else "-", root),
            "content": content.replace("{{root}}", root),
            "footer_art": f'    <div class="footer-art" aria-hidden="true">{art_step("f-step")}</div>',
            "footer_role": esc(f'{self.cfg["profile"]["role"]}, {self.cfg["profile"]["university"]}'),
            "email": esc(self.cfg["profile"]["email"]),
            "updated": f"{dt.date.today():%B %Y}",
            "year": str(TODAY.year),
        }

        def sub(m):
            key = m[1]
            if key not in values:
                sys.exit(f"templates/base.html: unknown placeholder {{{{ {key} }}}}")
            return values[key]

        page = re.sub(r"\{\{\s*(\w+)\s*\}\}", sub, self.template)
        target = OUT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, "utf-8")
        if not absolute_root and "noindex" not in head_extra:
            self.pages.append(url_path)

    # ---- pages ---------------------------------------------------------
    def build_home(self):
        cfg, prof = self.cfg, self.cfg["profile"]
        root = ""
        link_defs = [
            ("email", "mail", "Email", f'mailto:{prof["email"]}'),
            ("github", "github", "GitHub", cfg["links"].get("github")),
            ("scholar", "scholar", "Scholar", cfg["links"].get("scholar")),
            ("cv", "download", "Download CV", cfg["links"].get("cv")),
            ("orcid", "orcid", "ORCID", cfg["links"].get("orcid")),
            ("linkedin", "linkedin", "LinkedIn", cfg["links"].get("linkedin")),
            ("scopus", "scopus", "Scopus", cfg["links"].get("scopus")),
            ("institutional", "institution", "UniCa profile", cfg["links"].get("institutional")),
        ]
        links = []
        for key, ic, label, url in link_defs:
            if not url:
                continue
            target = href(url, root)
            cls = "plink plink-primary" if key == "email" else "plink"
            extra = " download" if key == "cv" else ext_attrs(target)
            links.append(f'<a class="{cls}" href="{esc(target)}"{extra}>{icon(ic)}<span>{label}</span></a>')

        interests = []
        for i, it in enumerate(cfg.get("interest", []), 1):
            interests.append(f'''          <article class="interest">
            <div class="interest-top"><span class="interest-icon">{mini(it["icon"])}</span><span class="interest-num">{i:02d}</span></div>
            <h3>{esc(it["title"])}</h3>
            <p>{inline(it["text"], root)}</p>
          </article>''')

        news = self.sorted_news()[: cfg.get("news_on_home", 5)]
        selected = [p for p in self.pubs if p.get("selected")]
        cards = "\n".join(self.paper_card(p, root) for p in selected)

        person = {
            "@context": "https://schema.org", "@type": "Person", "name": prof["name"],
            "jobTitle": prof["role"], "email": f'mailto:{prof["email"]}',
            "affiliation": {"@type": "CollegeOrUniversity", "name": prof["university"]},
            "url": cfg["base_url"] + "/", "image": f'{cfg["base_url"]}/{prof["photo"]}',
            "sameAs": [u for k, u in cfg["links"].items() if u and u.startswith("http")],
        }
        head_extra = f'  <script type="application/ld+json">{json.dumps(person, ensure_ascii=False)}</script>'

        content = f'''    <section class="hero">
      <div class="hero-grid" aria-hidden="true"></div>
      <div class="container hero-inner">
        <div class="hero-text">
          <p class="eyebrow">{esc(prof["university"])} &middot; DIEE</p>
          <h1>{esc(prof["name"])}</h1>
          <p class="hero-role">{esc(prof["role"])}</p>
          <p class="hero-aff"><a href="{esc(prof["department_url"])}" target="_blank" rel="noopener">{esc(prof["department"])}</a><br>{esc(prof["university"])}, Italy</p>
          <div class="hero-bio">
{paragraphs(prof["bio"], root)}
          </div>
          <div class="profile-links">{"".join(links)}</div>
        </div>
        <figure class="hero-photo">
          <div class="photo-frame"><img src="{esc(prof["photo"])}" alt="Portrait of {esc(prof["name"])}" width="646" height="800"></div>
          <div class="hero-art" aria-hidden="true">{art_loop("h-loop")}</div>
        </figure>
      </div>
    </section>

    <section class="section" aria-labelledby="interests-h">
      <div class="container">
        {self.section_head("01", "Research interests", hid="interests-h")}
        <div class="interest-grid">
{chr(10).join(interests)}
        </div>
      </div>
    </section>

    <section class="section section-news" aria-labelledby="news-h">
      <div class="side-art side-left" aria-hidden="true">{art_nn("s-nn")}</div>
      <div class="container">
        {self.section_head("02", "News", ("All news", "news/"), hid="news-h")}
        {self.news_list(news, root)}
      </div>
    </section>

    <section class="section section-papers" aria-labelledby="papers-h">
      <div class="side-art side-right" aria-hidden="true">{art_phase("s-phase")}</div>
      <div class="container">
        {self.section_head("03", "Selected publications", ("All publications", "publications/"), hid="papers-h")}
        <div class="paper-grid">
{cards}
        </div>
      </div>
    </section>'''
        self.write("index.html", title=f'{prof["name"]} · {prof["role"]}', content=content,
                   active="", head_extra=head_extra, body_class="home", og_type="profile")

    def filter_bar(self, chips, scholar_link: str) -> str:
        """Type chips (arXiv / journal / conference / thesis) and a Year menu."""
        years = sorted({p["year"] for p in self.pubs}, reverse=True)
        options = "".join(f'<option value="{y}">{y}</option>' for y in years)
        all_chip = (f'<a class="chip chip-all" href="#" data-type="" hidden>All'
                    f'<span class="chip-count">{len(self.pubs)}</span></a>')
        return f'''    <section class="container pub-filters" aria-label="Filter publications">
      <div class="filter-row">
        <nav class="pub-jump" aria-label="Publication type">{all_chip}{"".join(chips)}</nav>
        <div class="filter-controls">
          <label class="filter-field"><span>Year</span><select data-filter="year"><option value="">All</option>{options}</select></label>
          <button type="button" class="filter-reset" hidden>Reset</button>
        </div>
      </div>
      <div class="filter-foot"><p class="filter-status" aria-live="polite"></p>{scholar_link}</div>
    </section>'''

    def build_publications(self):
        root = "../"
        sections, chips = [], []
        total = 0
        for cat in self.categories:
            items = sorted((p for p in self.pubs if p["category"] == cat["key"]), key=label_num, reverse=True)
            total += len(items)
            n = len(items)
            one, many = cat.get("unit", ["paper", "papers"])
            count = f"{n} {one if n == 1 else many}"
            chips.append(f'<a class="chip{" is-empty" if not n else ""}" href="#{cat["key"]}" data-type="{esc(cat["key"])}">'
                         f'<span class="chip-prefix">{esc(cat["prefix"])}</span>{esc(cat["title"])}<span class="chip-count">{n}</span></a>')
            body = ("\n".join(self.pub_entry(p, root) for p in items) if items
                    else f'      <p class="pub-empty">{inline(cat.get("empty", "Nothing here yet."), root)}</p>')
            sections.append(f'''    <section class="pub-section" id="{esc(cat["key"])}" aria-labelledby="{esc(cat["key"])}-h">
      <div class="container">
        <header class="pub-section-head">
          <span class="cat-badge" aria-hidden="true">{esc(cat["prefix"])}</span>
          <div><h2 id="{esc(cat["key"])}-h">{esc(cat["title"])}</h2><p>{esc(cat.get("caption", ""))}</p></div>
          <span class="cat-count">{count}</span>
        </header>
        <div class="pub-list">
{body}
        </div>
      </div>
    </section>''')
        scholar = self.cfg["links"].get("scholar")
        scholar_link = (f' <a class="chip chip-out" href="{esc(scholar)}" target="_blank" rel="noopener">'
                        f'{icon("scholar")}Google Scholar</a>') if scholar else ""
        lede = ("Research on the certification, robustness and identification of learning-based models "
                "for dynamical and control systems. Labels: "
                + ", ".join(f'<b>{esc(c["prefix"])}</b> {esc(" ".join(w.lower() if w[1:].islower() else w for w in c["title"].split()))}' for c in self.categories) + ".")
        content = f'''{self.page_head("Research output", "Publications", lede, art_cpwa("p-cpwa"))}
{self.filter_bar(chips, scholar_link)}
{chr(10).join(sections)}
    <div class="container"><p class="filter-empty" hidden>No publications match these filters. <button type="button" class="filter-reset-inline">Reset filters</button></p></div>
    <section class="container pub-note">
      <p>Manuscripts are the authors' versions, provided for personal and scholarly use. Copyright of published papers
      belongs to the respective publishers (IEEE, IFAC); please cite the published versions.</p>
    </section>'''
        self.write("publications/index.html", title="Publications · Marco Ledda", content=content,
                   active="publications/",
                   description=f"Publications of Marco Ledda ({total} entries): certification of learning-based models, adversarial perturbations, neural system identification.")

    def build_talks(self):
        root = "../"
        talks = sorted(self.talks, key=lambda t: sort_key_date(t["date"]), reverse=True)
        rows = []
        for t in talks:
            start, label, iso = parse_date(t["date"])
            event = esc(t["event"])
            if t.get("event_url"):
                event = f'<a href="{esc(t["event_url"])}" target="_blank" rel="noopener">{event}</a>'
            acts = []
            if t.get("slug"):
                acts.append(f'<a class="act act-primary" href="{root}slides/{esc(t["slug"])}/">{icon("slides")}View slides</a>')
            if t.get("slides"):
                acts.append(f'<a class="act" href="{root}{esc(t["slides"])}" download>{icon("download")}PDF</a>')
            if t.get("paper"):
                acts.append(f'<a class="act" href="{root}publications/#{esc(t["paper"])}">{icon("pdf")}Paper [{esc(t["paper"])}]</a>')
            withs = f'<p class="talk-with">with {self.authors(t["authors"], root)}</p>' if t.get("authors") else ""
            rows.append(f'''        <article class="talk" id="{esc(t.get("slug", ""))}">
          <div class="talk-when"><time datetime="{esc(iso)}">{label}</time><span class="talk-kind">{esc(t.get("kind", ""))}</span></div>
          <div class="talk-body">
            <h3>{esc(t["title"])}</h3>
            <p class="talk-event">{event}</p>
            <p class="talk-place">{icon("pin")}{esc(t.get("place", ""))}</p>
            {withs}
            <div class="pub-actions">{"".join(acts)}</div>
          </div>
        </article>''')
        content = f'''{self.page_head("Talks & slides", "Talks", "Presentations at international conferences and national meetings, with slides available for download.", art_bode("t-bode"))}
    <section class="section section-tight">
      <div class="container talk-list">
{chr(10).join(rows)}
      </div>
    </section>'''
        self.write("talks/index.html", title="Talks · Marco Ledda", content=content, active="talks/",
                   description="Talks and slides by Marco Ledda at IEEE CDC, IEEE CASE, IFAC World Congress and Automatica.it.")

    def build_teaching(self):
        root = "../"
        cards = []
        for c in self.teaching.get("course", []):
            topics = "".join(f"<li>{esc(x)}</li>" for x in c.get("topics", []))
            extra = []
            if c.get("url"):
                extra.append(f'<a class="act" href="{esc(c["url"])}" target="_blank" rel="noopener">{icon("doi")}Course page</a>')
            if c.get("materials"):
                extra.append(f'<a class="act act-primary" href="{esc(href(c["materials"], root))}">{icon("pdf")}Materials</a>')
            actions = f'<div class="pub-actions">{"".join(extra)}</div>' if extra else ""
            yrs = c.get("years") or ([c["year"]] if c.get("year") else [])
            years = "".join(f'<span class="course-year">{esc(y)}</span>' for y in yrs)
            activities = (f'<div><dt>Activities</dt><dd>{esc(c["activities"])}</dd></div>'
                          if c.get("activities") else "")
            cards.append(f'''        <article class="course">
          <p class="course-meta">{years}<span>{esc(c.get("role", ""))}</span></p>
          <h3>{esc(c["course"])}</h3>
          <p class="course-en">{esc(c.get("course_en", ""))}</p>
          <dl class="course-facts">
            <div><dt>Program</dt><dd>{esc(c.get("program", ""))}</dd></div>
            <div><dt>Instructor</dt><dd>{self.authors([c["instructor"]], root) if c.get("instructor") else ""}</dd></div>
            {activities}
          </dl>
          <ul class="course-topics">{topics}</ul>
          {actions}
        </article>''')
        content = f'''{self.page_head("Teaching", "Teaching", esc(self.teaching.get("intro", "")), art_nyquist("te-nyq"))}
    <section class="section section-tight">
      <div class="container course-grid">
{chr(10).join(cards)}
      </div>
    </section>'''
        self.write("teaching/index.html", title="Teaching · Marco Ledda", content=content, active="teaching/",
                   description="Teaching activities of Marco Ledda at the University of Cagliari.")

    def build_news(self):
        root = "../"
        groups: dict[str, list] = {}
        for n in self.sorted_news():
            groups.setdefault(str(n["date"])[:4], []).append(n)
        blocks = []
        for year, items in groups.items():
            blocks.append(f'''      <div class="news-year">
        <h2 class="year-label">{year}</h2>
        {self.news_list(items, root)}
      </div>''')
        content = f'''{self.page_head("Updates", "News", "Papers, conferences and other updates.", art_stems("n-stems"))}
    <section class="section section-tight">
      <div class="container news-archive">
{chr(10).join(blocks)}
      </div>
    </section>'''
        self.write("news/index.html", title="News · Marco Ledda", content=content, active="news/",
                   description="News and updates from Marco Ledda.")

    def build_slides(self):
        root = "../../"
        for t in self.talks:
            if not t.get("slug") or not t.get("slides"):
                continue
            start, label, iso = parse_date(t["date"])
            pdf = f'{root}{t["slides"]}'
            paper = self.by_id.get(t.get("paper", ""))
            acts = [f'<a class="act act-primary" href="{esc(pdf)}" target="_blank" rel="noopener">{icon("slides")}Open slides (PDF)</a>',
                    f'<a class="act" href="{esc(pdf)}" download>{icon("download")}Download</a>']
            if paper:
                acts.append(f'<a class="act" href="{root}publications/#{esc(paper["id"])}">{icon("pdf")}Paper [{esc(paper["id"])}]</a>')
            acts.append(f'<a class="act" href="{root}talks/">{icon("arrow")}All talks</a>')
            event = esc(t["event"])
            if t.get("event_url"):
                event = f'<a href="{esc(t["event_url"])}" target="_blank" rel="noopener">{event}</a>'
            content = f'''    <section class="slides-page">
      <div class="container">
        <p class="eyebrow">Slides &middot; {label}</p>
        <h1>{esc(t["title"])}</h1>
        <p class="slides-authors">{self.authors(["M. Ledda"] + t.get("authors", []), root)}</p>
        <p class="slides-event">{event} &middot; {esc(t.get("place", ""))}</p>
        <div class="pub-actions">{"".join(acts)}</div>
        <div class="slides-frame">
          <iframe src="{esc(pdf)}#view=FitH" title="Slides: {esc(t["title"])}" loading="lazy"></iframe>
        </div>
        <p class="slides-fallback">If the slides do not appear above, <a href="{esc(pdf)}" target="_blank" rel="noopener">open the PDF directly</a>.</p>
      </div>
    </section>'''
            self.write(f'slides/{t["slug"]}/index.html', title=f'Slides: {t["title"]} · Marco Ledda',
                       content=content, description=f'Slides of the talk “{t["title"]}” at {t["event"]}.',
                       body_class="slides")

    def build_readers(self):
        """Pages to read a PDF online, e.g. the M.Sc. thesis at /thesis/."""
        for p in self.pubs:
            if not p.get("reader") or not p.get("manuscript"):
                continue
            slug = p["reader"].strip("/")
            root = "../" * (slug.count("/") + 1)
            pdf = f'{root}{p["manuscript"]}'
            acts = [f'<a class="act act-primary" href="{esc(pdf)}" target="_blank" rel="noopener">{icon("pdf")}Open PDF</a>',
                    f'<a class="act" href="{esc(pdf)}" download>{icon("download")}Download</a>',
                    f'<a class="act" href="{root}publications/#{esc(p["id"])}">{icon("arrow")}Publications</a>']
            note = f'<p class="slides-event">{inline(p["note"], root)}</p>' if p.get("note") else ""
            abstract = (f'<div class="panel panel-abs reader-abstract"><p class="reader-abstract-label">Abstract</p>'
                        f'{paragraphs(p["abstract"], root)}</div>') if p.get("abstract") else ""
            content = f'''    <section class="slides-page">
      <div class="container">
        <p class="eyebrow">{esc(p.get("short") or p["venue"])} &middot; {p["year"]}</p>
        <h1>{esc(p["title"])}</h1>
        <p class="slides-authors">{self.authors(p["authors"], root)}</p>
        <p class="slides-event">{esc(p["venue"])}, {p["year"]}</p>
        {note}
        <div class="pub-actions">{"".join(acts)}</div>
        {abstract}
        <div class="slides-frame doc-frame">
          <iframe src="{esc(pdf)}#view=FitH" title="{esc(p["title"])}" loading="lazy"></iframe>
        </div>
        <p class="slides-fallback">If the document does not appear above, <a href="{esc(pdf)}" target="_blank" rel="noopener">open the PDF directly</a>.</p>
      </div>
    </section>'''
            self.write(f"{slug}/index.html", title=f'{p["title"]} · Marco Ledda', content=content,
                       description=f'{p.get("short") or p["venue"]} by Marco Ledda: {p["title"]}.')

    def build_redirects(self):
        """Old WordPress URLs keep working."""
        for old, new in {"presentations": "talks/", "tutoring": "teaching/", "slides": "talks/"}.items():
            target = f"../{new}"
            page = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Redirecting…</title>
<meta http-equiv="refresh" content="0; url={target}"><link rel="canonical" href="{self.cfg["base_url"]}/{new}">
<meta name="robots" content="noindex"></head>
<body><p>This page has moved to <a href="{target}">{self.cfg["base_url"]}/{new}</a>.</p></body></html>
'''
            (OUT / old).mkdir(parents=True, exist_ok=True)
            (OUT / old / "index.html").write_text(page, "utf-8")

    def build_404(self):
        content = f'''    <section class="page-head page-404">
      <div class="container page-head-inner">
        <div class="page-head-text">
          <p class="eyebrow">Error 404</p>
          <h1>Page not found</h1>
          <p class="lede">The page you are looking for does not exist or has moved. Try the <a href="/">homepage</a>, the <a href="/publications/">publications</a> or the <a href="/talks/">talks</a>.</p>
        </div>
        <div class="page-head-art" aria-hidden="true">{art_nyquist("e-nyq")}</div>
      </div>
    </section>'''
        self.write("404.html", title="Page not found · Marco Ledda", content=content,
                   absolute_root=True, head_extra='  <meta name="robots" content="noindex">')

    def build_meta(self):
        base = self.cfg["base_url"]
        urls = "\n".join(f"  <url><loc>{base}/{p}</loc><lastmod>{TODAY.isoformat()}</lastmod></url>"
                         for p in self.pages)
        (OUT / "sitemap.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n', "utf-8")
        (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", "utf-8")
        (OUT / ".nojekyll").write_text("", "utf-8")

    def build(self):
        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir()
        for item in STATIC:
            src = ROOT / item
            if src.is_dir():
                shutil.copytree(src, OUT / item, ignore=shutil.ignore_patterns(".DS_Store"))
            elif src.exists():
                shutil.copy2(src, OUT / item)
        self.build_home()
        self.build_publications()
        self.build_talks()
        self.build_teaching()
        self.build_news()
        self.build_slides()
        self.build_readers()
        self.build_redirects()
        self.build_404()
        self.build_meta()
        n_html = len(list(OUT.rglob("*.html")))
        print(f"Built {n_html} pages into {OUT.relative_to(ROOT)}/ "
              f"({len(self.pubs)} publications, {len(self.news)} news, {len(self.talks)} talks)")


def serve(port: int):
    import functools
    import http.server

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Preview at http://localhost:{port}/  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    Site().build()
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        serve(int(sys.argv[2]) if len(sys.argv) > 2 else 8000)
