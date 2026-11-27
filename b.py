#!/usr/bin/env python3
"""
ZOOM: An Everyday, Symbol-Free Programming Language for Real & Complex Analysis
==============================================================================
Features:
  - Explicit everyday vocabulary: `goal`, `buffer`, `cutoff`, `step`
  - Real Analysis: `limit`, `cauchy`, `continuity`, `uniform_continuity`, `derivative`
  - Complex Analysis: `complex_continuity`, `complex_derivative` (360-degree check)
  - Built-in Terminal ASCII diagrams + zero-dependency `zoom_view.html` visual export

Usage:
  1. Run a .zoom file:      python3 zoom_lang.py my_notes.zoom
  2. Interactive prompt:    python3 zoom_lang.py
"""

import cmath
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# =====================================================================
# 1. SAFE MATH EVALUATOR (Real & Complex)
# =====================================================================
SAFE_ENV = {
    "abs": abs,
    "min": min,
    "max": max,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "exp": math.exp,
    "log": math.log,
    "sqrt": math.sqrt,
    "pi": math.pi,
    "e": math.e,
    "j": 1j,
    "csin": cmath.sin,
    "ccos": cmath.cos,
    "cexp": cmath.exp,
    "clog": cmath.log,
    "csqrt": cmath.sqrt,
}


def make_sequence(expr: str) -> Callable[[int], float]:
    code = compile(expr, "<sequence>", "eval")
    return lambda n: float(eval(code, {"__builtins__": {}}, {**SAFE_ENV, "n": n}))


def make_curve(expr: str) -> Callable[[float], float]:
    code = compile(expr, "<curve>", "eval")
    return lambda x: float(eval(code, {"__builtins__": {}}, {**SAFE_ENV, "x": x}))


def make_complex_func(expr: str) -> Callable[[complex], complex]:
    code = compile(expr, "<complex_func>", "eval")
    return lambda z: complex(eval(code, {"__builtins__": {}}, {**SAFE_ENV, "z": z}))


def parse_complex_literal(raw: str) -> complex:
    cleaned = raw.strip().replace(" ", "").replace("i", "j")
    return complex(cleaned)


# =====================================================================
# 2. TEST REPORT + VISUAL DATA STRUCTURE
# =====================================================================
@dataclass
class TestReport:
    passed: bool
    title: str
    summary: str
    details: List[str]
    ascii_art: str = ""
    viz_payload: Dict[str, Any] = field(default_factory=dict)


# =====================================================================
# 3. TERMINAL ASCII VISUALIZERS
# =====================================================================
def render_ascii_sequence(
    values: List[float], target: float, goal: float, cutoff: Optional[int], width: int = 56, height: int = 11
) -> str:
    if not values:
        return ""
    lo = min(min(values), target - goal * 1.5)
    hi = max(max(values), target + goal * 1.5)
    if abs(hi - lo) < 1e-12:
        hi += 1.0
        lo -= 1.0

    grid = [[" " for _ in range(width)] for _ in range(height)]

    def to_row(val: float) -> int:
        norm = (val - lo) / (hi - lo)
        r = int(round((1.0 - norm) * (height - 1)))
        return max(0, min(height - 1, r))

    top_band = to_row(target + goal)
    bot_band = to_row(target - goal)
    tgt_row = to_row(target)

    for c in range(width):
        grid[top_band][c] = "-"
        grid[bot_band][c] = "-"
        grid[tgt_row][c] = "."

    if cutoff is not None and 1 <= cutoff <= len(values):
        cut_col = int((cutoff - 1) / max(1, len(values) - 1) * (width - 1))
        for r in range(height):
            grid[r][cut_col] = "|"

    for idx, val in enumerate(values):
        c = int(idx / max(1, len(values) - 1) * (width - 1))
        r = to_row(val)
        grid[r][c] = "●"

    lines = ["  [Visual: '-' = goal band, '|' = cutoff, '●' = sequence steps]"]
    for r in range(height):
        lines.append("  " + "".join(grid[r]))
    return "\n".join(lines)


