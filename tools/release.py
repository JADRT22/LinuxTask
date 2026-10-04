#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LinuxTask Release Automation Script
Automates version bumping, changelog updates, and git tagging.
"""

import os
import re
import sys
import argparse
import subprocess
from datetime import datetime

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY_PATH = os.path.join(PROJECT_ROOT, 'src', 'main.py')
PYPROJECT_PATH = os.path.join(PROJECT_ROOT, 'tools', 'appimage', 'pyproject.toml')
# Single canonical changelog at the repository root (docs/CHANGELOG.md was
# merged into it and removed).
CHANGELOG_PATH = os.path.join(PROJECT_ROOT, 'CHANGELOG.md')

# Single source of truth for the version: the APP_VERSION constant in
# src/main.py (the window title interpolates it, so parsing the title
# no longer works).
APP_VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*["\']([\d\.]+)["\']', re.MULTILINE)

def run_command(args, cwd=PROJECT_ROOT):
    """Run a command (arg list, no shell) and return its output."""
    try:
        result = subprocess.run(
            args, shell=False, check=True, capture_output=True, text=True, cwd=cwd
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command '{args}': {e.stderr}")
        sys.exit(1)

def get_current_version():
    """Extract current version from the APP_VERSION constant in src/main.py."""
    if not os.path.exists(MAIN_PY_PATH):
        print(f"Error: {MAIN_PY_PATH} not found.")
        sys.exit(1)
    
    with open(MAIN_PY_PATH, 'r') as f:
        content = f.read()
        match = APP_VERSION_RE.search(content)
        if match:
            return match.group(1)
    
    print("Error: Could not find APP_VERSION constant in src/main.py.")
    sys.exit(1)

def bump_version(current_version, bump_type):
    """Calculate the next version based on semantic versioning."""
    parts = list(map(int, current_version.split('.')))
    
    # Ensure we have at least 3 parts for full semver, but handle X.Y as well
    while len(parts) < 3:
        parts.append(0)
    
    if bump_type == 'major':
        parts[0] += 1
        parts[1] = 0
        parts[2] = 0
    elif bump_type == 'minor':
        parts[1] += 1
        parts[2] = 0
    elif bump_type == 'patch':
        parts[2] += 1
    
    return '.'.join(map(str, parts))

def update_source_version(new_version):
    """Update the APP_VERSION constant in src/main.py and mirror it to
    tools/appimage/pyproject.toml so AppImage builds don't drift."""
    with open(MAIN_PY_PATH, 'r') as f:
        content = f.read()
    
    new_content, n = APP_VERSION_RE.subn(
        f'APP_VERSION = "{new_version}"', content
    )
    if n == 0:
        print("Error: APP_VERSION constant not found in src/main.py; nothing updated.")
        sys.exit(1)
    
    with open(MAIN_PY_PATH, 'w') as f:
        f.write(new_content)
    print(f"Updated {MAIN_PY_PATH} to version {new_version}")
    
    if os.path.exists(PYPROJECT_PATH):
        with open(PYPROJECT_PATH, 'r') as f:
            pp = f.read()
        pp_new, n_pp = re.subn(
            r'^(version\s*=\s*)["\'][\d\.]+["\']',
            f'\\g<1>"{new_version}"',
            pp, count=1, flags=re.MULTILINE
        )
        if n_pp:
            with open(PYPROJECT_PATH, 'w') as f:
                f.write(pp_new)
            print(f"Updated {PYPROJECT_PATH} to version {new_version}")
        else:
            print(f"Warning: no version key found in {PYPROJECT_PATH}.")

