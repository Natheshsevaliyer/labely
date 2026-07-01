"""Unit tests for app/core/config.py"""
import pytest
from app.core.config import settings


class TestSettings:
    def test_app_name_default(self):
        assert settings.APP_NAME == "EMD Label Generator"

    def test_jwt_algorithm_default(self):
        assert settings.JWT_ALGORITHM == "HS256"

    def test_redis_url_without_password(self):
        # In test mode, REDIS_PASSWORD is not set
        url = settings.REDIS_URL
        assert url.startswith("redis://")
        assert str(settings.REDIS_PORT) in url

    def test_redis_url_with_password(self, monkeypatch):
        monkeypatch.setattr(settings, "REDIS_PASSWORD", "secret")
        url = settings.REDIS_URL
        assert ":secret@" in url

    def test_database_url_tcp_mode(self):
        url = settings.DATABASE_URL
        assert "mysql" in url
        assert settings.DB_HOST in url

    def test_database_url_socket_mode(self, monkeypatch):
        monkeypatch.setattr(settings, "DB_MODE", "socket")
        monkeypatch.setattr(settings, "DB_HOST", "/var/run/mysql.sock")
        url = settings.DATABASE_URL
        assert "unix_socket" in url

    def test_allowed_extensions_contains_pdf(self):
        assert "pdf" in settings.ALLOWED_EXTENSIONS

    def test_access_token_expire_hours_positive(self):
        assert settings.ACCESS_TOKEN_EXPIRE_HOURS > 0

    def test_batch_size_positive(self):
        assert settings.BATCH_SIZE >= 1

    def test_srp_max_concurrent_positive(self):
        assert settings.SRP_MAX_CONCURRENT > 0

    def test_ensure_directories_creates_output(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "OUTPUT_FOLDER", str(tmp_path / "new_output"))
        settings.ensure_directories()
        import os
        assert os.path.isdir(settings.OUTPUT_FOLDER)