def render_ascii_curve_box(
    f: Callable[[float], float], at_x: float, goal: float, buffer_w: Optional[float], width: int = 56, height: int = 13
) -> str:
    center_y = f(at_x)
    span_x = (buffer_w * 2.5) if buffer_w else 0.5
    xs = [at_x - span_x + (2 * span_x * i / (width - 1)) for i in range(width)]
    ys = []
    for x in xs:
        try:
            ys.append(f(x))
        except Exception:
            ys.append(float("nan"))

    valid_ys = [y for y in ys if not math.isnan(y) and not math.isinf(y)]
    lo = min(min(valid_ys, default=center_y - goal), center_y - goal * 1.6)
    hi = max(max(valid_ys, default=center_y + goal), center_y + goal * 1.6)
    if abs(hi - lo) < 1e-12:
        hi += 1.0
        lo -= 1.0

    grid = [[" " for _ in range(width)] for _ in range(height)]

    def to_row(val: float) -> int:
        norm = (val - lo) / (hi - lo)
        r = int(round((1.0 - norm) * (height - 1)))
        return max(0, min(height - 1, r))

    top_g = to_row(center_y + goal)
    bot_g = to_row(center_y - goal)
    for c in range(width):
        grid[top_g][c] = "-"
        grid[bot_g][c] = "-"

    if buffer_w is not None:
        left_c = int(((at_x - buffer_w) - (at_x - span_x)) / (2 * span_x) * (width - 1))
        right_c = int(((at_x + buffer_w) - (at_x - span_x)) / (2 * span_x) * (width - 1))
        for r in range(height):
            if 0 <= left_c < width:
                grid[r][left_c] = "|"
            if 0 <= right_c < width:
                grid[r][right_c] = "|"

    for c, y in enumerate(ys):
        if not math.isnan(y) and not math.isinf(y):
            grid[to_row(y)][c] = "*"

    lines = ["  [Visual: '-' = goal ceiling/floor, '|' = buffer walls, '*' = curve]"]
    for r in range(height):
        lines.append("  " + "".join(grid[r]))
    return "\n".join(lines)


def render_ascii_complex_slopes(slopes: List[complex], goal: float) -> str:
    """Renders the 8 compass directional slopes on a 2D complex plane grid."""
    width, height = 41, 15
    cx, cy = width // 2, height // 2
    grid = [[" " for _ in range(width)] for _ in range(height)]

    for c in range(width):
        grid[cy][c] = "·"
    for r in range(height):
        grid[r][cx] = "·"
    grid[cy][cx] = "+"

    mean_s = sum(slopes) / len(slopes)
    max_dev = max([abs(s - mean_s) for s in slopes] + [goal * 1.5, 1e-6])

    labels = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]
    for idx, s in enumerate(slopes):
        dx = (s.real - mean_s.real) / max_dev
        dy = (s.imag - mean_s.imag) / max_dev
        col = max(1, min(width - 2, int(round(cx + dx * (cx - 3)))))
        row = max(1, min(height - 2, int(round(cy - dy * (cy - 2)))))
        grid[row][col] = labels[idx][0]

    lines = [
        f"  [Visual: 360° Slope Cluster around center {mean_s:.3g} | tight cluster = differentiable]"
    ]
    for r in range(height):
        lines.append("  " + "".join(grid[r]))
    return "\n".join(lines)


# =====================================================================
# 4. REAL & COMPLEX ANALYSIS ENGINE
# =====================================================================
def run_limit_test(
    seq_expr: str,
    target: float,
    goals: List[float],
    max_n: int = 5000,
    hold_window: int = 200,
) -> TestReport:
    f = make_sequence(seq_expr)
    details = []
    all_passed = True
    last_cutoff = None

    for g in goals:
        cutoff = None
        for start in range(1, max_n - hold_window):
            if all(abs(f(k) - target) < g for k in range(start, start + hold_window)):
                cutoff = start
                break

        last_cutoff = cutoff
        if cutoff is not None:
            details.append(
                f"  [OK]   goal({g}) -> cutoff at step {cutoff} "
                f"(every step after #{cutoff} stays inside [{target - g:.4g}, {target + g:.4g}])"
            )
        else:
            all_passed = False
            bad_n = next(
                (k for k in range(max_n - 50, max_n) if abs(f(k) - target) >= g),
                max_n,
            )
            details.append(
                f"  [FAIL] goal({g}) -> NO cutoff found! "
                f"At step {bad_n}, value = {f(bad_n):.4g} misses the goal."
            )

    tightest_g = goals[-1]
    plot_n = max(40, (last_cutoff * 2) if last_cutoff else 60)
    plot_n = min(plot_n, 200)
    sample_vals = [f(k) for k in range(1, plot_n + 1)]
    ascii_art = render_ascii_sequence(sample_vals, target, tightest_g, last_cutoff)

    summary = (
        f"PASS: '{seq_expr}' reaches target {target} within every tested goal."
        if all_passed
        else f"BREAKS: '{seq_expr}' fails to stay within tight goals around {target}."
    )
    return TestReport(
        all_passed,
        f"Limit Check: {seq_expr} -> {target}",
        summary,
        details,
        ascii_art,
        {
            "type": "limit",
            "title": f"Limit: {seq_expr} -> {target}",
            "values": sample_vals,
            "target": target,
            "goal": tightest_g,
            "cutoff": last_cutoff,
        },
    )