def _latest_tag_by_version():
    """Return the tag with the highest semantic version, or "" if none.

    Tags are ordered by version number, not by commit reachability, so a
    release cut from a side branch cannot pick a stale base the way
    ``git describe --tags --abbrev=0`` (nearest reachable tag) can.
    """
    tags = run_command(["git", "tag", "-l"]).split('\n')
    best_tag = ""
    best_version = ()
    for tag in tags:
        tag = tag.strip()
        match = re.fullmatch(r'v?(\d+)\.(\d+)(?:\.(\d+))?', tag)
        if not match:
            continue
        version = tuple(int(p) if p is not None else 0
                        for p in match.groups())
        while len(version) < 3:
            version = version + (0,)
        if version > best_version:
            best_version = version
            best_tag = tag
    return best_tag

def get_commits_since_last_tag():
    """Get list of commits since the highest-version tag.

    The base is the highest semantic version across all tags (see
    _latest_tag_by_version), not the nearest reachable tag, so history
    from merged side branches cannot shift the range.
    """
    last_tag = _latest_tag_by_version()
    if not last_tag:
        # If no tag exists, get all commits
        commits = run_command(["git", "log", "--oneline"]).split('\n')
    else:
        commits = run_command(["git", "log", f"{last_tag}..HEAD", "--oneline"]).split('\n')

    # Clean up empty lines
    return [c for c in commits if c.strip()]

# Map from conventional-commit type to Keep a Changelog section.
_COMMIT_TYPE_SECTIONS = {
    'feat': 'Added',
    'epic': 'Added',
    'fix': 'Fixed',
    'security': 'Security',
    'sec': 'Security',
}

_COMMIT_PREFIX_RE = re.compile(r'^([A-Za-z]+)(?:\([^)]*\))?!?:\s*(.*)$', re.DOTALL)

def _clean_commit_message(commit):
    """Turn a raw oneline commit into user-facing prose.

    Drops the leading hash and strips the conventional-commit prefix
    (``feat:``, ``fix(scope):``, ...), then capitalizes the first
    letter. The raw prefix and any non-English subject are never copied
    verbatim: the caller still rewrites the entry by hand when needed,
    but the generated draft is already prefix-free English-shaped text.
    """
    # Remove hash
    msg = ' '.join(commit.split(' ')[1:]).strip()
    match = _COMMIT_PREFIX_RE.match(msg)
    if match:
        msg = match.group(2).strip()
    if msg:
        msg = msg[0].upper() + msg[1:]
    return msg

def _commit_section(commit):
    """Return the Keep a Changelog section for a raw oneline commit."""
    msg = ' '.join(commit.split(' ')[1:]).strip()
    match = _COMMIT_PREFIX_RE.match(msg)
    commit_type = match.group(1).lower() if match else ''
    return _COMMIT_TYPE_SECTIONS.get(commit_type, 'Changed')

def format_changelog_entry(version, commits):
    """Format a new release entry in plain Keep a Changelog style.

    Sections are ``### Added`` / ``### Changed`` / ``### Fixed`` /
    ``### Security`` (in that order); only non-empty sections are
    emitted and no category is ever dropped. Commit subjects are
    cleaned (no ``feat:``/``fix:`` prefixes) so the draft reads as
    user-facing prose.
    """
    date = datetime.now().strftime("%Y-%m-%d")
    header = f"## [v{version}] - {date}\n"

    if not commits:
        return header + "\n### Changed\n- Maintenance release.\n"

    sections = {'Added': [], 'Changed': [], 'Fixed': [], 'Security': []}
    for commit in commits:
        text = _clean_commit_message(commit)
        if not text:
            continue
        sections[_commit_section(commit)].append(f"- {text}")

    blocks = []
    for name in ('Added', 'Changed', 'Fixed', 'Security'):
        if sections[name]:
            blocks.append(f"### {name}\n" + '\n'.join(sections[name]))

    if not blocks:
        blocks.append("### Changed\n- Maintenance release.")

    return header + '\n' + '\n\n'.join(blocks) + '\n'


