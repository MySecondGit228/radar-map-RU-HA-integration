"""Validate a release tag against the custom integration manifest."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "custom_components" / "radar_map" / "manifest.json"
SEMVER = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?:0|[1-9A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def manifest_version() -> str:
    """Read the integration version from its single source of truth."""
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    version = payload.get("version")
    if not isinstance(version, str):
        raise ValueError("manifest.json does not contain a string version")
    return version


def validate_version(tag: str | None = None) -> str:
    """Validate SemVer and optionally ensure a v-prefixed tag matches it."""
    version = manifest_version()
    if SEMVER.fullmatch(version) is None:
        raise ValueError(f"Manifest version is not valid SemVer: {version!r}")
    if tag is not None:
        if not tag.startswith("v") or SEMVER.fullmatch(tag[1:]) is None:
            raise ValueError(f"Release tag must use v-prefixed SemVer: {tag!r}")
        if tag[1:] != version:
            raise ValueError(f"Release tag {tag!r} does not match manifest version {version!r}")
    return version


def main() -> int:
    """Run validation from the command line."""
    tag = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        version = validate_version(tag)
    except (OSError, json.JSONDecodeError, ValueError) as err:
        print(f"Version validation failed: {err}", file=sys.stderr)
        return 1
    print(f"RadarMap version {version} is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