def run_cauchy_test(
    seq_expr: str,
    goals: List[float],
    max_n: int = 2000,
    lookahead: int = 80,
) -> TestReport:
    f = make_sequence(seq_expr)
    details = []
    all_passed = True
    last_cutoff = None

    for g in goals:
        cutoff = None
        for start in range(1, max_n - lookahead):
            window = [f(k) for k in range(start, start + lookahead)]
            if max(window) - min(window) < g:
                cutoff = start
                break

        last_cutoff = cutoff
        if cutoff is not None:
            details.append(
                f"  [OK]   goal({g}) -> cutoff at step {cutoff} "
                f"(all remaining steps stay within {g} of each other)"
            )
        else:
            all_passed = False
            details.append(f"  [FAIL] goal({g}) -> steps never stop drifting apart.")

    sample_vals = [f(k) for k in range(1, 81)]
    est_target = sample_vals[-1]
    ascii_art = render_ascii_sequence(sample_vals, est_target, goals[-1], last_cutoff)

    summary = (
        f"PASS: '{seq_expr}' is Cauchy (steps huddle within any goal without needing a target)."
        if all_passed
        else f"BREAKS: '{seq_expr}' is NOT Cauchy."
    )
    return TestReport(
        all_passed,
        f"Cauchy Check: {seq_expr}",
        summary,
        details,
        ascii_art,
        {
            "type": "limit",
            "title": f"Cauchy: {seq_expr}",
            "values": sample_vals,
            "target": est_target,
            "goal": goals[-1],
            "cutoff": last_cutoff,
        },
    )


def run_continuity_test(
    curve_expr: str,
    at_x: float,
    goals: List[float],
    samples: int = 200,
) -> TestReport:
    f = make_curve(curve_expr)
    center_y = f(at_x)
    details = []
    all_passed = True
    last_buf = None

    for g in goals:
        found_b = None
        for exp in range(1, 28):
            b = 0.5 ** exp
            xs = [at_x - b + (2 * b * i / samples) for i in range(samples + 1)]
            try:
                if all(abs(f(x) - center_y) < g for x in xs):
                    found_b = b
                    break
            except Exception:
                continue

        last_buf = found_b
        if found_b is not None:
            details.append(
                f"  [OK]   goal({g}) -> buffer({found_b:.6g}) "
                f"(staying within ±{found_b:.6g} of x={at_x} hits the output goal)"
            )
        else:
            all_passed = False
            details.append(
                f"  [FAIL] goal({g}) -> NO buffer works; curve jumps or blows up at x = {at_x}!"
            )

    tightest_g = goals[-1]
    ascii_art = render_ascii_curve_box(f, at_x, tightest_g, last_buf)

    span = (last_buf * 2.5) if last_buf else 0.5
    plot_xs = [at_x - span + (2 * span * i / 120) for i in range(121)]
    plot_ys = []
    for x in plot_xs:
        try:
            y = f(x)
            plot_ys.append(None if math.isnan(y) or math.isinf(y) else y)
        except Exception:
            plot_ys.append(None)

    summary = (
        f"PASS: '{curve_expr}' is continuous at x = {at_x}."
        if all_passed
        else f"BREAKS: '{curve_expr}' is NOT continuous at x = {at_x}."
    )
    return TestReport(
        all_passed,
        f"Continuity Check: {curve_expr} at x={at_x}",
        summary,
        details,
        ascii_art,
        {
            "type": "continuity",
            "title": f"Continuity: {curve_expr} at x={at_x}",
            "xs": plot_xs,
            "ys": plot_ys,
            "at_x": at_x,
            "center_y": center_y,
            "goal": tightest_g,
            "buffer": last_buf,
        },
    )


