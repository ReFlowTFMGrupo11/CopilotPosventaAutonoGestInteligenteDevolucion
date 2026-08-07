"""
frontend/lib/settings.py
===========================
Configuración del frontend Streamlit: URL base del backend FastAPI. Se lee
de la variable de entorno REFLOW_API_URL para poder apuntar a un backend
distinto (Docker, staging...) sin tocar código.
"""

import os

API_BASE_URL = os.getenv("REFLOW_API_URL", "http://localhost:8000")
