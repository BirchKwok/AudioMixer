#!/usr/bin/env python3
"""
Release helper script for AudioMixer

This script helps automate version bumping and releasing.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def get_current_version():
    """Get current version from pyproject.toml"""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        raise FileNotFoundError("pyproject.toml not found")
    
    content = pyproject_path.read_text()
    match = re.search(r'version = "([^"]+)"', content)
    if not match:
        raise ValueError("Version not found in pyproject.toml")
    
    return match.group(1)


def bump_version(current_version, bump_type):
    """Bump version based on type (major, minor, patch)"""
    parts = current_version.split('.')
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {current_version}")
    
    major, minor, patch = map(int, parts)
    
    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")
    
    return f"{major}.{minor}.{patch}"


def update_version_in_file(new_version):
    """Update version in pyproject.toml"""
    pyproject_path = Path("pyproject.toml")
    content = pyproject_path.read_text()
    
    new_content = re.sub(
        r'version = "[^"]+"',
        f'version = "{new_version}"',
        content
    )
    
    pyproject_path.write_text(new_content)
    print(f"Updated version to {new_version} in pyproject.toml")


def run_command(cmd, check=True):
    """Run a shell command"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if check and result.returncode != 0:
        print(f"Command failed: {cmd}")
        print(f"Error: {result.stderr}")
        sys.exit(1)
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Release helper for AudioMixer")
    parser.add_argument(
        "bump_type",
        choices=["major", "minor", "patch"],
        help="Type of version bump"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip running tests before release"
    )
    
    args = parser.parse_args()
    
    try:
        # Get current version
        current_version = get_current_version()
        print(f"Current version: {current_version}")
        
        # Calculate new version
        new_version = bump_version(current_version, args.bump_type)
        print(f"New version: {new_version}")
        
        if args.dry_run:
            print("DRY RUN - No changes will be made")
            print(f"Would update version from {current_version} to {new_version}")
            print(f"Would create tag v{new_version}")
            return
        
        # Check if working directory is clean
        result = run_command("git status --porcelain")
        if result.stdout.strip():
            print("Working directory is not clean. Please commit or stash changes.")
            sys.exit(1)
        
        # Run tests unless skipped
        if not args.skip_tests:
            print("Running tests...")
            run_command("python -m pytest tests/ -v")
            print("Tests passed ✅")
        
        # Update version
        update_version_in_file(new_version)
        
        # Commit version bump
        run_command(f"git add pyproject.toml")
        run_command(f'git commit -m "bump: version to {new_version}"')
        
        # Create and push tag
        tag_name = f"v{new_version}"
        run_command(f"git tag {tag_name}")
        
        print(f"\n✅ Release {new_version} prepared!")
        print(f"Tag {tag_name} created locally.")
        print("\nTo complete the release:")
        print(f"  git push origin main")
        print(f"  git push origin {tag_name}")
        print("\nThis will trigger the release workflow on GitHub.")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 