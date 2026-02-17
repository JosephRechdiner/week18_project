"""
project_overview.py
Utility -> universal structure + full content dump script

Default behavior:
- Includes only git-tracked files (git ls-files)
- Writes output to project_dump.md
- Skips selected folders + ignore files (see EXCLUDED_* below)

Optional:
- Include ignored + untracked files listed by git (can be huge!)
"""
from __future__ import annotations

import argparse
import os
from collections import defaultdict
from pathlib import Path
import subprocess
from typing import Dict, Any, List, TextIO, Tuple

# -----------------------------
# EXCLUDES (customize here)
# -----------------------------
EXCLUDED_DIR_NAMES = {
    "venv",
    ".venv",   # common; remove if not desired
    "general",
    "arc",
    "ignore",
    "data"
}

EXCLUDED_FILE_NAMES = {
    ".gitignore",
    ".dockerignore",
}


def is_excluded_path(file_path: str) -> bool:
    """
    Returns True if file_path should be excluded based on directory/file name rules.
    - Excludes if any path segment matches EXCLUDED_DIR_NAMES
    - Excludes if the file name matches EXCLUDED_FILE_NAMES
    """
    p = Path(file_path)

    # Exclude specific filenames anywhere
    if p.name in EXCLUDED_FILE_NAMES:
        return True

    # Exclude any file inside excluded directories (at any depth)
    if any(part in EXCLUDED_DIR_NAMES for part in p.parts):
        return True

    return False


# -----------------------------
# GIT FILE LISTING
# -----------------------------
def get_git_files(include_ignored: bool) -> List[str]:
    """
    Returns file paths relative to repo root.
    include_ignored=False:
      - tracked files only
    include_ignored=True:
      - tracked + untracked + ignored (gitignored)

    Then filters out excluded paths (venv/general/arc/ignore dirs + .gitignore/.dockerignore files).
    """
    if include_ignored:
        cmd = ["git", "ls-files", "--cached", "--others", "--ignored", "--exclude-standard"]
    else:
        cmd = ["git", "ls-files"]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "Git command failed. Are you in a git repository?\n"
            f"Command: {' '.join(cmd)}\n"
            f"Error: {result.stderr.strip()}"
        )

    files = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    # Apply exclusions
    files = [fp for fp in files if not is_excluded_path(fp)]
    return files


# -----------------------------
# TREE BUILDING
# -----------------------------
Tree = Dict[str, Any]  # nested dict; leaf files are None


def add_to_tree(tree: Tree, file_path: str) -> None:
    parts = Path(file_path).parts
    current = tree
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = None


def sum_files(node: Tree) -> int:
    count = 0
    for v in node.values():
        if isinstance(v, dict):
            count += sum_files(v)
        else:
            count += 1
    return count


def count_folders(node: Tree) -> int:
    """
    Counts folders recursively (each dict node is a folder).
    """
    total = 0
    for v in node.values():
        if isinstance(v, dict):
            total += 1
            total += count_folders(v)
    return total


def print_tree(node: Tree, out: TextIO, prefix: str = "") -> None:
    for key, value in sorted(node.items(), key=lambda kv: kv[0].lower()):
        if isinstance(value, dict):
            subfolders = sum(1 for v in value.values() if isinstance(v, dict))
            files = sum(1 for v in value.values() if v is None)
            total_files = sum_files(value)
            out.write(
                f"{prefix}{key}/ [subfolders: {subfolders}, files: {files}, total files: {total_files}]\n"
            )
            print_tree(value, out, prefix + "    ")
        else:
            out.write(f"{prefix}{key}\n")


# -----------------------------
# CONTENT DUMP HELPERS
# -----------------------------
def is_probably_binary(path: str, sniff_bytes: int = 2048) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(sniff_bytes)
        if b"\x00" in chunk:
            return True
        # If it decodes as UTF-8, assume text
        try:
            chunk.decode("utf-8")
            return False
        except UnicodeDecodeError:
            return True
    except Exception:
        # If we can't read it, treat as "not text dumpable"
        return True


def language_from_extension(ext: str) -> str:
    ext = ext.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "jsx",
        ".tsx": "tsx",
        ".json": "json",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".toml": "toml",
        ".md": "markdown",
        ".html": "html",
        ".css": "css",
        ".sh": "bash",
        ".bat": "bat",
        ".ps1": "powershell",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".rs": "rust",
        ".go": "go",
        ".sql": "sql",
        ".xml": "xml",
        ".ini": "ini",
        ".env": "",
    }.get(ext, "")


def safe_read_text(path: str, max_bytes: int) -> Tuple[str | None, str | None]:
    """
    Returns (text, error). If too large/binary/unreadable, text is None and error explains why.
    """
    try:
        size = os.path.getsize(path)
        if size > max_bytes:
            return None, f"SKIPPED (too large: {size} bytes > limit {max_bytes} bytes)"
        if is_probably_binary(path):
            return None, "SKIPPED (binary or non-UTF8 text)"
        with open(path, "r", encoding="utf-8", errors="strict") as f:
            return f.read(), None
    except UnicodeDecodeError:
        return None, "SKIPPED (not UTF-8 decodable)"
    except Exception as e:
        return None, f"SKIPPED (read error: {e})"


# -----------------------------
# MAIN
# -----------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Project overview + full code dump to a single file.")
    parser.add_argument("--out", default="project_dump.md", help="Output file path (default: project_dump.md)")
    parser.add_argument(
        "--include-ignored",
        action="store_true",
        help="Include gitignored + untracked files (can be huge). Default is tracked files only.",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=1_000_000,
        help="Max file size to include in content dump (default: 1,000,000 bytes).",
    )
    args = parser.parse_args()

    all_files = get_git_files(include_ignored=args.include_ignored)

    tree: Tree = {}
    file_types = defaultdict(int)
    file_lines = defaultdict(int)

    # Build tree + stats
    for file_path in all_files:
        add_to_tree(tree, file_path)
        ext = Path(file_path).suffix or "no_ext"
        file_types[ext] += 1

        # Count lines only for readable utf-8 text files within size limit
        text, err = safe_read_text(file_path, max_bytes=args.max_bytes)
        if text is not None:
            file_lines[ext] += text.count("\n") + (1 if text else 0)

    total_files = len(all_files)
    total_folders = count_folders(tree)

    out_path = Path(args.out)
    with open(out_path, "w", encoding="utf-8") as out:
        out.write("# PROJECT TREE\n\n")
        out.write("```\n")
        print_tree(tree, out)
        out.write("```\n\n")

        out.write("# PROJECT STATS\n\n")
        out.write(f"- Total folders: {total_folders}\n")
        out.write(f"- Total files  : {total_files}\n\n")

        out.write("## File types\n\n")
        out.write("| Extension | Files | Lines (utf-8 text only) |\n")
        out.write("|---|---:|---:|\n")
        for ext, count in sorted(file_types.items(), key=lambda kv: kv[0].lower()):
            out.write(f"| `{ext}` | {count} | {file_lines[ext]} |\n")
        out.write("\n---\n\n")

        out.write("# FILE CONTENTS\n\n")
        for file_path in all_files:
            out.write(f"## {file_path}\n\n")
            text, err = safe_read_text(file_path, max_bytes=args.max_bytes)
            if text is None:
                out.write(f"**{err}**\n\n")
                continue
            lang = language_from_extension(Path(file_path).suffix)
            out.write(f"```{lang}\n")
            out.write(text)
            if not text.endswith("\n"):
                out.write("\n")
            out.write("```\n\n")

    print(f"Wrote project dump to: {out_path.resolve()}")


if __name__ == "__main__":
    main()