def _update_link_footer(lines, new_version, prev_version):
    """Update the Keep a Changelog footer link refs for a new release.

    Rewrites the ``[Unreleased]:`` ref to ``compare/v{new}...HEAD`` and
    inserts ``[v{new}]: compare/v{prev}...v{new}`` directly above the
    previous top version's ref (or above the version-ref block when this
    is the first release). Every other ref is left untouched.

    No-op when the changelog has no footer block (no ``[Unreleased]:``
    ref): old changelogs without links must not crash or gain a
    half-built footer. Also skips the version-ref insert when the
    previous version cannot be determined or a ref for the new version
    already exists.
    """
    unreleased_idx = None
    for i, line in enumerate(lines):
        if re.match(r'^\[Unreleased\]:', line):
            unreleased_idx = i
            break
    if unreleased_idx is None:
        return lines

    old_ref = lines[unreleased_idx]
    new_ref_line, n = re.subn(
        r'compare/\S+\.\.\.HEAD', f'compare/v{new_version}...HEAD', old_ref
    )
    if n:
        lines[unreleased_idx] = new_ref_line

    if not prev_version or prev_version == new_version:
        return lines

    for line in lines:
        if line.startswith(f"[v{new_version}]:"):
            return lines

    match = re.search(r'(\S*compare/)', lines[unreleased_idx])
    if not match:
        return lines
    base = match.group(1)
    version_ref = f"[v{new_version}]: {base}v{prev_version}...v{new_version}\n"

    prev_ref_idx = None
    first_ver_ref_idx = None
    for i in range(unreleased_idx + 1, len(lines)):
        if lines[i].startswith(f"[v{prev_version}]:") and prev_ref_idx is None:
            prev_ref_idx = i
        if re.match(r'^\[v[\d.]+\]:', lines[i]) and first_ver_ref_idx is None:
            first_ver_ref_idx = i
    if prev_ref_idx is not None:
        insert_at = prev_ref_idx
    elif first_ver_ref_idx is not None:
        insert_at = first_ver_ref_idx
    else:
        insert_at = unreleased_idx + 1
    lines.insert(insert_at, version_ref)
    return lines


def build_new_changelog_text(changelog_text, new_version, generated_entry):
    """Build the full new changelog text for a release (pure, no I/O).

    This is the single code path behind both the real write and
    ``--dry-run``: the new version heading comes from ``generated_entry``
    while the body is the hand-written ``[Unreleased]`` body when it is
    non-empty (the generated commit draft is used only when
    ``[Unreleased]`` is empty). Footer link refs are maintained via
    :func:`_update_link_footer`.

    ``changelog_text`` is the current file content, or ``None`` when the
    file is missing (a fresh changelog carrying just the new entry is
    returned). ``new_version`` is the version number without a ``v``
    prefix (e.g. ``"3.0.2"``).
    """
    entry_lines = generated_entry.rstrip('\n').split('\n')
    entry_header = entry_lines[0] + '\n'
    entry_body = entry_lines[1:]

    if changelog_text is None:
        return "# Changelog\n\n## [Unreleased]\n\n" + generated_entry

    lines = changelog_text.splitlines(keepends=True)

    # Locate the [Unreleased] section and the first version heading.
    unreleased_idx = None
    first_version_idx = None
    for i, line in enumerate(lines):
        if line.startswith('## [Unreleased]'):
            unreleased_idx = i
        elif line.startswith('## [') and first_version_idx is None:
            first_version_idx = i
            break

    if unreleased_idx is None:
        # No Unreleased section: create one above the new entry.
        insert_pos = first_version_idx if first_version_idx is not None else len(lines)
        new_lines = (lines[:insert_pos]
                     + ["## [Unreleased]\n", "\n"]
                     + [generated_entry.rstrip('\n') + "\n", "\n"]
                     + lines[insert_pos:])
    else:
        end_idx = first_version_idx if first_version_idx is not None else len(lines)
        raw_slice = lines[unreleased_idx + 1:end_idx]
        # Decide emptiness on the stripped slice but keep the original
        # lines: filtering blanks here would glue category headings to
        # the previous bullet (Markdown needs a blank line before ###).
        if any(l.strip() for l in raw_slice):
            body = list(raw_slice)
        else:
            # Fallback to the generated draft; entry_body shares the
            # same header-then-blank-line layout as the main path once
            # leading blanks are stripped below.
            body = [l + '\n' for l in entry_body]
        # Normalize only the edges: drop leading/trailing blank lines so
        # there is exactly one blank line between the heading and the
        # body, and guarantee newline termination.
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        body = [l if l.endswith('\n') else l + '\n' for l in body]
        section = [entry_header, "\n"] + body + ["\n"]
        new_lines = (lines[:unreleased_idx]
                     + ["## [Unreleased]\n", "\n"]
                     + section
                     + lines[end_idx:])

    # Maintain the footer link refs the changelog already carries.
    prev_version = None
    if first_version_idx is not None:
        prev_match = re.match(
            r'^## \[v([\d.]+)\]', lines[first_version_idx]
        )
        if prev_match:
            prev_version = prev_match.group(1)
    if prev_version is None:
        for line in lines:
            if line.startswith('[Unreleased]:'):
                prev_match = re.search(
                    r'compare/v([\d.]+)\.\.\.HEAD', line
                )
                if prev_match:
                    prev_version = prev_match.group(1)
                break
    new_lines = _update_link_footer(new_lines, new_version, prev_version)

    return ''.join(new_lines)


