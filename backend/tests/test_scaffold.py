"""Minimal non-business check for the Python package scaffold."""

import stem_sci


def test_stem_sci_package_is_importable() -> None:
    """The namespaced project package must import from the src layout."""
    assert stem_sci.__version__ == "0.1.0"
