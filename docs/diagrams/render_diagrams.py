#!/usr/bin/env python3
"""Render editable SVG graphs and optional PNG mirrors with CairoSVG."""

from html import escape
from pathlib import Path


OUT = Path(__file__).resolve().parents[1] / "images"
OUT.mkdir(parents=True, exist_ok=True)


class Figure:
    def __init__(self, title, subtitle, height=1100):
        self.height = height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" viewBox="0 0 1600 {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title>',
            f'<desc id="desc">{escape(subtitle)}</desc>',
            '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0 0L9 4.5L0 9Z" fill="#647d94"/></marker></defs>',
            f'<rect width="1600" height="{height}" fill="white"/>',
            '<g font-family="DejaVu Sans, Arial, sans-serif">',
        ]
        self.text(64, 70, title, 37, weight=700)
        self.text(64, 111, subtitle, 20, fill="#536171")

    def text(self, x, y, value, size=24, anchor="start", weight=400, fill="#17212b"):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{escape(value)}</text>')

    def edge(self, path, arrow=True):
        marker = ' marker-end="url(#arrow)"' if arrow else ''
        self.parts.append(f'<path d="{path}" fill="none" stroke="#647d94" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"{marker}/>')

    def node(self, x, y, width, height, title, subtitle=None, accent=False, size=24):
        fill = "#f2f7fc" if accent else "#ffffff"
        self.parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="{fill}" stroke="#bccbd9" stroke-width="1.6"/>')
        baseline = y + height / 2 + (8 if subtitle is None else -4)
        self.text(x + width / 2, baseline, title, size, anchor="middle", weight=600)
        if subtitle:
            self.text(x + width / 2, baseline + 31, subtitle, 17, anchor="middle", fill="#536171")

    def save(self, stem):
        path = OUT / f"{stem}.svg"
        path.write_text("\n".join(self.parts + ["</g></svg>"]) + "\n", encoding="utf-8")
        try:
            import cairosvg
        except ImportError:
            print("CairoSVG is absent; keeping SVG only.")
        else:
            cairosvg.svg2png(url=str(path), write_to=str(OUT / f"{stem}.png"))
        print(path.relative_to(OUT.parent.parent))


def investigation():
    f = Figure("A1X investigation workflow", "From protocol obligations to tested vulnerability evidence")
    # Directed edges are explicit; feedback enters analysis, not validation.
    for p in ("M800 240V290", "M800 390V440", "M800 540V590", "M800 690V750", "M1100 800H1190", "M500 800H409", "M236.5 850V950"):
        f.edge(p)
    f.edge("M1362.5 750V520Q1362.5 490 1332.5 490H1100")
    f.node(560, 160, 480, 80, "Target + pinned state")
    f.node(510, 290, 580, 100, "Independent first pass", "Value · authority · lifecycle · refutation")
    f.node(500, 440, 600, 100, "Map, derive, compose", "Protocol obligations + reachable attack path", True)
    f.node(500, 590, 600, 100, "Execute a discriminating test", "Deterministic execution · fuzzing · solving")
    f.node(500, 750, 600, 100, "Evidence + remaining prerequisites", accent=True)
    f.node(1190, 750, 345, 100, "Test-time scaling + RSA", "Close · compose · explore", size=21)
    f.node(64, 750, 345, 100, "Validate + replay", "Causal control · fidelity · review", size=23)
    f.node(64, 950, 345, 90, "Measured impact", "+ open risks", size=23)
    f.text(454, 775, "Candidate", 15, anchor="middle")
    f.text(1380, 603, "Next", 18)
    f.text(1380, 630, "experiments", 18)
    f.save("investigation-workflow")


def scaling():
    f = Figure("Test-time scaling and RSA", "Allocate compute across continuation, composition and independent discovery")
    f.edge("M820 250V310")
    f.edge("M820 400V450H410V500")
    f.edge("M820 450V500")
    f.edge("M820 450H1280V500")
    f.edge("M410 610V680Q410 700 430 700H820", arrow=False)
    f.edge("M1280 610V680Q1280 700 1260 700H820", arrow=False)
    f.edge("M820 610V770")
    # A single arrowhead at the population: assessment is the feedback origin.
    f.edge("M520 825H110Q80 825 80 795V235Q80 205 110 205H520")
    f.edge("M820 880V950")
    f.node(520, 160, 600, 90, "Grounded lead population", accent=True, size=27)
    f.node(500, 310, 640, 90, "Select leads + preserve reserve", accent=True, size=26)
    f.node(230, 500, 360, 110, "K=1 · Close a witness", "One parent → next prerequisite", size=22)
    f.node(640, 500, 360, 110, "K=2 · Compose leads", "Two parents → compatibility test", size=22)
    f.node(1050, 500, 460, 110, "Fresh · Explore independently", "New perspective → cheapest test", size=22)
    f.node(520, 770, 600, 110, "Execute + assess evidence", "Phase advance · prerequisite closure · refutation", True, size=26)
    f.node(580, 950, 480, 90, "Validate, retain or record blocker", size=23)
    f.text(110, 420, "Next generation", 18)
    f.text(110, 449, "within budget", 18)
    f.text(1005, 657, "Incompatible parents", 16, anchor="middle", fill="#536171")
    f.text(1005, 682, "stay separate", 16, anchor="middle", fill="#536171")
    f.save("test-time-scaling-rsa")


if __name__ == "__main__":
    investigation()
    scaling()
