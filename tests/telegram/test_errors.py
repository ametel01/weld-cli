"""Tests for Telegram error hierarchy."""

import pytest


class TestTelegramErrorHierarchy:
    """Test that all Telegram errors form a proper hierarchy."""

    @pytest.mark.unit
    def test_telegram_error_is_base_exception(self):
        """TelegramError inherits from Exception."""
        from weld.telegram.errors import TelegramError

        assert issubclass(TelegramError, Exception)

    @pytest.mark.unit
    def test_file_path_error_inherits_from_telegram_error(self):
        """FilePathError inherits from TelegramError."""
        from weld.telegram.errors import FilePathError, TelegramError

        assert issubclass(FilePathError, TelegramError)

    @pytest.mark.unit
    def test_path_traversal_error_inherits_from_file_path_error(self):
        """PathTraversalError inherits from FilePathError."""
        from weld.telegram.errors import FilePathError, PathTraversalError

        assert issubclass(PathTraversalError, FilePathError)

    @pytest.mark.unit
    def test_path_not_allowed_error_inherits_from_file_path_error(self):
        """PathNotAllowedError inherits from FilePathError."""
        from weld.telegram.errors import FilePathError, PathNotAllowedError

        assert issubclass(PathNotAllowedError, FilePathError)

    @pytest.mark.unit
    def test_path_not_found_error_inherits_from_file_path_error(self):
        """PathNotFoundError inherits from FilePathError."""
        from weld.telegram.errors import FilePathError, PathNotFoundError

        assert issubclass(PathNotFoundError, FilePathError)

    @pytest.mark.unit
    def test_file_path_errors_can_be_caught_as_telegram_error(self):
        """All file path errors can be caught as TelegramError."""
        from weld.telegram.errors import (
            PathNotAllowedError,
            PathNotFoundError,
            PathTraversalError,
            TelegramError,
        )

        # Each specific error should be catchable as TelegramError
        for error_class in [PathTraversalError, PathNotAllowedError, PathNotFoundError]:
            with pytest.raises(TelegramError):
                raise error_class("test message")

    @pytest.mark.unit
    def test_file_path_error_importable_from_errors_module(self):
        """FilePathError and subclasses are importable from errors.py."""
        from weld.telegram.errors import (
            FilePathError,
            PathNotAllowedError,
            PathNotFoundError,
            PathTraversalError,
        )

        # Verify all are available
        assert FilePathError is not None
        assert PathTraversalError is not None
        assert PathNotAllowedError is not None
        assert PathNotFoundError is not None

    @pytest.mark.unit
    def test_file_path_error_also_importable_from_files_module(self):
        """FilePathError remains importable from files.py for backwards compatibility."""
        from weld.telegram.files import (
            FilePathError,
            PathNotAllowedError,
            PathNotFoundError,
            PathTraversalError,
        )

        # Verify all are available from original location
        assert FilePathError is not None
        assert PathTraversalError is not None
        assert PathNotAllowedError is not None
        assert PathNotFoundError is not None
