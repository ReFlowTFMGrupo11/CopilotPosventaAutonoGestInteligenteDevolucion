#!/usr/bin/env bash
# Arranca ReFlow completo: para procesos anteriores, activa el entorno
# virtual y levanta los 4 servicios en background.
#
# Compatible con macOS y Linux.
# Uso:  ./scripts/start_mac.sh          (o ./deploy.sh local)
#       ./scripts/start_mac.sh stop     (para todos los servicios)
set -euo pipefail

# El script vive en scripts/, pero .venv/, .env y requirements.txt están en
# la raíz del repo: subimos un nivel.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PIDFILE="$REPO_ROOT/.reflow_pids"

# ── Función stop: mata los procesos anteriores ─────────────────────────────
stop_services() {
    if [ -f "$PIDFILE" ]; then
        echo "==> Parando servicios anteriores..."
        while read -r pid; do
            kill "$pid" 2>/dev/null && echo "    Parado PID $pid" || true
        done < "$PIDFILE"
        rm -f "$PIDFILE"
    fi
    # Matar por puerto por si quedó algo huérfano
    for port in 8000 8001 8002 8501; do
        lsof -ti :"$port" 2>/dev/null | xargs kill 2>/dev/null || true
    done
}

if [ "${1:-}" = "stop" ]; then
    stop_services
    echo "==> Todos los servicios parados."
    exit 0
fi

# ── Parar lo anterior antes de arrancar ────────────────────────────────────
stop_services

# 1. Entorno virtual
if [ ! -f "$REPO_ROOT/.venv/bin/activate" ]; then
    echo "==> Creando entorno virtual .venv..."
    python3 -m venv .venv
fi
source "$REPO_ROOT/.venv/bin/activate"

# 2. Dependencias
echo "==> Instalando/actualizando dependencias..."
pip install -q -r requirements.txt

# 3. Variables de entorno
if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "==> No existe .env, copiando .env.example -> .env"
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
    echo "    AVISO: edita .env con tus credenciales reales antes de usar la app."
fi

# 4. Configurar Streamlit headless (evita prompt de email)
mkdir -p ~/.streamlit
cat > ~/.streamlit/credentials.toml <<TOML
[general]
email = ""
TOML

# 5. Lanzar servicios en background
> "$PIDFILE"

echo "==> Lanzando MCP Supabase (http://localhost:8001/mcp)..."
python -m backend.mcp.mcp_supabase > /tmp/reflow_mcp_supabase.log 2>&1 &
echo $! >> "$PIDFILE"
sleep 2

echo "==> Lanzando MCP Logistics (http://localhost:8002/mcp)..."
python -m backend.mcp.mcp_logistics > /tmp/reflow_mcp_logistics.log 2>&1 &
echo $! >> "$PIDFILE"
sleep 2

echo "==> Lanzando API FastAPI (http://localhost:8000)..."
python -m backend.api.run --reload --port 8000 > /tmp/reflow_api.log 2>&1 &
echo $! >> "$PIDFILE"
sleep 3

echo "==> Lanzando frontend Streamlit (http://localhost:8501)..."
streamlit run frontend/app.py --server.port 8501 --server.headless true > /tmp/reflow_streamlit.log 2>&1 &
echo $! >> "$PIDFILE"

cat <<EOF

==> ¡Listo! Servicios corriendo:
      - MCP Supabase   -> http://localhost:8001/mcp
      - MCP Logistics  -> http://localhost:8002/mcp
      - API FastAPI    -> http://localhost:8000 (docs en /docs)
      - Frontend       -> http://localhost:8501

    Logs en /tmp/reflow_*.log
    Para parar todo:  ./deploy.sh local stop  (o ./scripts/start_mac.sh stop)
EOF
