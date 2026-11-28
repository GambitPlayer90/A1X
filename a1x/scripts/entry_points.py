#!/usr/bin/env python3
"""Inventory Solidity mutation entry points and externally callable readers.

An entry point is a non-view, non-pure `external` or `public` function, plus
`receive` and `fallback`. Each function header is read as a whole, from
`function` (or `receive` / `fallback`) to its opening `{`, after comments and
string literals are blanked. Line breaks therefore cannot hide an entry point:
line-oriented grep misses headers that formatters wrap, such as `external` on
its own line (`forge fmt`'s default `multiline_func_header = "attributes_first"`)
or one-parameter-per-line headers whose `function` keyword sits far above the
`) external` line. Pre-0.5 code is handled too: a missing visibility counts as
`public`, `constant` counts as `view`, `function () ... {` is the fallback, and a
function named exactly like its contract is a constructor (a misspelled one is
still listed, since it is callable).

Output (stdout), one line per entry point, whitespace collapsed:
    path:line: [abstract|library] Container.name(params) attributes
followed by a `# N entry point(s) in M of K .sol file(s)` summary line. An
ordinary function that is merely named `receive` or `fallback` ends with a
`// ordinary function named ...` note, since it is not the special function.
Unreadable files and directories are reported on stderr, skipped, and counted
in the summary.

Skipped as mutation entry points: interface and bodiless declarations (ending in `;`),
internal/private functions, view/pure functions, and free functions. Public/external
view/pure functions and generated public state-variable getters are emitted separately
as read surfaces so valuation, preview, oracle, and transient-state consumers cannot
silently disappear from coverage. Every
`.sol` file remains in the machine-readable inventory, including interfaces and mocks, so
full-scope file accounting cannot silently omit a directory. `[abstract]` marks functions defined in abstract
contracts; they are entry points of every concrete contract that inherits them,
unless a contract lower in the hierarchy overrides them. `[library]` marks
library functions, which are reached only through the contracts that call them.

Usage:
    python3 entry_points.py src
    python3 entry_points.py src --root src --json-output x-ray/entry-points.json
    python3 entry_points.py --scope-json bounty/scope.json --root .
    python3 entry_points.py contracts other/contracts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

IDENT = r"[A-Za-z_$][A-Za-z0-9_$]*"
# Keyword boundaries. `\b` would treat `$` as a boundary, but `$` is part of Solidity identifiers.
B = r"(?<![A-Za-z0-9_$])"
E = r"(?![A-Za-z0-9_$])"
CONTAINER_RE = re.compile(B + r"(abstract\s+)?(contract|interface|library)\s+(" + IDENT + r")")
FUNCTION_RE = re.compile(B + r"function\s+(" + IDENT + r")\s*\(")
SPECIAL_RE = re.compile(B + r"(receive|fallback)\s*\(")
LEGACY_FALLBACK_RE = re.compile(B + r"function\s*\(")
VISIBILITY_RE = re.compile(B + r"(external|public|internal|private)" + E)
VIEW_OR_PURE_RE = re.compile(B + r"(view|pure|constant)" + E)
PUBLIC_RE = re.compile(B + r"public" + E)
GETTER_SKIP_TOKENS = {"constant", "immutable", "override", "transient"}


def blank_comments_and_strings(src: str, strings: bool = True) -> str:
    """Replace comments (and, if `strings`, string literal contents) with spaces, keeping offsets."""
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
        elif ch == "/" and nxt == "*":
            end = src.find("*/", i + 2)
            end = n if end == -1 else end + 2
            for j in range(i, end):
                if src[j] != "\n":
                    out[j] = " "
            i = end
        elif ch in "\"'":
            j = i + 1
            while j < n and src[j] != ch and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            if strings:
                for k in range(i + 1, min(j, n)):
                    if src[k] != "\n":
                        out[k] = " "
            i = j + 1
        else:
            i += 1
    return "".join(out)


def matching_close(text: str, open_idx: int, open_ch: str, close_ch: str) -> int:
    """Index of the bracket closing the one at open_idx, or -1 if unbalanced."""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return -1


def header_end(text: str, start: int) -> int:
    """Index of the first `{` or `;` at parenthesis depth 0 from start, or -1."""
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and ch in "{;":
            return i
    return -1


def previous_token(text: str, pos: int) -> str:
    """The identifier or `.` that ends right before pos, skipping whitespace."""
    i = pos - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    if i >= 0 and text[i] == ".":
        return "."
    j = i
    while j >= 0 and (text[j].isalnum() or text[j] in "_$"):
        j -= 1
    return text[j + 1 : i + 1]


def strip_parenthesized(text: str) -> str:
    """Drop every parenthesized group (returns lists, modifier arguments, override lists)."""
    out, depth = [], 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def containers(clean: str) -> list[tuple[int, int, str, str]]:
    """(body_open, body_close, kind, name) for every contract/interface/library."""
    found = []
    for m in CONTAINER_RE.finditer(clean):
        brace = header_end(clean, m.end())
        if brace == -1 or clean[brace] != "{":
            continue
        close = matching_close(clean, brace, "{", "}")
        if close == -1:
            continue
        kind = "abstract" if m.group(1) else m.group(2)
        found.append((brace, close, kind, m.group(3)))
    return found


def _top_level_statements(text: str, body_open: int, body_close: int) -> list[tuple[int, int]]:
    """Return semicolon-terminated statements at contract-body depth zero."""
    statements: list[tuple[int, int]] = []
    start = body_open + 1
    depth = 0
    for index in range(body_open + 1, body_close):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(depth - 1, 0)
            if depth == 0:
                start = index + 1
        elif char == ";" and depth == 0:
            statements.append((start, index))
            start = index + 1
    return statements


def _public_getters(
    clean: str,
    display: str,
    scopes: list[tuple[int, int, str, str]],
) -> list[tuple[int, str, str, str]]:
    getters: list[tuple[int, str, str, str]] = []
    excluded = ("event ", "error ", "using ", "type ", "struct ", "enum ", "modifier ", "function ")
    for body_open, body_close, kind, contract_name in scopes:
        if kind == "interface":
            continue
        for start, end in _top_level_statements(clean, body_open, body_close):
            raw_statement = clean[start:end]
            leading = len(raw_statement) - len(raw_statement.lstrip())
            statement = raw_statement.strip()
            if not statement or statement.startswith(excluded):
                continue
            public = PUBLIC_RE.search(statement)
            if not public:
                continue
            tail = statement[public.end() :]
            tail = re.sub(B + r"override\s*(?:\([^)]*\))?", " ", tail)
            name = ""
            for token in re.findall(IDENT, tail):
                if token not in GETTER_SKIP_TOKENS:
                    name = token
                    break
            if not name:
                continue
            declaration = re.sub(r"\s+", " ", display[start:end]).strip()
            tag = f"[{kind}] " if kind in ("abstract", "library") else ""
            text = f"{tag}{contract_name}.{name} [generated public getter] // {declaration}"
            declaration_start = start + leading
            getters.append((clean.count("\n", 0, declaration_start) + 1, text, "generated-getter", "view"))
    return getters


def callable_surfaces(path: str) -> tuple[list[tuple[int, str]], list[tuple[int, str, str, str]]]:
    with open(path, encoding="utf-8", errors="replace") as f:
        source = f.read()
    clean = blank_comments_and_strings(source)  # parsed: no comments, no string contents
    display = blank_comments_and_strings(source, strings=False)  # printed: strings kept
    scopes = containers(clean)
    results: list[tuple[int, str]] = []
    readers: list[tuple[int, str, str, str]] = []
    for regex in (FUNCTION_RE, SPECIAL_RE, LEGACY_FALLBACK_RE):
        for m in regex.finditer(clean):
            start = m.start()
            if regex is SPECIAL_RE and previous_token(clean, start) in (".", "function"):
                continue  # a member call (`x.receive(`), or an ordinary function named receive/fallback
            enclosing = [s for s in scopes if s[0] < start < s[1]]
            if not enclosing:
                continue  # free function: cannot be external or public
            body_open, _, kind, name = max(enclosing, key=lambda s: s[0])
            between = clean[body_open + 1 : start]
            if between.count("{") != between.count("}"):
                continue  # not declared at contract level
            if between.count("(") != between.count(")"):
                continue  # function type inside a parameter list or mapping
            params_open = m.end() - 1
            params_close = matching_close(clean, params_open, "(", ")")
            if params_close == -1:
                continue
            end = header_end(clean, params_close + 1)
            if end == -1:
                continue
            bodiless = clean[end] == ";"
            attributes = strip_parenthesized(clean[params_close + 1 : end])
            visibility = VISIBILITY_RE.search(attributes)
            if visibility and visibility.group(1) not in ("external", "public"):
                continue  # no visibility only compiles before 0.5, where it means public
            mutability_match = VIEW_OR_PURE_RE.search(attributes)
            if bodiless and not mutability_match:
                continue  # mutating interface/abstract declaration is not an executable entry point
            if kind == "interface" and not mutability_match:
                continue
            if regex is FUNCTION_RE and m.group(1) == name:
                continue  # pre-0.5 constructor
            if regex is LEGACY_FALLBACK_RE:
                header = "fallback" + display[params_open:end]
            else:
                header = display[m.start(1) : end]
            header = re.sub(r"\s+", " ", header).strip()
            header = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", header))
            header = re.sub(r"^([^\s(]+)\s+\(", r"\1(", header)  # `receive ()` -> `receive()`
            if regex is FUNCTION_RE and m.group(1) in ("receive", "fallback"):
                header += f" // ordinary function named {m.group(1)}, not the special {m.group(1)} function"
            tag = f"[{kind}] " if kind in ("abstract", "interface", "library") else ""
            line = clean.count("\n", 0, start) + 1
            rendered = f"{tag}{name}.{header}"
            if mutability_match:
                mutability = "view" if mutability_match.group(1) == "constant" else mutability_match.group(1)
                readers.append((line, rendered, "function", mutability))
            else:
                results.append((line, rendered))
    readers.extend(_public_getters(clean, display, scopes))
    return sorted(results), sorted(readers)


def entry_points(path: str) -> list[tuple[int, str]]:
    return callable_surfaces(path)[0]


def read_surfaces(path: str) -> list[tuple[int, str, str, str]]:
    return callable_surfaces(path)[1]


def solidity_files(paths: list[str], problems: list[str]) -> list[str]:
    files = []
    for root_path in paths:
        if os.path.isfile(root_path):
            files.append(root_path)
            continue
        on_error = lambda e: problems.append(f"{e.filename}: {e.strerror or e}")  # noqa: E731
        for root, dirs, names in os.walk(root_path, onerror=on_error):
            dirs.sort()
            files.extend(os.path.join(root, n) for n in sorted(names) if n.endswith(".sol"))
    normalized = [os.path.normpath(f).replace(os.sep, "/") for f in files]
    return list(dict.fromkeys(normalized))  # drop duplicates from overlapping arguments


def scope_files(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list) or not files:
        raise ValueError("scope JSON must contain a non-empty files array")
    normalized = [str(value).strip().replace("\\", "/") for value in files]
    if any(
        not value
        or Path(value).is_absolute()
        or ".." in Path(value).parts
        or not value.endswith(".sol")
        for value in normalized
    ):
        raise ValueError("scope files must be safe repository-relative .sol paths")
    if len(normalized) != len(set(normalized)):
        raise ValueError("scope files contain duplicates")
    return normalized


def display_path(path: str, root: Path | None) -> str:
    if root is None:
        return path
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"source file escapes --root: {path}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="List Solidity entry points for the x-ray skill.")
    parser.add_argument("paths", nargs="*", help="source directories or .sol files (e.g. src)")
    parser.add_argument(
        "--scope-json",
        type=Path,
        help="instead scan exactly the repository-relative files in a JSON files array",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="resolve scope paths from this root and emit stable root-relative paths",
    )
    parser.add_argument(
        "--json-output",
        help="also write the complete machine-readable scan to this path",
    )
    args = parser.parse_args()
    if args.scope_json and args.paths:
        parser.error("paths and --scope-json are mutually exclusive")
    if not args.scope_json and not args.paths:
        parser.error("provide source paths or --scope-json")
    root = args.root.expanduser().resolve() if args.root else None
    try:
        selected = scope_files(args.scope_json) if args.scope_json else list(args.paths)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot load scope: {exc}", file=sys.stderr)
        return 2
    input_paths = [
        str((root or Path.cwd()) / path)
        if args.scope_json or (root is not None and not Path(path).is_absolute())
        else path
        for path in selected
    ]
    missing = [p for p in input_paths if not os.path.exists(p)]
    if missing:
        print(f"error: path not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    problems: list[str] = []
    files = solidity_files(input_paths, problems)
    try:
        displayed_files = [display_path(path, root) for path in files]
        scope_inputs = (
            list(selected)
            if args.scope_json
            else [display_path(path, root) for path in input_paths]
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    total, files_with_entries = 0, 0
    total_readers, files_with_readers = 0, 0
    records: list[dict[str, object]] = []
    reader_records: list[dict[str, object]] = []
    for path, displayed in zip(files, displayed_files, strict=True):
        try:
            found, found_readers = callable_surfaces(path)
        except OSError as e:
            problems.append(f"{path}: {e.strerror or e}")
            continue
        if found:
            files_with_entries += 1
        if found_readers:
            files_with_readers += 1
        for line, text in found:
            print(f"{displayed}:{line}: {text}")
            records.append(
                {
                    "id": f"{displayed}:{line}:{text}",
                    "path": displayed,
                    "line": line,
                    "declaration": text,
                }
            )
        total += len(found)
        for line, text, surface_kind, mutability in found_readers:
            print(f"{displayed}:{line}: [read] {text}")
            reader_records.append(
                {
                    "id": f"{displayed}:{line}:{text}",
                    "path": displayed,
                    "line": line,
                    "declaration": text,
                    "surface_kind": surface_kind,
                    "mutability": mutability,
                }
            )
        total_readers += len(found_readers)
    for problem in problems:
        print(f"warning: skipped {problem}", file=sys.stderr)
    if not files:
        print("warning: no .sol files to scan", file=sys.stderr)
    summary = (
        f"# {total} entry point(s) in {files_with_entries} of {len(files)} .sol file(s); "
        f"{total_readers} read surface(s) in {files_with_readers} file(s)"
    )
    if problems:
        summary += f"; {len(problems)} unreadable path(s) skipped, see stderr"
    print(summary)
    if args.json_output:
        destination = Path(args.json_output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "path_basis": "root-relative" if root else "invocation-relative",
                    "scope_mode": "manifest" if args.scope_json else "paths",
                    "scope_inputs": scope_inputs,
                    "files": displayed_files,
                    "entry_points": records,
                    "read_surfaces": reader_records,
                    "files_with_entry_points": files_with_entries,
                    "files_with_read_surfaces": files_with_readers,
                    "problems": problems,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
