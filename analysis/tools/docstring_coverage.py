#!/usr/bin/env python3
"""Measure docstring coverage the way a PR reviewer scopes it: by the diff.

    python3 analysis/tools/docstring_coverage.py              # vs origin/main
    python3 analysis/tools/docstring_coverage.py --base REF
    python3 analysis/tools/docstring_coverage.py --missing    # list what is bare

Whole-file coverage is the wrong number for a pull request: it counts code the
branch never touched, so it moves when you edit an unrelated file and it cannot
tell you what THIS change left undocumented. The review bots that gate on
coverage scope it to the functions a diff touches, and so does this.

A function counts as touched when any line the diff added or changed falls
inside it — including its signature. Nested functions and methods count
separately, because each is a thing a reader has to understand on its own.

Standard library only: it runs in CI next to kpi_snapshot.py, before the
pipeline's dependencies are installed.
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(base: str, head: str, path: str) -> set[int]:
    """Line numbers in `head`'s version of `path` that the diff added or changed."""
    out = subprocess.run(
        ["git", "diff", "--unified=0", f"{base}..{head}", "--", path],
        cwd=ROOT, capture_output=True, text=True).stdout
    lines: set[int] = set()
    cursor = 0
    for line in out.splitlines():
        m = HUNK.match(line)
        if m:
            cursor = int(m.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            lines.add(cursor)
            cursor += 1
    return lines


def functions(tree: ast.AST):
    """Every def and class in the file, innermost ones included."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node


def span(node) -> range:
    """The line range a definition occupies, end included.

    Used to decide whether any changed line falls inside the function; the
    signature counts, so renaming a parameter marks it touched.
    """
    return range(node.lineno, (node.end_lineno or node.lineno) + 1)


def scan(base: str, head: str, paths: list[str], scope_to_diff: bool):
    rows = []
    for path in paths:
        text = (ROOT / path).read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        touched = changed_lines(base, head, path) if scope_to_diff else None
        for node in functions(tree):
            if touched is not None and not (touched & set(span(node))):
                continue
            rows.append({
                "file": path,
                "name": node.name,
                "line": node.lineno,
                "kind": type(node).__name__.replace("Def", "").lower(),
                "documented": ast.get_docstring(node) is not None,
            })
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--missing", action="store_true",
                    help="list every undocumented function instead of the summary")
    ap.add_argument("--whole-file", action="store_true",
                    help="count every function in a changed file, not just touched ones")
    ap.add_argument("--threshold", type=float, default=0.0,
                    help="exit non-zero below this percentage")
    args = ap.parse_args(argv)

    paths = subprocess.run(
        ["git", "diff", "--name-only", f"{args.base}..{args.head}", "--", "*.py"],
        cwd=ROOT, capture_output=True, text=True).stdout.split()
    paths = [p for p in paths if (ROOT / p).exists()]

    rows = scan(args.base, args.head, paths, scope_to_diff=not args.whole_file)
    if not rows:
        print("no functions in scope")
        return 0

    done = sum(r["documented"] for r in rows)
    pct = done / len(rows) * 100

    if args.missing:
        for r in sorted((r for r in rows if not r["documented"]),
                        key=lambda r: (r["file"], r["line"])):
            print(f'{r["file"]}:{r["line"]}  {r["kind"]} {r["name"]}')
        print()

    by_file: dict[str, list] = {}
    for r in rows:
        by_file.setdefault(r["file"], []).append(r)
    for path, rs in sorted(by_file.items(),
                           key=lambda kv: sum(not r["documented"] for r in kv[1]),
                           reverse=True):
        bare = sum(not r["documented"] for r in rs)
        if bare:
            print(f"  {bare:3d} bare of {len(rs):3d}   {path}")

    print(f"\n{done}/{len(rows)} documented across {len(by_file)} files — "
          f"{pct:.2f}%")
    if args.threshold and pct < args.threshold:
        print(f"below the {args.threshold:.0f}% threshold")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
