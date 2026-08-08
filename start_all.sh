#!/usr/bin/env bash
# Arranca ReFlow completo: crea/actualiza el entorno virtual, instala
# dependencias y levanta los 4 procesos (MCP Supabase, MCP Logistics,
# API FastAPI y frontend Streamlit), cada uno en su propia ventana de
# Git Bash. Pensado para ejecutarse con Git Bash en Windows.
#
# Uso:  ./start_all.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

GIT_BASH="/c/Program Files/Git/git-bash.exe"
if [ ! -f "$GIT_BASH" ]; then
    echo "No se encuentra Git Bash en '$GIT_BASH'." >&2
    echo "Edita GIT_BASH en este script con la ruta correcta." >&2
    exit 1
fi

# 1. Entorno virtual
if [ ! -f "$REPO_ROOT/.venv/Scripts/activate" ]; then
    echo "==> Creando entorno virtual .venv..."
    python -m venv .venv
fi

# 2. Dependencias
echo "==> Instalando/actualizando dependencias (pip install -r requirements.txt)..."
"$REPO_ROOT/.venv/Scripts/python.exe" -m pip install -q -r requirements.txt

# 3. Variables de entorno
if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "==> No existe .env, copiando .env.example -> .env"
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
    echo "    AVISO: edita .env con tus credenciales reales antes de usar la app."
fi

# 4. Lanzar cada servicio en su propia ventana de Git Bash
launch() {
    local title="$1"
    local cmd="$2"
    "$GIT_BASH" -c "cd '$REPO_ROOT' && source .venv/Scripts/activate && printf '\\n== %s ==\\n\\n' '$title' && $cmd; echo; echo '[proceso terminado, pulsa Enter para cerrar]'; read" &
}

echo "==> Lanzando MCP Supabase (http://localhost:8001/mcp)..."
launch "MCP Supabase (8001)" "python -m backend.mcp.mcp_supabase"
sleep 2

echo "==> Lanzando MCP Logistics (http://localhost:8002/mcp)..."
launch "MCP Logistics (8002)" "python -m backend.mcp.mcp_logistics"
sleep 2

echo "==> Lanzando API FastAPI (http://localhost:8000)..."
launch "API FastAPI (8000)" "uvicorn backend.api.main:app --reload --port 8000"
sleep 3

echo "==> Lanzando frontend Streamlit (http://localhost:8501)..."
launch "Frontend Streamlit (8501)" "streamlit run frontend/Chat.py"

cat <<EOF

==> Listo. 4 ventanas de Git Bash abiertas:
      - MCP Supabase   -> http://localhost:8001/mcp
      - MCP Logistics  -> http://localhost:8002/mcp
      - API FastAPI    -> http://localhost:8000 (docs en /docs)
      - Frontend       -> http://localhost:8501

    Cierra cada ventana (o Ctrl+C dentro de ella) para parar ese servicio.
EOF
