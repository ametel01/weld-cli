"""Tests for Timing model."""

from weld.models import Timing


class TestTimingModel:
    """Tests for Timing Pydantic model."""

    def test_default_values(self) -> None:
        """Timing should have zero defaults for all fields."""
        timing = Timing()
        assert timing.ai_invocation_ms == 0
        assert timing.checks_ms == 0
        assert timing.review_ms == 0
        assert timing.total_ms == 0

    def test_custom_values(self) -> None:
        """Timing should accept custom values."""
        timing = Timing(
            ai_invocation_ms=1500,
            checks_ms=500,
            review_ms=2000,
            total_ms=4000,
        )
        assert timing.ai_invocation_ms == 1500
        assert timing.checks_ms == 500
        assert timing.review_ms == 2000
        assert timing.total_ms == 4000

    def test_partial_values(self) -> None:
        """Timing should accept partial values with defaults for rest."""
        timing = Timing(ai_invocation_ms=1000)
        assert timing.ai_invocation_ms == 1000
        assert timing.checks_ms == 0
        assert timing.review_ms == 0
        assert timing.total_ms == 0

    def test_json_serialization(self) -> None:
        """Timing should serialize to JSON correctly."""
        timing = Timing(ai_invocation_ms=100, total_ms=200)
        json_str = timing.model_dump_json()
        assert "ai_invocation_ms" in json_str
        assert "100" in json_str

    def test_json_deserialization(self) -> None:
        """Timing should deserialize from JSON correctly."""
        json_str = '{"ai_invocation_ms": 500, "checks_ms": 100, "review_ms": 200, "total_ms": 800}'
        timing = Timing.model_validate_json(json_str)
        assert timing.ai_invocation_ms == 500
        assert timing.checks_ms == 100
        assert timing.review_ms == 200
        assert timing.total_ms == 800

    def test_model_dump(self) -> None:
        """Timing should dump to dict correctly."""
        timing = Timing(ai_invocation_ms=1000, checks_ms=500)
        data = timing.model_dump()
        assert data == {
            "ai_invocation_ms": 1000,
            "checks_ms": 500,
            "review_ms": 0,
            "total_ms": 0,
        }

    def test_negative_values_accepted(self) -> None:
        """Timing currently accepts negative values (no validation)."""
        # This documents current behavior - may want to add validation later
        timing = Timing(ai_invocation_ms=-100)
        assert timing.ai_invocation_ms == -100
