"""Unit tests for app/utils/file_utils.py"""
import os
import time
import tempfile
import pytest

from app.utils.file_utils import ensure_dir, safe_filename, get_file_size, cleanup_old_files


class TestEnsureDir:
    def test_creates_directory(self, tmp_path):
        target = str(tmp_path / "new_dir")
        result = ensure_dir(target)
        assert os.path.isdir(target)
        assert result == target

    def test_existing_directory_no_error(self, tmp_path):
        target = str(tmp_path)
        result = ensure_dir(target)
        assert result == target

    def test_nested_directories(self, tmp_path):
        target = str(tmp_path / "a" / "b" / "c")
        ensure_dir(target)
        assert os.path.isdir(target)


class TestSafeFilename:
    def test_alphanumeric_unchanged(self):
        assert safe_filename("file123") == "file123"

    def test_removes_special_chars(self):
        result = safe_filename("file/name<>?")
        assert "/" not in result
        assert "<" not in result

    def test_allows_dots_and_dashes(self):
        result = safe_filename("report-2024.pdf")
        assert result == "report-2024.pdf"

    def test_strips_trailing_spaces(self):
        result = safe_filename("file   ")
        assert not result.endswith(" ")

    def test_empty_string(self):
        assert safe_filename("") == ""


class TestGetFileSize:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        assert get_file_size(str(f)) == 11

    def test_nonexistent_file_returns_zero(self):
        assert get_file_size("/nonexistent/path/file.txt") == 0

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        assert get_file_size(str(f)) == 0


class TestCleanupOldFiles:
    def test_deletes_old_files(self, tmp_path):
        old_file = tmp_path / "old.pdf"
        old_file.write_bytes(b"old content")
        # Backdate modification time by 2 days
        two_days_ago = time.time() - (2 * 86400)
        os.utime(str(old_file), (two_days_ago, two_days_ago))

        cleanup_old_files(str(tmp_path), days_old=1)
        assert not old_file.exists()

    def test_keeps_recent_files(self, tmp_path):
        new_file = tmp_path / "new.pdf"
        new_file.write_bytes(b"new content")

        cleanup_old_files(str(tmp_path), days_old=1)
        assert new_file.exists()

    def test_pattern_filter_skips_non_matching(self, tmp_path):
        old_txt = tmp_path / "old.txt"
        old_txt.write_bytes(b"x")
        two_days_ago = time.time() - (2 * 86400)
        os.utime(str(old_txt), (two_days_ago, two_days_ago))

        cleanup_old_files(str(tmp_path), days_old=1, pattern=".pdf")
        # .txt file should NOT be deleted because pattern is ".pdf"
        assert old_txt.exists()