def run_uniform_continuity_test(
    curve_expr: str,
    domain: Tuple[float, float],
    goals: List[float],
    grid_points: int = 400,
) -> TestReport:
    f = make_curve(curve_expr)
    a, b = domain
    details = []
    all_passed = True
    last_buf = None

    for g in goals:
        found_buf = None
        worst_x = None
        for exp in range(1, 22):
            buf = 0.5 ** exp
            ok = True
            for i in range(grid_points):
                x1 = a + (b - a) * (i / grid_points)
                x2 = min(b, x1 + buf)
                try:
                    if abs(f(x2) - f(x1)) >= g:
                        ok = False
                        worst_x = x1
                        break
                except Exception:
                    ok = False
                    worst_x = x1
                    break
            if ok:
                found_buf = buf
                break

        last_buf = found_buf
        if found_buf is not None:
            details.append(
                f"  [OK]   goal({g}) -> single buffer({found_buf:.6g}) works everywhere on [{a}, {b}]"
            )
        else:
            all_passed = False
            details.append(
                f"  [FAIL] goal({g}) -> no single buffer works everywhere; "
                f"curve gets too steep near x = {worst_x:.5g}!"
            )

    mid_x = 0.5 * (a + b)
    ascii_art = render_ascii_curve_box(f, mid_x, goals[-1], last_buf)

    summary = (
        f"PASS: '{curve_expr}' is uniformly continuous on [{a}, {b}]."
        if all_passed
        else f"BREAKS: '{curve_expr}' is NOT uniformly continuous on [{a}, {b}]."
    )
    return TestReport(
        all_passed,
        f"Uniform Continuity Check: {curve_expr} on [{a}, {b}]",
        summary,
        details,
        ascii_art,
    )


def run_derivative_test(
    curve_expr: str,
    at_x: float,
    steps: List[float],
    goal: float,
) -> TestReport:
    f = make_curve(curve_expr)
    details = []
    final_gap = float("inf")
    est_slope = 0.0

    for s in steps:
        left_slope = (f(at_x) - f(at_x - s)) / s
        right_slope = (f(at_x + s) - f(at_x)) / s
        gap = abs(right_slope - left_slope)
        final_gap = gap
        est_slope = 0.5 * (left_slope + right_slope)
        status = "OK" if gap < goal else "GAP > GOAL"
        details.append(
            f"  [step({s})] left_slope = {left_slope:.6g}, right_slope = {right_slope:.6g} "
            f"| gap = {gap:.6g} ({status})"
        )

    s_vis = steps[-1]
    span = max(s_vis * 8, 0.05)
    plot_xs = [at_x - span + (2 * span * i / 120) for i in range(121)]
    plot_ys = [f(x) for x in plot_xs]
    ascii_art = render_ascii_curve_box(f, at_x, abs(est_slope) * span + goal, span * 0.4)

    passed = final_gap < goal
    summary = (
        f"PASS: At step({steps[-1]}), left and right slopes agree within goal({goal}) -> slope ≈ {est_slope:.6g}."
        if passed
        else f"BREAKS: At step({steps[-1]}), slope gap ({final_gap:.6g}) exceeds goal({goal}) -> no single tangent line at x = {at_x}."
    )
    return TestReport(
        passed,
        f"Derivative Check: {curve_expr} at x={at_x}",
        summary,
        details,
        ascii_art,
        {
            "type": "derivative",
            "title": f"Derivative: {curve_expr} at x={at_x}",
            "xs": plot_xs,
            "ys": plot_ys,
            "at_x": at_x,
            "center_y": f(at_x),
            "slope": est_slope,
            "passed": passed,
        },
    )


