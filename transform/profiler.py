"""
profiler.py – Generación de reportes de calidad de datos.

Clase principal: DataProfiler
  - Recibe un DataFrame (o lista de DataFrames) y genera métricas de
    calidad: nulos, cardinalidad, estadísticas descriptivas, etc.
  - Puede exportar el reporte como DataFrame, JSON o archivo Excel.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class DataProfiler:
    """Calcula métricas de calidad sobre un DataFrame."""

    def __init__(self, df: pd.DataFrame, table_name: str = "tabla") -> None:
        """
        Args:
            df:          DataFrame a perfilar.
            table_name:  Nombre descriptivo de la tabla (aparece en el reporte).
        """
        self.df = df
        self.table_name = table_name
        self._profile: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # Generación del perfil
    # ------------------------------------------------------------------

    def build(self) -> "DataProfiler":
        """
        Calcula todas las métricas y almacena el resultado internamente.

        Returns:
            self (permite encadenamiento).
        """
        logger.info("Perfilando tabla '%s' (%d filas, %d cols)…",
                    self.table_name, len(self.df), len(self.df.columns))

        rows: list[dict] = []
        total = len(self.df)

        for col in self.df.columns:
            serie = self.df[col]
            null_count = int(serie.isna().sum())
            not_null = total - null_count

            row: dict = {
                "tabla": self.table_name,
                "columna": col,
                "tipo_dato": str(serie.dtype),
                "total_filas": total,
                "nulos": null_count,
                "pct_nulos": round(null_count / total * 100, 2) if total else 0.0,
                "no_nulos": not_null,
                "pct_no_nulos": round(not_null / total * 100, 2) if total else 0.0,
                "cardinalidad": int(serie.nunique(dropna=True)),
                "pct_unicidad": round(serie.nunique(dropna=True) / not_null * 100, 2)
                if not_null else 0.0,
            }

            # Estadísticas numéricas
            if pd.api.types.is_numeric_dtype(serie):
                row.update({
                    "min": serie.min(),
                    "max": serie.max(),
                    "media": round(float(serie.mean()), 4) if not_null else None,
                    "mediana": round(float(serie.median()), 4) if not_null else None,
                    "desv_std": round(float(serie.std()), 4) if not_null else None,
                })
            else:
                row.update({"min": None, "max": None, "media": None,
                             "mediana": None, "desv_std": None})

            # Estadísticas de texto
            if pd.api.types.is_string_dtype(serie) or pd.api.types.is_object_dtype(serie):
                lengths = serie.dropna().astype(str).str.len()
                row.update({
                    "long_min": int(lengths.min()) if not lengths.empty else None,
                    "long_max": int(lengths.max()) if not lengths.empty else None,
                    "long_media": round(float(lengths.mean()), 2) if not lengths.empty else None,
                    "valor_mas_frecuente": serie.value_counts().idxmax() if not_null else None,
                })
            else:
                row.update({
                    "long_min": None, "long_max": None,
                    "long_media": None, "valor_mas_frecuente": None,
                })

            rows.append(row)

        self._profile = pd.DataFrame(rows)
        logger.info("Perfil generado: %d columnas analizadas.", len(rows))
        return self

    # ------------------------------------------------------------------
    # Acceso al resultado
    # ------------------------------------------------------------------

    @property
    def profile(self) -> pd.DataFrame:
        """Devuelve el DataFrame con el perfil; genera si aún no existe."""
        if self._profile is None:
            self.build()
        return self._profile

    def to_dict(self) -> list[dict]:
        """Devuelve el perfil como lista de diccionarios."""
        return self.profile.to_dict(orient="records")

    def to_json(self, path: Optional[Path] = None, indent: int = 2) -> str:
        """
        Serializa el perfil a JSON.

        Args:
            path:   Si se indica, guarda el JSON en esa ruta.
            indent: Indentación del JSON.

        Returns:
            String JSON.
        """
        data = self.to_dict()
        json_str = json.dumps(data, ensure_ascii=False, indent=indent, default=str)
        if path is not None:
            Path(path).write_text(json_str, encoding="utf-8")
            logger.info("Perfil JSON guardado en %s.", path)
        return json_str

    def to_excel(self, path: Path) -> None:
        """
        Exporta el perfil a un archivo Excel (.xlsx).

        Args:
            path: Ruta del archivo de salida.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            self.profile.to_excel(writer, sheet_name="Perfil", index=False)
        logger.info("Perfil Excel guardado en %s.", path)

    def to_csv(self, path: Path, delimiter: str = ",") -> None:
        """
        Exporta el perfil a CSV.

        Args:
            path:      Ruta del archivo de salida.
            delimiter: Separador de columnas.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.profile.to_csv(path, index=False, sep=delimiter, encoding="utf-8")
        logger.info("Perfil CSV guardado en %s.", path)

    # ------------------------------------------------------------------
    # Resumen ejecutivo
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """
        Devuelve un resumen de alto nivel del perfil.

        Returns:
            Diccionario con métricas globales.
        """
        p = self.profile
        return {
            "tabla": self.table_name,
            "total_filas": int(p["total_filas"].iloc[0]) if not p.empty else 0,
            "total_columnas": len(p),
            "columnas_con_nulos": int((p["nulos"] > 0).sum()),
            "columnas_sin_nulos": int((p["nulos"] == 0).sum()),
            "pct_nulos_global": round(float(p["pct_nulos"].mean()), 2),
        }
