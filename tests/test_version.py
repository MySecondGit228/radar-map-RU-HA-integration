"""Release version consistency tests."""

from __future__ import annotations

import pytest

from scripts.check_version import validate_version


def test_manifest_version_matches_release_tag() -> None:
    """The current release tag and manifest version remain synchronized."""
    assert validate_version("v1.1.0") == "1.1.0"


@pytest.mark.parametrize("tag", ["1.1.0", "v1.1", "v1.1.1"])
def test_invalid_or_mismatched_release_tag_is_rejected(tag: str) -> None:
    """Invalid and stale tags cannot create an incorrectly versioned release."""
    with pytest.raises(ValueError):
        validate_version(tag)
