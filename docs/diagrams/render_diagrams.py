#!/usr/bin/env python3
"""Render editable SVG graphs and optional PNG mirrors with CairoSVG."""

from html import escape
from pathlib import Path


OUT = Path(__file__).resolve().parents[1] / "images"
OUT.mkdir(parents=True, exist_ok=True)


class Figure:
    def __init__(self, title, subtitle, height=1100, width=1600):
        self.height = height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title>',
            f'<desc id="desc">{escape(subtitle)}</desc>',
            '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0 0L9 4.5L0 9Z" fill="#647d94"/></marker></defs>',
            f'<rect width="{width}" height="{height}" fill="white"/>',
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
    f = Figure(
        "How A1X explores attack ideas",
        "Keep working on promising ideas, combine discoveries, and try new approaches.",
        height=900, width=2000,
    )
    # Five columns, left to right. The three ways to explore are alternatives.
    f.edge("M328 460H400")
    f.edge("M700 460H770")
    f.edge("M735 460V260H770")
    f.edge("M735 460V660H770")
    f.edge("M1120 260H1155V660H1120", arrow=False)
    f.edge("M1120 460H1200")
    f.edge("M1480 460H1550")
    # Results feed another choice of tests; the loop has one arrowhead.
    f.edge("M1550 495H1510Q1490 495 1490 515V770Q1490 790 1470 790H570Q550 790 550 770V515")
    f.edge("M1740 515V610")
    f.node(48, 405, 280, 110, "Find attack ideas", "Independent AI investigations", accent=True, size=24)
    f.node(400, 405, 300, 110, "Choose the next tests", "Keep useful alternatives", accent=True, size=23)
    f.node(770, 210, 350, 100, "Keep working on an idea", "Solve the next missing step", size=22)
    f.node(770, 405, 350, 110, "Combine two ideas", "Check whether they fit together", size=24)
    f.node(770, 610, 350, 100, "Try a new idea", "Look from a different angle", size=24)
    f.node(1200, 405, 280, 110, "Run local tests", "Test ideas on a local fork", accent=True, size=24)
    f.node(1550, 405, 380, 110, "Check the results", "Did the idea actually work?", accent=True, size=25)
    f.node(1550, 610, 380, 100, "Confirm the finding", "Replay it and challenge it", size=24)
    f.text(1760, 570, "Possible bug", 17)
    f.text(1010, 826, "Use the results to choose the next round", 20, anchor="middle")
    f.text(945, 555, "Keep separate if they do not fit.", 16, anchor="middle", fill="#536171")
    f.save("test-time-scaling-rsa")


if __name__ == "__main__":
    investigation()
    scaling()
