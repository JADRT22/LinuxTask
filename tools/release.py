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
CHANGELOG_PATH = os.path.join(PROJECT_ROOT, 'docs', 'CHANGELOG.md')

def run_command(command, cwd=PROJECT_ROOT):
    """Run a shell command and return its output."""
    try:
        result = subprocess.run(
            command, shell=True, check=True, capture_output=True, text=True, cwd=cwd
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command '{command}': {e.stderr}")
        sys.exit(1)

def get_current_version():
    """Extract current version from src/main.py."""
    if not os.path.exists(MAIN_PY_PATH):
        print(f"Error: {MAIN_PY_PATH} not found.")
        sys.exit(1)
    
    with open(MAIN_PY_PATH, 'r') as f:
        content = f.read()
        # Look for pattern self.title("LinuxTask vX.Y - ...")
        match = re.search(r'self\.title\("LinuxTask v([\d\.]+) -', content)
        if match:
            return match.group(1)
    
    print("Error: Could not find version in src/main.py.")
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
    """Update version string in src/main.py."""
    with open(MAIN_PY_PATH, 'r') as f:
        content = f.read()
    
    new_content = re.sub(
        r'self\.title\("LinuxTask v[\d\.]+ -',
        f'self.title("LinuxTask v{new_version} -',
        content
    )
    
    with open(MAIN_PY_PATH, 'w') as f:
        f.write(new_content)
    print(f"Updated {MAIN_PY_PATH} to version {new_version}")

def get_commits_since_last_tag():
    """Get list of commits since the last tag."""
    last_tag = run_command("git describe --tags --abbrev=0")
    if not last_tag:
        # If no tag exists, get all commits
        commits = run_command("git log --oneline").split('\n')
    else:
        commits = run_command(f"git log {last_tag}..HEAD --oneline").split('\n')
    
    # Clean up empty lines
    return [c for c in commits if c.strip()]

def format_changelog_entry(version, commits):
    """Format new release entry for CHANGELOG.md."""
    date = datetime.now().strftime("%Y-%m-%d")
    header = f"## [v{version}] - {date}\n"

    if not commits:
        return header + "### 🛡️ Improvements & Fixes\n- Maintenance release.\n"

    # Group commits by type (naive implementation)
    feats = []
    fixes = []
    others = []

    for commit in commits:
        # Remove hash
        msg = ' '.join(commit.split(' ')[1:])
        if msg.lower().startswith('feat'):
            feats.append(f"- {msg}")
        elif msg.lower().startswith('fix'):
            fixes.append(f"- {msg}")
        elif msg.lower().startswith('epic'):
            feats.append(f"- {msg}")
        else:
            others.append(f"- {msg}")

    entry = header
    if feats:
        entry += "### ✨ New Features\n" + '\n'.join(feats) + '\n'
    if fixes:
        entry += "### 🛡️ Improvements & Fixes\n" + '\n'.join(fixes) + '\n'
    if others and not (feats or fixes):
         entry += "### 🛠️ Maintenance\n" + '\n'.join(others) + '\n'
    elif others:
         entry += "### 🛠️ Other Changes\n" + '\n'.join(others) + '\n'

    return entry


def update_changelog_file(entry):
    """Prepend new entry to docs/CHANGELOG.md."""
    if not os.path.exists(CHANGELOG_PATH):
        with open(CHANGELOG_PATH, 'w') as f:
            f.write("# Changelog\n\n" + entry)
        return

    with open(CHANGELOG_PATH, 'r') as f:
        lines = f.readlines()
    
    # Find position after the title
    insert_pos = 0
    for i, line in enumerate(lines):
        if line.strip().startswith('# Changelog'):
            insert_pos = i + 1
            break
    
    # Add spacing
    new_lines = lines[:insert_pos] + ["\n", entry + "\n"] + lines[insert_pos:]
    
    with open(CHANGELOG_PATH, 'w') as f:
        f.writelines(new_lines)
    print(f"Updated {CHANGELOG_PATH}")

def git_tag_exists(tag):
    """Check if a git tag already exists."""
    return run_command(f"git tag -l {tag}") != ""

def is_dirty():
    """Check if the git worktree is dirty."""
    return run_command("git status --short") != ""

def get_highest_tag():
    """Get the highest semantic version tag."""
    tags = run_command("git tag -l").split('\n')
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
        print("\n--- DRY RUN: Proposed Changelog Entry ---")
        print(changelog_entry)
        print("--- DRY RUN: Skipping file updates and git operations ---")
        return

    # Phase 1: Update source
    update_source_version(new_version)
    
    # Phase 2: Update changelog
    update_changelog_file(changelog_entry)
    
    # Phase 3: Git operations
    print("Staging changes...")
    run_command("git add src/main.py docs/CHANGELOG.md")
    print(f"Committing release v{new_version}...")
    run_command(f'git commit -m "chore: release v{new_version}"')
    print(f"Tagging release v{new_version}...")
    run_command(f'git tag -a v{new_version} -m "Release v{new_version}"')
    
    print(f"\n✅ Release v{new_version} completed successfully!")
    print("Don't forget to push: git push origin main --tags")

if __name__ == "__main__":
    main()
