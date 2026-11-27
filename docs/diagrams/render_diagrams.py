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

    def card(self, x, y, width, height, title, lines, accent=False, size=23):
        fill = "#f2f7fc" if accent else "#ffffff"
        self.parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="{fill}" stroke="#bccbd9" stroke-width="1.6"/>')
        self.text(x + width / 2, y + 36, title, size, anchor="middle", weight=600)
        for index, line in enumerate(lines):
            self.text(x + width / 2, y + 74 + index * 28, line, 17, anchor="middle", fill="#536171")


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
        "A1X · Test-time scaling + RSA",
        "Parallel discovery, deeper exploit search, and evidence-grounded recombination.",
        height=1020, width=1800,
    )
    f.text(64, 156, "TTS (test-time scaling): allocate more inference and execution effort during the hunt.", 19)
    f.text(64, 187, "RSA (recursive self-aggregation): reuse parent results to build and test new attack paths.", 19)
    # Five columns. The middle column separates depth, composition, and breadth.
    f.edge("M310 500H360")
    f.edge("M630 500H680")
    f.edge("M650 500V285H680")
    f.edge("M650 500V715H680")
    f.edge("M1040 285H1065V715H1040", arrow=False)
    f.edge("M1040 500H1090")
    f.edge("M1370 500H1420")
    # Execution results inform the next population; no vote establishes a bug.
    f.edge("M1420 570H1405Q1390 570 1390 585V855Q1390 875 1370 875H515Q495 875 495 855V600")
    f.edge("M1585 610V700")
    f.card(50, 390, 260, 220, "Parallel discovery", [
        "4 independent Codex lanes", "Value / numerical",
        "Authority / trust", "Lifecycle / composition", "Adversarial refutation",
    ], True, size=23)
    f.card(360, 400, 270, 200, "Shared evidence", [
        "Attack prefixes & traces", "Constraints & blockers",
        "Select diverse leads", "Retain useful alternatives",
    ], True)
    f.card(680, 210, 360, 150, "K=1 · Sequential depth", [
        "Continue one partial exploit", "Resolve its next prerequisite",
    ])
    f.card(680, 420, 360, 160, "K=2 · RSA composition", [
        "Combine two grounded leads", "Check state, actors & call order",
        "Example: prefix + solved constraint",
    ])
    f.card(680, 640, 360, 150, "Fresh · Independent search", [
        "Explore another mechanism", "Without parent conclusions",
    ], size=22)
    f.card(1090, 390, 280, 220, "Execute experiments", [
        "Pinned local fork", "PoC tests + fuzz/solver replay",
        "Record traces & state deltas",
    ], True, size=22)
    f.card(1420, 390, 330, 220, "Assess execution", [
        "New reachable state?", "Prerequisite resolved?",
        "Property violation + control?", "Mechanism refuted?",
    ], True)
    f.card(1420, 700, 330, 145, "Validate candidate", [
        "Clean replay & target fidelity", "Independent review",
    ])
    f.text(1605, 660, "Supported violation", 16)
    f.text(935, 909, "Next generation: select follow-up experiments using execution evidence", 19, anchor="middle")
    f.text(935, 950, "K = parent results reused by each worker · Incompatible parents remain separate", 17, anchor="middle", fill="#536171")
    f.text(935, 978, "Continue within campaign budgets; track progress separately for each attack mechanism.", 17, anchor="middle", fill="#536171")
    f.save("test-time-scaling-rsa")


if __name__ == "__main__":
    investigation()
    scaling()