def update_changelog_file(entry):
    """Prepend a new entry to the root CHANGELOG.md and drain [Unreleased].

    The new version heading is inserted below the ``[Unreleased]`` section.
    When ``[Unreleased]`` holds hand-written notes, that body is moved under
    the new version heading (the generated commit draft is used only when
    ``[Unreleased]`` is empty, so the same change is never recorded twice)
    and ``[Unreleased]`` is reset to an empty section. Without the drain,
    released notes would linger on top forever and read as still pending.

    Implemented on top of :func:`build_new_changelog_text` so ``--dry-run``
    previews byte-identical text to what this function writes.
    """
    new_match = re.match(r'^## \[v([\d.]+)\]', entry.rstrip('\n').split('\n')[0])
    new_version = new_match.group(1) if new_match else ""

    if not os.path.exists(CHANGELOG_PATH):
        new_text = build_new_changelog_text(None, new_version, entry)
        with open(CHANGELOG_PATH, 'w') as f:
            f.write(new_text)
        return

    with open(CHANGELOG_PATH, 'r') as f:
        changelog_text = f.read()

    new_text = build_new_changelog_text(changelog_text, new_version, entry)
    with open(CHANGELOG_PATH, 'w') as f:
        f.write(new_text)
    print(f"Updated {CHANGELOG_PATH}")


def _extract_version_section(new_changelog_text, new_version):
    """Return the ``## [vX.Y.Z]`` section from built changelog text.

    The section spans from the new version heading up to (excluding) the
    next ``## [`` heading, with trailing blank lines stripped and exactly
    one trailing newline. Returns ``""`` when the heading is not found.
    """
    lines = new_changelog_text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"## [v{new_version}]"):
            start = i
            break
    if start is None:
        return ""
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith('## ['):
            end = i
            break
    return ''.join(lines[start:end]).rstrip('\n') + '\n'


def _extract_footer_block(new_changelog_text):
    """Return the trailing footer link-ref block from built changelog text.

    The block starts at the ``[Unreleased]:`` ref and runs to end of
    file. Returns ``""`` when the changelog carries no footer refs.
    """
    lines = new_changelog_text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith('[Unreleased]:'):
            start = i
            break
    if start is None:
        return ""
    return ''.join(lines[start:]).rstrip('\n') + '\n'

def git_tag_exists(tag):
    """Check if a git tag already exists."""
    return run_command(["git", "tag", "-l", tag]) != ""

