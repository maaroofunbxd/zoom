#!/usr/bin/env python3
"""
ZOOM: An Everyday, Symbol-Free Programming Language for Real Analysis
====================================================================
Uses explicit everyday words:
  - `goal`   (output tolerance)
  - `buffer` (input leeway)
  - `cutoff` (step threshold)
  - `step`   (explicit distance left/right of x for slope checks)

Usage:
  1. Run a .zoom file:      python3 zoom_lang.py my_notes.zoom
  2. Interactive prompt:    python3 zoom_lang.py
"""

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple


# =====================================================================
# 1. SAFE MATH EVALUATOR
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
}


def make_sequence(expr: str) -> Callable[[int], float]:
    code = compile(expr, "<sequence>", "eval")
    return lambda n: float(eval(code, {"__builtins__": {}}, {**SAFE_ENV, "n": n}))


def make_curve(expr: str) -> Callable[[float], float]:
    code = compile(expr, "<curve>", "eval")
    return lambda x: float(eval(code, {"__builtins__": {}}, {**SAFE_ENV, "x": x}))


# =====================================================================
# 2. EVERYDAY ANALYSIS ENGINE (Goal, Buffer, Cutoff, Step)
# =====================================================================
@dataclass
class TestReport:
    passed: bool
    title: str
    summary: str
    details: List[str]


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

    for g in goals:
        cutoff = None
        for start in range(1, max_n - hold_window):
            if all(abs(f(k) - target) < g for k in range(start, start + hold_window)):
                cutoff = start
                break

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

    summary = (
        f"PASS: '{seq_expr}' reaches target {target} within every tested goal."
        if all_passed
        else f"BREAKS: '{seq_expr}' fails to stay within tight goals around {target}."
    )
    return TestReport(all_passed, f"Limit Check: {seq_expr} -> {target}", summary, details)


def run_cauchy_test(
    seq_expr: str,
    goals: List[float],
    max_n: int = 2000,
    lookahead: int = 80,
) -> TestReport:
    f = make_sequence(seq_expr)
    details = []
    all_passed = True

    for g in goals:
        cutoff = None
        for start in range(1, max_n - lookahead):
            window = [f(k) for k in range(start, start + lookahead)]
            if max(window) - min(window) < g:
                cutoff = start
                break

        if cutoff is not None:
            details.append(
                f"  [OK]   goal({g}) -> cutoff at step {cutoff} "
                f"(all remaining steps stay within {g} of each other)"
            )
        else:
            all_passed = False
            details.append(
                f"  [FAIL] goal({g}) -> steps never stop drifting apart."
            )

    summary = (
        f"PASS: '{seq_expr}' is Cauchy (steps huddle within any goal without needing a target)."
        if all_passed
        else f"BREAKS: '{seq_expr}' is NOT Cauchy."
    )
    return TestReport(all_passed, f"Cauchy Check: {seq_expr}", summary, details)


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

    summary = (
        f"PASS: '{curve_expr}' is continuous at x = {at_x}."
        if all_passed
        else f"BREAKS: '{curve_expr}' is NOT continuous at x = {at_x}."
    )
    return TestReport(all_passed, f"Continuity Check: {curve_expr} at x={at_x}", summary, details)


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

    summary = (
        f"PASS: '{curve_expr}' is uniformly continuous on [{a}, {b}]."
        if all_passed
        else f"BREAKS: '{curve_expr}' is NOT uniformly continuous on [{a}, {b}]."
    )
    return TestReport(
        all_passed, f"Uniform Continuity Check: {curve_expr} on [{a}, {b}]", summary, details
    )


def run_derivative_test(
    curve_expr: str,
    at_x: float,
    steps: List[float],
    goal: float,
) -> TestReport:
    """
    Explicit slope check:
    For each explicit `step` distance, measure the left slope across [x - step, x]
    and the right slope across [x, x + step]. At the smallest step, the gap between
    left_slope and right_slope must be strictly less than `goal`.
    """
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

    passed = final_gap < goal
    summary = (
        f"PASS: At step({steps[-1]}), left and right slopes agree within goal({goal}) -> slope ≈ {est_slope:.6g}."
        if passed
        else f"BREAKS: At step({steps[-1]}), slope gap ({final_gap:.6g}) exceeds goal({goal}) -> no single tangent line at x = {at_x}."
    )
    return TestReport(passed, f"Derivative Check: {curve_expr} at x={at_x}", summary, details)


