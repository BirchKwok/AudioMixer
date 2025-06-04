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
        print(f"Return code: {result.returncode}")
        if result.stderr:
            print(f"Error output: {result.stderr}")
        if result.stdout:
            print(f"Standard output: {result.stdout}")
        sys.exit(1)
    
    return result


def check_pypi_dependencies():
    """Check if required PyPI publishing dependencies are installed"""
    try:
        run_command("python -c 'import build'", check=False)
        build_available = True
    except:
        build_available = False
    
    try:
        run_command("python -c 'import twine'", check=False)
        twine_available = True
    except:
        twine_available = False
    
    if not build_available or not twine_available:
        print("Missing dependencies for PyPI publishing:")
        if not build_available:
            print("  - build: pip install build")
        if not twine_available:
            print("  - twine: pip install twine")
        print("\nInstalling dependencies...")
        run_command("pip install build twine")


def build_package():
    """Build the package for PyPI"""
    print("Building package...")
    
    # Clean previous builds
    dist_dir = Path("dist")
    if dist_dir.exists():
        run_command("rm -rf dist/")
    
    # Build source distribution and wheel
    run_command("python -m build")
    print("Package built successfully ✅")


def upload_to_pypi(dry_run=False):
    """Upload package to PyPI"""
    if dry_run:
        print("DRY RUN - Would upload to PyPI")
        run_command("twine check dist/*")
        return
    
    print("Uploading to PyPI...")
    
    # Check the distribution files first
    print("Checking distribution files...")
    run_command("twine check dist/*")
    
    # List what files will be uploaded
    result = run_command("ls -la dist/", check=False)
    print("Files to upload:")
    print(result.stdout)
    
    # Check if PyPI credentials are configured
    print("Checking PyPI credentials...")
    
    # Try to get repository info (this will show if credentials are set up)
    result = run_command("twine check --repository pypi dist/* 2>&1 || true", check=False)
    
    print("Attempting to upload to PyPI...")
    print("Note: This requires PyPI credentials to be configured.")
    print("You can set them via:")
    print("  1. Environment variables: TWINE_USERNAME and TWINE_PASSWORD")
    print("  2. Config file: ~/.pypirc")
    print("  3. Interactive prompt (if not set)")
    
    # Upload to PyPI with more verbose output
    try:
        result = run_command("twine upload dist/* --verbose", check=False)
        if result.returncode != 0:
            print("\n❌ PyPI upload failed!")
            print("Common issues:")
            print("  - Missing credentials (set TWINE_USERNAME and TWINE_PASSWORD)")
            print("  - Package version already exists on PyPI")
            print("  - Network connection issues")
            print("  - Package name conflicts")
            
            if result.stderr:
                print(f"\nDetailed error: {result.stderr}")
            if result.stdout:
                print(f"\nOutput: {result.stdout}")
            
            sys.exit(1)
        else:
            print("Package uploaded to PyPI successfully ✅")
    except Exception as e:
        print(f"Exception during upload: {e}")
        sys.exit(1)


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
    parser.add_argument(
        "--publish-pypi",
        action="store_true",
        help="Automatically publish to PyPI after successful release"
    )
    parser.add_argument(
        "--skip-git",
        action="store_true",
        help="Skip git operations (commit, tag, push instructions)"
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
            if not args.skip_git:
                print(f"Would create tag v{new_version}")
            if args.publish_pypi:
                print("Would build and upload package to PyPI")
            return
        
        # Check if working directory is clean (unless skipping git)
        if not args.skip_git:
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
        
        # Git operations
        if not args.skip_git:
            # Commit version bump
            run_command(f"git add pyproject.toml")
            run_command(f'git commit -m "bump: version to {new_version}"')
            
            # Create tag
            tag_name = f"v{new_version}"
            run_command(f"git tag {tag_name}")
        
        # PyPI publishing
        if args.publish_pypi:
            check_pypi_dependencies()
            build_package()
            upload_to_pypi(dry_run=args.dry_run)
        
        print(f"\n✅ Release {new_version} prepared!")
        
        if not args.skip_git:
            tag_name = f"v{new_version}"
            print(f"Tag {tag_name} created locally.")
            print("\nTo complete the release:")
            print(f"  git push origin main")
            print(f"  git push origin {tag_name}")
            print("\nThis will trigger the release workflow on GitHub.")
        
        if args.publish_pypi:
            print(f"\n🎉 Package {new_version} has been published to PyPI!")
            print(f"Install with: pip install audiomixer=={new_version}")
        elif not args.dry_run:
            print(f"\nTo publish to PyPI later, run:")
            print(f"  python scripts/release.py {args.bump_type} --publish-pypi --skip-git")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 