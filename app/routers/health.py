"""
Router: GET /api/health
Verifica que el servidor esté en pie y que los CSV estén disponibles.
"""
from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter()

DATA_DIR = os.getenv("DATA_DIR", "./DB")


@router.get("/health")
async def health():
    csv_path = os.path.join(DATA_DIR, "denue_inegi_15_1.csv")
    data_available = os.path.isfile(csv_path)
    return {
        "ok": True,
        "data_dir": os.path.abspath(DATA_DIR),
        "data_available": data_available,
    }