def is_dirty():
    """Check if the git worktree is dirty."""
    return run_command(["git", "status", "--short"]) != ""

def get_highest_tag():
    """Get the highest semantic version tag."""
    tags = run_command(["git", "tag", "-l"]).split('\n')
    versions = []
    for t in tags:
        match = re.search(r'v?([\d\.]+)', t)
        if match:
            v_str = match.group(1)
            parts = list(map(int, v_str.split('.')))
            while len(parts) < 3: parts.append(0)
            versions.append(tuple(parts))
    
    if not versions: return (0, 0, 0)
    return max(versions)

def main():
    parser = argparse.ArgumentParser(description="LinuxTask Release Script")
    parser.add_argument(
        "--bump", choices=["major", "minor", "patch"], default="patch",
        help="Type of version bump (default: patch)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simulate the release process without making changes."
    )
    
    args = parser.parse_args()
    
    if not args.dry_run and is_dirty():
        print("Error: Git worktree is dirty. Please commit or stash changes before release.")
        sys.exit(1)
    
    print("--- Starting LinuxTask Release Process ---")
    
    code_version = get_current_version()
    print(f"Current version in code: v{code_version}")
    
    highest_tag = '.'.join(map(str, get_highest_tag()))
    print(f"Highest tag detected: v{highest_tag}")
    
    # Use the highest of code vs tag as base
    parts_code = list(map(int, code_version.split('.')))
    while len(parts_code) < 3: parts_code.append(0)
    parts_tag = list(map(int, highest_tag.split('.')))
    while len(parts_tag) < 3: parts_tag.append(0)
    
    base_version = code_version
    if tuple(parts_tag) > tuple(parts_code):
        print(f"Warning: Code version v{code_version} is behind highest tag v{highest_tag}.")
        base_version = highest_tag
    
    new_version = bump_version(base_version, args.bump)
    print(f"New version will be: v{new_version}")
    
    commits = get_commits_since_last_tag()
    print(f"Found {len(commits)} commits since last tag.")
    
    changelog_entry = format_changelog_entry(new_version, commits)
    
    if args.dry_run:
        print("\n--- DRY RUN: Changelog entry as it will be published ---")
        try:
            with open(CHANGELOG_PATH, 'r') as f:
                changelog_text = f.read()
        except OSError as e:
            print(f"Warning: could not read {CHANGELOG_PATH}: {e}")
            print("Showing generated draft instead "
                  "(no [Unreleased] body available):")
            print(changelog_entry, end="")
            print("--- DRY RUN: Skipping file updates and git operations ---")
            return
        new_text = build_new_changelog_text(
            changelog_text, new_version, changelog_entry)
        section = _extract_version_section(new_text, new_version)
        if not section:
            print("Warning: new version section not found; "
                  "showing generated draft instead:")
            print(changelog_entry, end="")
        else:
            print(section, end="")
        footer = _extract_footer_block(new_text)
        print("\n--- DRY RUN: Footer link refs as they will be published ---")
        if footer:
            print(footer, end="")
        else:
            print("(no footer link refs found)")
        print("--- DRY RUN: Skipping file updates and git operations ---")
        return

    # Phase 1: Update source
    update_source_version(new_version)
    
    # Phase 2: Update changelog
    update_changelog_file(changelog_entry)
    
    # Phase 3: Git operations
    print("Staging changes...")
    run_command(["git", "add", "src/main.py", "tools/appimage/pyproject.toml", "CHANGELOG.md"])
    print(f"Committing release v{new_version}...")
    run_command(["git", "commit", "-m", f"chore: release v{new_version}"])
    print(f"Tagging release v{new_version}...")
    run_command(["git", "tag", "-a", f"v{new_version}", "-m", f"Release v{new_version}"])
    
    print(f"\n✅ Release v{new_version} completed successfully!")
    print("Don't forget to push: git push origin main --tags")

if __name__ == "__main__":
    main()