def run_complex_continuity_test(
    func_expr: str,
    at_z: complex,
    goals: List[float],
) -> TestReport:
    """Checks 2D circular disk buffer around at_z -> circular goal disk around f(at_z)."""
    f = make_complex_func(func_expr)
    center_w = f(at_z)
    details = []
    all_passed = True

    angles = [2 * math.pi * k / 24 for k in range(24)]
    for g in goals:
        found_b = None
        for exp in range(1, 26):
            b = 0.5 ** exp
            try:
                ok = all(
                    abs(f(at_z + r * cmath.exp(1j * th)) - center_w) < g
                    for r in (b * 0.5, b)
                    for th in angles
                )
                if ok:
                    found_b = b
                    break
            except Exception:
                continue

        if found_b is not None:
            details.append(
                f"  [OK]   goal_disk({g}) -> buffer_disk({found_b:.6g}) around z={at_z}"
            )
        else:
            all_passed = False
            details.append(
                f"  [FAIL] goal_disk({g}) -> NO buffer disk traps output around z={at_z}!"
            )

    summary = (
        f"PASS: '{func_expr}' is complex-continuous at z = {at_z}."
        if all_passed
        else f"BREAKS: '{func_expr}' is NOT complex-continuous at z = {at_z}."
    )
    return TestReport(all_passed, f"Complex Continuity: {func_expr} at z={at_z}", summary, details)


def run_complex_derivative_test(
    func_expr: str,
    at_z: complex,
    steps: List[float],
    goal: float,
) -> TestReport:
    """Checks whether all 8 compass directions around z produce the same complex slope within `goal`."""
    f = make_complex_func(func_expr)
    directions = [cmath.exp(1j * (2 * math.pi * k / 8)) for k in range(8)]
    details = []
    final_spread = float("inf")
    est_slope = 0j
    last_slopes: List[complex] = []

    for s in steps:
        slopes = [(f(at_z + s * d) - f(at_z)) / (s * d) for d in directions]
        last_slopes = slopes
        spread = max(abs(a - b) for a in slopes for b in slopes)
        final_spread = spread
        est_slope = sum(slopes) / len(slopes)
        status = "OK" if spread < goal else "SPREAD > GOAL"
        details.append(
            f"  [step({s})] east={slopes[0]:.4g}, north={slopes[2]:.4g}, west={slopes[4]:.4g} "
            f"| 360° spread = {spread:.6g} ({status})"
        )

    ascii_art = render_ascii_complex_slopes(last_slopes, goal)
    passed = final_spread < goal
    summary = (
        f"PASS: At step({steps[-1]}), all 360° directions agree within goal({goal}) -> complex slope ≈ {est_slope:.4g}."
        if passed
        else f"BREAKS: 360° slope spread ({final_spread:.6g}) exceeds goal({goal}) -> NOT holomorphic at z = {at_z}."
    )
    return TestReport(
        passed,
        f"Complex Derivative Check: {func_expr} at z={at_z}",
        summary,
        details,
        ascii_art,
        {
            "type": "complex_derivative",
            "title": f"Complex 360° Slope: {func_expr} at z={at_z}",
            "slopes": [[s.real, s.imag] for s in last_slopes],
            "goal": goal,
            "passed": passed,
        },
    )


