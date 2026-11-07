# ── Imagen base ──────────────────────────────────────────────────────────────
FROM python:3.12-slim

# gcc: necesario para compilar extensiones C (tiktoken, pydantic-core, etc.)
# No se instala curl: arrastra libcurl→libsasl2 (CVEs sin parche en Debian).
# upgrade: aplica los parches de seguridad de Debian disponibles sobre la
# imagen base (Snyk reportaba CVEs en zlib, brotli, libsasl2, etc.).
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependencias Python (capa cacheada independiente del código) ──────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Código de la aplicación ───────────────────────────────────────────────────
COPY . .

# Directorio para PDFs y logs generados en tiempo de ejecución (gitignored,
# self-regenerating — no se necesita volumen persistente)
RUN mkdir -p generated_labels

# ── Puertos expuestos (documentación; CMD se sobreescribe en ECS por servicio)
# 8000 FastAPI · 8001 MCP Supabase · 8002 MCP Logistics · 8501 Streamlit
EXPOSE 8000

# CMD por defecto: FastAPI.
# Los demás servicios sobreescriben este CMD en su ECS task definition:
#   MCP Supabase:  python -m backend.mcp.mcp_supabase
#   MCP Logistics: python -m backend.mcp.mcp_logistics
#   Streamlit:     streamlit run frontend/Chat.py --server.port=8501 ...
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
