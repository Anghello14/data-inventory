"""
csv_writer.py – Escritura de DataFrames en CSV y generación de manifiestos.

Clase principal: CsvWriter
  - Escribe uno o varios DataFrames en archivos CSV.
  - Genera un manifiesto JSON con metadatos de cada archivo producido
    (nombre, ruta, filas, columnas, hash SHA-256, timestamp).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)


class CsvWriter:
    """Escribe DataFrames como CSV y registra metadatos en un manifiesto."""

    def __init__(
        self,
        output_dir: Path = settings.OUTPUT_DIR,
        delimiter: str = settings.CSV_DELIMITER,
        encoding: str = settings.CSV_ENCODING,
        manifest_filename: str = settings.MANIFEST_FILENAME,
    ) -> None:
        """
        Args:
            output_dir:        Directorio de salida.
            delimiter:         Separador de columnas CSV.
            encoding:          Codificación del archivo CSV.
            manifest_filename: Nombre del archivo de manifiesto JSON.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.delimiter = delimiter
        self.encoding = encoding
        self.manifest_path = self.output_dir / manifest_filename
        self._manifest: list[dict] = []

    # ------------------------------------------------------------------
    # Escritura de CSV
    # ------------------------------------------------------------------

    def write(
        self,
        df: pd.DataFrame,
        filename: str,
        include_index: bool = False,
    ) -> Path:
        """
        Escribe un DataFrame en un archivo CSV.

        Args:
            df:            DataFrame a escribir.
            filename:      Nombre del archivo (sin directorio).
                           Si no termina en ``.csv`` se añade automáticamente.
            include_index: Si True, incluye el índice del DataFrame.

        Returns:
            Ruta absoluta del archivo generado.
        """
        if not filename.endswith(".csv"):
            filename = f"{filename}.csv"

        filepath = self.output_dir / filename
        df.to_csv(
            filepath,
            index=include_index,
            sep=self.delimiter,
            encoding=self.encoding,
        )
        logger.info("CSV escrito: %s (%d filas, %d cols).", filepath, len(df), len(df.columns))

        self._register(df, filepath)
        return filepath

    def write_chunks(
        self,
        chunks,
        base_filename: str,
        include_index: bool = False,
    ) -> list[Path]:
        """
        Escribe un generador de DataFrames en archivos CSV numerados.

        Args:
            chunks:        Generador / iterable de DataFrames.
            base_filename: Nombre base (se añade ``_part{n}`` y ``.csv``).
            include_index: Si True, incluye el índice.

        Returns:
            Lista de rutas generadas.
        """
        paths: list[Path] = []
        for i, chunk in enumerate(chunks, start=1):
            part_name = f"{base_filename}_part{i:04d}.csv"
            path = self.write(chunk, part_name, include_index=include_index)
            paths.append(path)
        logger.info("%d fragmentos escritos para '%s'.", len(paths), base_filename)
        return paths

    # ------------------------------------------------------------------
    # Manifiesto
    # ------------------------------------------------------------------

    def _sha256(self, filepath: Path) -> str:
        """Calcula el hash SHA-256 de un archivo."""
        h = hashlib.sha256()
        with filepath.open("rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                h.update(block)
        return h.hexdigest()

    def _register(self, df: pd.DataFrame, filepath: Path) -> None:
        """Agrega una entrada al manifiesto en memoria."""
        entry = {
            "archivo": filepath.name,
            "ruta": str(filepath.resolve()),
            "filas": len(df),
            "columnas": len(df.columns),
            "columnas_nombres": list(df.columns),
            "sha256": self._sha256(filepath),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        self._manifest.append(entry)
        logger.debug("Manifiesto actualizado: %s.", entry["archivo"])

    def save_manifest(self, extra_metadata: Optional[dict] = None) -> Path:
        """
        Persiste el manifiesto JSON en disco.

        Args:
            extra_metadata: Diccionario adicional a incluir en el manifiesto
                            (ej. parámetros de ejecución, versión, etc.).

        Returns:
            Ruta del archivo de manifiesto generado.
        """
        manifest_data: dict = {
            "generado_utc": datetime.now(timezone.utc).isoformat(),
            "total_archivos": len(self._manifest),
        }
        if extra_metadata:
            manifest_data.update(extra_metadata)
        manifest_data["archivos"] = self._manifest

        self.manifest_path.write_text(
            json.dumps(manifest_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Manifiesto guardado en %s.", self.manifest_path)
        return self.manifest_path

    @property
    def manifest(self) -> list[dict]:
        """Lista en memoria de entradas del manifiesto."""
        return self._manifest