# =====================================================================
# 5. ZERO-DEPENDENCY HTML CANVAS VISUALIZER GENERATOR
# =====================================================================
def export_html_visualizer(reports: List[TestReport], out_path: Path = Path("zoom_view.html")) -> None:
    payloads = [r.viz_payload for r in reports if r.viz_payload]
    if not payloads:
        return

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>Zoom Analysis Visualizer</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; margin: 24px; }}
  h1 {{ font-size: 1.3rem; margin-bottom: 16px; color: #38bdf8; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(460px, 1fr)); gap: 20px; }}
  .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 16px; }}
  .card h2 {{ font-size: 1rem; margin: 0 0 10px 0; color: #f8fafc; }}
  canvas {{ width: 100%; height: 280px; background: #0b1120; border-radius: 6px; display: block; }}
  .legend {{ font-size: 0.82rem; color: #94a3b8; margin-top: 8px; }}
</style>
</head>
<body>
<h1>ZOOM — Visual Geometry Output</h1>
<div class="grid" id="cards"></div>
<script>
const DATA = {json.dumps(payloads)};
const container = document.getElementById("cards");

DATA.forEach((item) => {{
  const card = document.createElement("div");
  card.className = "card";
  const title = document.createElement("h2");
  title.textContent = item.title;
  const canvas = document.createElement("canvas");
  canvas.width = 520;
  canvas.height = 280;
  const legend = document.createElement("div");
  legend.className = "legend";
  card.append(title, canvas, legend);
  container.appendChild(card);

  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height, PAD = 32;

  if (item.type === "limit") {{
    const vals = item.values;
    const minY = Math.min(...vals, item.target - item.goal * 1.5);
    const maxY = Math.max(...vals, item.target + item.goal * 1.5);
    const mapX = i => PAD + (i / Math.max(1, vals.length - 1)) * (W - 2 * PAD);
    const mapY = y => H - PAD - ((y - minY) / (maxY - minY || 1)) * (H - 2 * PAD);

    // Goal band
    const yTop = mapY(item.target + item.goal);
    const yBot = mapY(item.target - item.goal);
    ctx.fillStyle = "rgba(34, 197, 94, 0.15)";
    ctx.fillRect(PAD, yTop, W - 2 * PAD, yBot - yTop);
    ctx.strokeStyle = "#22c55e";
    ctx.setLineDash([5, 5]);
    ctx.beginPath(); ctx.moveTo(PAD, yTop); ctx.lineTo(W - PAD, yTop);
    ctx.moveTo(PAD, yBot); ctx.lineTo(W - PAD, yBot); ctx.stroke();
    ctx.setLineDash([]);

    // Cutoff line
    if (item.cutoff && item.cutoff <= vals.length) {{
      const cx = mapX(item.cutoff - 1);
      ctx.strokeStyle = "#f59e0b";
      ctx.beginPath(); ctx.moveTo(cx, PAD); ctx.lineTo(cx, H - PAD); ctx.stroke();
    }}

    // Sequence dots
    vals.forEach((v, i) => {{
      ctx.fillStyle = (item.cutoff && i + 1 >= item.cutoff) ? "#4ade80" : "#38bdf8";
      ctx.beginPath(); ctx.arc(mapX(i), mapY(v), 3.2, 0, Math.PI * 2); ctx.fill();
    }});
    legend.textContent = `Green band: target ± goal (${{item.goal}}) | Amber line: cutoff (${{item.cutoff ?? "none"}})`;
  }}

  if (item.type === "continuity" || item.type === "derivative") {{
    const xs = item.xs, ys = item.ys.filter(v => v !== null);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys, item.center_y - (item.goal || 0.2) * 1.5);
    const maxY = Math.max(...ys, item.center_y + (item.goal || 0.2) * 1.5);
    const mapX = x => PAD + ((x - minX) / (maxX - minX || 1)) * (W - 2 * PAD);
    const mapY = y => H - PAD - ((y - minY) / (maxY - minY || 1)) * (H - 2 * PAD);

    if (item.type === "continuity") {{
      const yTop = mapY(item.center_y + item.goal);
      const yBot = mapY(item.center_y - item.goal);
      ctx.fillStyle = "rgba(34, 197, 94, 0.14)";
      ctx.fillRect(PAD, yTop, W - 2 * PAD, yBot - yTop);
      if (item.buffer) {{
        const xL = mapX(item.at_x - item.buffer);
        const xR = mapX(item.at_x + item.buffer);
        ctx.fillStyle = "rgba(56, 189, 248, 0.18)";
        ctx.fillRect(xL, PAD, xR - xL, H - 2 * PAD);
      }}
      legend.textContent = `Green horizontal: goal (±${{item.goal}}) | Blue vertical: buffer (±${{item.buffer ?? "none"}})`;
    }} else {{
      // Tangent line
      const x1 = minX, x2 = maxX;
      const y1 = item.center_y + item.slope * (x1 - item.at_x);
      const y2 = item.center_y + item.slope * (x2 - item.at_x);
      ctx.strokeStyle = item.passed ? "#22c55e" : "#ef4444";
      ctx.setLineDash([6, 4]);
      ctx.beginPath(); ctx.moveTo(mapX(x1), mapY(y1)); ctx.lineTo(mapX(x2), mapY(y2)); ctx.stroke();
      ctx.setLineDash([]);
      legend.textContent = `Dashed line: estimated slope (${{item.slope.toFixed(4)}}) at x = ${{item.at_x}}`;
    }}

    // Curve
    ctx.strokeStyle = "#f8fafc";
    ctx.lineWidth = 2;
    ctx.beginPath();
    item.xs.forEach((x, i) => {{
      const y = item.ys[i];
      if (y === null) return;
      if (i === 0 || item.ys[i - 1] === null) ctx.moveTo(mapX(x), mapY(y));
      else ctx.lineTo(mapX(x), mapY(y));
    }});
    ctx.stroke();
  }}

  if (item.type === "complex_derivative") {{
    const pts = item.slopes;
    const meanRe = pts.reduce((a, p) => a + p[0], 0) / pts.length;
    const meanIm = pts.reduce((a, p) => a + p[1], 0) / pts.length;
    const maxR = Math.max(...pts.map(p => Math.hypot(p[0] - meanRe, p[1] - meanIm)), item.goal * 1.5, 0.01);
    const cx = W / 2, cy = H / 2, scale = (Math.min(W, H) / 2 - PAD) / maxR;

    // Goal disk
    ctx.strokeStyle = "#22c55e";
    ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.arc(cx, cy, item.goal * scale, 0, Math.PI * 2); ctx.stroke();
    ctx.setLineDash([]);

    const dirs = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"];
    pts.forEach((p, idx) => {{
      const px = cx + (p[0] - meanRe) * scale;
      const py = cy - (p[1] - meanIm) * scale;
      ctx.fillStyle = item.passed ? "#4ade80" : "#f87171";
      ctx.beginPath(); ctx.arc(px, py, 5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#cbd5e1";
      ctx.font = "11px sans-serif";
      ctx.fillText(dirs[idx], px + 7, py + 4);
    }});
    legend.textContent = `8 compass directional slopes relative to center (${{meanRe.toFixed(2)}} + ${{meanIm.toFixed(2)}}i) | Green circle = goal(${{item.goal}})`;
  }}
}});
</script>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")


# =====================================================================
# 6. DUAL-SYNTAX PARSER & INTERPRETER
# =====================================================================
class ZoomInterpreter:
    def __init__(self):
        self.blueprints: Dict[str, List[str]] = {}
        self.sequences: Dict[str, str] = {}
        self.curves: Dict[str, str] = {}
        self.complex_funcs: Dict[str, str] = {}
        self.reports: List[TestReport] = []

    def normalize_line(self, line: str) -> str:
        s = line.strip()
        s = re.sub(r"^given\s+goal\s*=\s*([0-9.]+)\s*,?\s*find\s+buffer.*", r"goal(\1) -> buffer", s, flags=re.I)
        s = re.sub(r"^given\s+goal\s*=\s*([0-9.]+)\s*,?\s*find\s+cutoff.*", r"goal(\1) -> cutoff", s, flags=re.I)
        s = re.sub(r"^given\s+goal\s*=\s*([0-9.]+)\s*,?\s*find\s+single\s+buffer.*", r"goal(\1) -> single buffer", s, flags=re.I)
        s = re.sub(r"^with\s+step\s*=\s*([0-9.]+).*", r"step(\1) -> check slope", s, flags=re.I)

        s = re.sub(r"\btunnel\(([0-9.]+)\)", r"goal(\1)", s)
        s = re.sub(r"\bruler\(([0-9.]+)\)", r"goal(\1)", s)
        s = re.sub(r"\bcamera_height\(([0-9.]+)\)", r"goal(\1)", s)
        s = re.sub(r"\bstencil_height\(([0-9.]+)\)", r"goal(\1)", s)
        return s

    def run(self, program: str, export_html: bool = True) -> None:
        self.reports.clear()
        lines = [
            ln.split("#")[0].strip()
            for ln in program.splitlines()
            if ln.split("#")[0].strip()
        ]

        i = 0
        while i < len(lines):
            line = lines[i]

            if line.startswith("sequence "):
                name, expr = [p.strip() for p in line[len("sequence "):].split("=", 1)]
                self.sequences[name] = expr
                i += 1
                continue

            if line.startswith("curve "):
                name, expr = [p.strip() for p in line[len("curve "):].split("=", 1)]
                self.curves[name] = expr
                i += 1
                continue

            if line.startswith("complex_func "):
                name, expr = [p.strip() for p in line[len("complex_func "):].split("=", 1)]
                self.complex_funcs[name] = expr
                i += 1
                continue

            if line.startswith("define "):
                header = line[len("define "):].rstrip(":")
                block = []
                i += 1
                while i < len(lines) and not lines[i].startswith(
                    ("define ", "test ", "sequence ", "curve ", "complex_func ")
                ):
                    block.append(self.normalize_line(lines[i]))
                    i += 1
                self.blueprints[header] = block
                print(f"\n=== BLUEPRINT: {header} ===")
                for step in block:
                    print(f"  {step}")
                continue

            if line.startswith("test "):
                header = line[len("test "):].rstrip(":")
                block = []
                i += 1
                while i < len(lines) and not lines[i].startswith(
                    ("define ", "test ", "sequence ", "curve ", "complex_func ")
                ):
                    block.append(self.normalize_line(lines[i]))
                    i += 1
                self._execute_test(header, block)
                continue

            i += 1

        if export_html and any(r.viz_payload for r in self.reports):
            export_html_visualizer(self.reports)
            print("\n[Visuals saved -> open 'zoom_view.html' in any browser to inspect interactive diagrams]")

    def _execute_test(self, header: str, block: List[str]) -> None:
        print(f"\n==========================================")
        print(f"RUNNING TEST: {header}")
        print(f"==========================================")

        goals = [float(m.group(1)) for ln in block if (m := re.search(r"goal\(([0-9.]+)\)", ln))]
        steps = [float(m.group(1)) for ln in block if (m := re.search(r"step\(([0-9.]+)\)", ln))]

        if m := re.match(r"limit\s+of\s+(\w+)\s+to\s+([+-]?[0-9.]+)", header):
            seq_name, target = m.group(1), float(m.group(2))
            report = run_limit_test(self.sequences[seq_name], target, goals or [0.1, 0.01, 0.001])

        elif m := re.match(r"cauchy\s+of\s+(\w+)", header):
            seq_name = m.group(1)
            report = run_cauchy_test(self.sequences[seq_name], goals or [0.1, 0.01, 0.001])

        elif m := re.match(r"continuity\s+of\s+(\w+)\s+at\s+([+-]?[0-9.]+)", header):
            curve_name, at_x = m.group(1), float(m.group(2))
            report = run_continuity_test(self.curves[curve_name], at_x, goals or [0.5, 0.1, 0.01])

        elif m := re.match(r"uniform_continuity\s+of\s+(\w+)\s+on\s+\[([+-]?[0-9.]+)\s*,\s*([+-]?[0-9.]+)\]", header):
            curve_name, a, b = m.group(1), float(m.group(2)), float(m.group(3))
            report = run_uniform_continuity_test(
                self.curves[curve_name], (a, b), goals or [0.2, 0.05, 0.01]
            )

        elif m := re.match(r"derivative\s+of\s+(\w+)\s+at\s+([+-]?[0-9.]+)", header):
            curve_name, at_x = m.group(1), float(m.group(2))
            report = run_derivative_test(
                self.curves[curve_name],
                at_x,
                steps or [0.1, 0.01, 0.0001],
                goals[-1] if goals else 0.001,
            )

        elif m := re.match(r"complex_continuity\s+of\s+(\w+)\s+at\s+(.+)", header):
            func_name, raw_z = m.group(1), m.group(2)
            report = run_complex_continuity_test(
                self.complex_funcs[func_name], parse_complex_literal(raw_z), goals or [0.5, 0.1, 0.01]
            )

        elif m := re.match(r"complex_derivative\s+of\s+(\w+)\s+at\s+(.+)", header):
            func_name, raw_z = m.group(1), m.group(2)
            report = run_complex_derivative_test(
                self.complex_funcs[func_name],
                parse_complex_literal(raw_z),
                steps or [0.1, 0.01, 0.0001],
                goals[-1] if goals else 0.001,
            )

        else:
            print(f"  [ERROR] Unrecognized test header: {header}")
            return

        self.reports.append(report)
        print(report.summary)
        for d in report.details:
            print(d)
        if report.ascii_art:
            print(report.ascii_art)


# =====================================================================
# 7. COMMAND-LINE RUNNER (.zoom FILES + INTERACTIVE REPL)
# =====================================================================
def run_repl() -> None:
    interpreter = ZoomInterpreter()
    print("ZOOM Interactive Mode — type Zoom lines, press Enter on an empty line to run, or type 'exit'.")
    buffer: List[str] = []

    while True:
        try:
            prompt = "zoom> " if not buffer else "  ... "
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if line.strip().lower() in ("exit", "quit"):
            break

        if line.strip() == "":
            if buffer:
                try:
                    interpreter.run("\n".join(buffer))
                except Exception as exc:
                    print(f"  [ERROR] {exc}")
                buffer.clear()
        else:
            buffer.append(line)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        zoom_file = Path(sys.argv[1])
        if not zoom_file.exists():
            print(f"File not found: {zoom_file}")
            sys.exit(1)
        ZoomInterpreter().run(zoom_file.read_text(encoding="utf-8"))
    else:
        run_repl()
