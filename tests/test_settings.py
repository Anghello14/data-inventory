"""
test_settings.py – Pruebas de la configuración central.
"""

from pathlib import Path

import pytest

from config import settings


class TestPaths:
    def test_base_dir_is_path(self) -> None:
        assert isinstance(settings.BASE_DIR, Path)

    def test_output_dir_exists(self) -> None:
        assert settings.OUTPUT_DIR.exists()

    def test_logs_dir_exists(self) -> None:
        assert settings.LOGS_DIR.exists()


class TestConnectionDefaults:
    def test_dsn_contains_host(self) -> None:
        assert settings.DB_HOST in settings.DSN

    def test_dsn_contains_port(self) -> None:
        assert str(settings.DB_PORT) in settings.DSN

    def test_sqlalchemy_url_has_driver(self) -> None:
        assert settings.SQLALCHEMY_URL.startswith("oracle+oracledb://")


class TestExtractDefaults:
    def test_batch_size_positive(self) -> None:
        assert settings.DEFAULT_BATCH_SIZE > 0

    def test_batch_size_is_int(self) -> None:
        assert isinstance(settings.DEFAULT_BATCH_SIZE, int)


class TestOutputDefaults:
    def test_delimiter_is_string(self) -> None:
        assert isinstance(settings.CSV_DELIMITER, str)

    def test_encoding_is_string(self) -> None:
        assert isinstance(settings.CSV_ENCODING, str)

    def test_manifest_filename_ends_json(self) -> None:
        assert settings.MANIFEST_FILENAME.endswith(".json")