# =====================================================================
# 3. DUAL-SYNTAX PARSER & INTERPRETER
# =====================================================================
class ZoomInterpreter:
    def __init__(self):
        self.blueprints: Dict[str, List[str]] = {}
        self.sequences: Dict[str, str] = {}
        self.curves: Dict[str, str] = {}

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

    def run(self, program: str) -> None:
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

            if line.startswith("define "):
                header = line[len("define "):].rstrip(":")
                block = []
                i += 1
                while i < len(lines) and not lines[i].startswith(("define ", "test ", "sequence ", "curve ")):
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
                while i < len(lines) and not lines[i].startswith(("define ", "test ", "sequence ", "curve ")):
                    block.append(self.normalize_line(lines[i]))
                    i += 1
                self._execute_test(header, block)
                continue

            i += 1

    def _execute_test(self, header: str, block: List[str]) -> None:
        print(f"\n==========================================")
        print(f"RUNNING TEST: {header}")
        print(f"==========================================")

        goals = [float(m.group(1)) for ln in block if (m := re.search(r"goal\(([0-9.]+)\)", ln))]
        steps = [float(m.group(1)) for ln in block if (m := re.search(r"step\(([0-9.]+)\)", ln))]

        if m := re.match(r"limit\s+of\s+(\w+)\s+to\s+([+-]?[0-9.]+)", header):
            seq_name, target = m.group(1), float(m.group(2))
            if seq_name not in self.sequences:
                print(f"  [ERROR] Unknown sequence '{seq_name}'. Define it first with: sequence {seq_name} = ...")
                return
            report = run_limit_test(self.sequences[seq_name], target, goals or [0.1, 0.01, 0.001])

        elif m := re.match(r"cauchy\s+of\s+(\w+)", header):
            seq_name = m.group(1)
            if seq_name not in self.sequences:
                print(f"  [ERROR] Unknown sequence '{seq_name}'.")
                return
            report = run_cauchy_test(self.sequences[seq_name], goals or [0.1, 0.01, 0.001])

        elif m := re.match(r"continuity\s+of\s+(\w+)\s+at\s+([+-]?[0-9.]+)", header):
            curve_name, at_x = m.group(1), float(m.group(2))
            if curve_name not in self.curves:
                print(f"  [ERROR] Unknown curve '{curve_name}'. Define it first with: curve {curve_name} = ...")
                return
            report = run_continuity_test(self.curves[curve_name], at_x, goals or [0.5, 0.1, 0.01])

        elif m := re.match(r"uniform_continuity\s+of\s+(\w+)\s+on\s+\[([+-]?[0-9.]+)\s*,\s*([+-]?[0-9.]+)\]", header):
            curve_name, a, b = m.group(1), float(m.group(2)), float(m.group(3))
            if curve_name not in self.curves:
                print(f"  [ERROR] Unknown curve '{curve_name}'.")
                return
            report = run_uniform_continuity_test(
                self.curves[curve_name], (a, b), goals or [0.2, 0.05, 0.01]
            )

        elif m := re.match(r"derivative\s+of\s+(\w+)\s+at\s+([+-]?[0-9.]+)", header):
            curve_name, at_x = m.group(1), float(m.group(2))
            if curve_name not in self.curves:
                print(f"  [ERROR] Unknown curve '{curve_name}'.")
                return
            report = run_derivative_test(
                self.curves[curve_name],
                at_x,
                steps or [0.1, 0.01, 0.0001],
                goals[-1] if goals else 0.001,
            )

        else:
            print(f"  [ERROR] Unrecognized test header: {header}")
            return

        print(report.summary)
        for d in report.details:
            print(d)


# =====================================================================
# 4. COMMAND-LINE RUNNER (.zoom FILES + INTERACTIVE REPL)
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
