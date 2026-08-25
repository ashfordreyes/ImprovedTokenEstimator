#!/usr/bin/env python3
"""Check the notebook against the version of tcelibrary that Colab would install.

The notebook is a thin shell over the package now, which buys automatic updates and
costs a coupling: rename something in tce-library and this notebook breaks in Colab,
silently, for whoever opens it next. The setup cell tracks `main`, so there is no
release gate to catch it either.

This is that gate. It installs nothing and mocks nothing — point it at an installed
tcelibrary and it fails if the notebook calls something that is no longer there.

Usage:
    python tools/check_notebook.py [notebook.ipynb]
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

DEFAULT_NOTEBOOK = "improvedClaudeTokenEstimator.ipynb"
PACKAGE = "tcelibrary"

# Anthropic keys are recognisable on sight, which is what makes committing one easy.
SECRET_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")


class CheckFailed(Exception):
    pass


def load_notebook(path: Path) -> dict:
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CheckFailed(f"{path} does not exist") from None
    except json.JSONDecodeError as e:
        raise CheckFailed(f"{path} is not valid JSON: {e}") from None

    if notebook.get("nbformat") != 4:
        raise CheckFailed(f"expected nbformat 4, found {notebook.get('nbformat')!r}")
    if not isinstance(notebook.get("cells"), list):
        raise CheckFailed("notebook has no cell list")
    return notebook


def code_cells(notebook: dict) -> list[tuple[int, str]]:
    cells = []
    for i, cell in enumerate(notebook["cells"]):
        if cell.get("cell_type") == "code":
            cells.append((i, "".join(cell.get("source", []))))
    return cells


def strip_magics(source: str) -> str:
    """Drop IPython magics so the cell is parseable as plain Python.

    A `%%cell` magic makes the whole cell something other than Python, so the cell is
    dropped entirely rather than half-parsed.
    """
    if source.lstrip().startswith("%%"):
        return ""
    kept = []
    for line in source.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("!", "%", "?")):
            kept.append("pass")  # keep the line count honest for error messages
        else:
            kept.append(line)
    return "\n".join(kept)


def parse_cells(cells: list[tuple[int, str]]) -> list[tuple[int, ast.Module]]:
    trees = []
    errors = []
    for index, source in cells:
        cleaned = strip_magics(source)
        if not cleaned.strip():
            continue
        try:
            trees.append((index, ast.parse(cleaned)))
        except SyntaxError as e:
            errors.append(f"  cell {index}, line {e.lineno}: {e.msg}")
    if errors:
        raise CheckFailed("cells do not parse as Python:\n" + "\n".join(errors))
    return trees


def package_aliases(trees: list[tuple[int, ast.Module]]) -> set[str]:
    """Every name the notebook binds tcelibrary to (`import tcelibrary as tce`)."""
    aliases = set()
    for _, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == PACKAGE:
                        aliases.add(alias.asname or alias.name)
    return aliases


def referenced_attributes(
    trees: list[tuple[int, ast.Module]], aliases: set[str]
) -> dict[str, list[int]]:
    """Map each `tce.<name>` the notebook uses to the cells that use it."""
    found: dict[str, list[int]] = {}
    for index, tree in trees:
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases
            ):
                found.setdefault(node.attr, [])
                if index not in found[node.attr]:
                    found[node.attr].append(index)
    return found


def check_drift(trees: list[tuple[int, ast.Module]]) -> int:
    aliases = package_aliases(trees)
    if not aliases:
        raise CheckFailed(
            f"the notebook never imports {PACKAGE} — the setup cell is supposed to, "
            f"and every later cell depends on it"
        )

    try:
        package = __import__(PACKAGE)
    except ImportError as e:
        raise CheckFailed(f"could not import {PACKAGE}: {e}") from None

    referenced = referenced_attributes(trees, aliases)
    if not referenced:
        raise CheckFailed(f"the notebook imports {PACKAGE} but never calls into it")

    missing = {
        name: cells for name, cells in sorted(referenced.items()) if not hasattr(package, name)
    }
    if missing:
        detail = "\n".join(
            f"  {PACKAGE}.{name}  (used in cell{'s' if len(c) > 1 else ''} "
            f"{', '.join(str(i) for i in c)})"
            for name, c in missing.items()
        )
        raise CheckFailed(
            f"the notebook calls names that {PACKAGE} "
            f"{getattr(package, '__version__', '?')} no longer provides:\n{detail}\n"
            f"Either restore them in tce-library or update the notebook."
        )

    return len(referenced)


def check_secrets(notebook: dict) -> None:
    """Look for a leaked API key in cell source and in committed outputs alike."""
    hits = []
    for i, cell in enumerate(notebook["cells"]):
        blobs = ["".join(cell.get("source", []))]
        for output in cell.get("outputs") or []:
            blobs.append("".join(output.get("text") or []))
            for value in (output.get("data") or {}).values():
                blobs.append("".join(value) if isinstance(value, list) else str(value))
        for blob in blobs:
            if SECRET_PATTERN.search(blob):
                hits.append(i)
                break
    if hits:
        raise CheckFailed(
            "what looks like an Anthropic API key appears in "
            f"cell(s) {', '.join(str(i) for i in hits)}. Clear it and rotate the key."
        )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", nargs="?", default=DEFAULT_NOTEBOOK)
    parser.add_argument(
        "--skip-drift",
        action="store_true",
        help=(
            f"Run only the checks that need no dependency — cells parse, no leaked key. "
            f"For when {PACKAGE} cannot be installed at all, not for when it is installed "
            f"and the notebook disagrees with it."
        ),
    )
    args = parser.parse_args(argv[1:])
    path = Path(args.notebook)

    try:
        notebook = load_notebook(path)
        cells = code_cells(notebook)
        trees = parse_cells(cells)
        checked = None if args.skip_drift else check_drift(trees)
        check_secrets(notebook)
    except CheckFailed as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    print(f"OK: {path.name} — {len(cells)} code cells parse")
    if checked is None:
        print(f"SKIPPED: drift check ({PACKAGE} not installed)")
    else:
        version = getattr(__import__(PACKAGE), "__version__", "?")
        print(f"OK: {checked} {PACKAGE} names resolve against {PACKAGE} {version}")
    print("OK: no API key found in sources or outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
