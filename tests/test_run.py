"""Tests for weld run utilities."""

from pathlib import Path

from weld.run import generate_run_id, sanitize_slug


def test_generate_run_id_with_slug():
    rid = generate_run_id(slug="my-feature")
    assert "my-feature" in rid
    assert len(rid.split("-")) >= 3


def test_generate_run_id_from_spec():
    rid = generate_run_id(spec_path=Path("specs/my_feature.md"))
    assert "my-feature" in rid or "my_feature" in rid


def test_sanitize_slug():
    assert sanitize_slug("Hello World!") == "hello-world"
    assert sanitize_slug("Test@#$123") == "test-123"
    assert sanitize_slug("   spaces   ") == "spaces"
