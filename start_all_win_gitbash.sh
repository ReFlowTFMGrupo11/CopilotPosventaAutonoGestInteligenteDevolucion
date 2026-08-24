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

# Desactivar conda si está activo en esta terminal: su python/pip no deben
# usarse para crear el .venv del proyecto, y su activate.d suele dejar puesto
# SSL_CERT_FILE (a veces roto) que interfiere con las conexiones HTTPS/SSL.
if [ -n "${CONDA_PREFIX:-}" ]; then
    echo "==> Entorno conda activo detectado (${CONDA_DEFAULT_ENV:-desconocido}), desactivando..."
    if declare -F conda >/dev/null 2>&1; then
        # 'conda' está cargado como función de shell (conda init): usar
        # 'conda deactivate' tantas veces como niveles apilados haya.
        while [ -n "${CONDA_PREFIX:-}" ]; do
            conda deactivate
        done
    else
        # Sin la función de shell (script no interactivo): limpiar a mano lo
        # que deja puesto la activación de conda.
        PATH="$(printf '%s' "$PATH" | tr ':' '\n' | grep -vi '/conda' | paste -sd: -)"
        export PATH
        unset CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_SHLVL CONDA_PROMPT_MODIFIER CONDA_PYTHON_EXE
        unset SSL_CERT_FILE SSL_CERT_DIR __CONDA_OPENSSL_CERT_FILE_SET __CONDA_OPENSSL_CERT_DIR_SET
    fi
fi

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

# 3.5. Langfuse (opcional): solo se intenta si ya lo configuraste alguna vez
# (existe langfuse_docker/.env). Es observabilidad, no un requisito para que
# la app funcione, así que si Docker no está disponible o no arranca, se
# avisa y se continúa sin bloquear el resto de servicios.
if [ -f "$REPO_ROOT/langfuse_docker/.env" ]; then
    echo "==> Langfuse configurado, intentando levantarlo..."
    if ! "$REPO_ROOT/langfuse_docker/start_langfuse.sh"; then
        echo "    AVISO: no se pudo levantar Langfuse (¿Docker Desktop cerrado?). Continuando sin tracing."
    fi
else
    echo "==> Langfuse no configurado (opcional, ver langfuse_docker/README.md). Saltando."
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

    Cierra cada ventana (o Ctrl+C dentro de ella) para parar ese servicio,
    o ejecuta ./stop_all.sh para cerrarlas todas de golpe.
EOF
