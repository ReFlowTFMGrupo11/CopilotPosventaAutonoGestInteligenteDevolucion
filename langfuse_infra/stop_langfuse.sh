#!/usr/bin/env bash
# Para los contenedores de Langfuse levantados por start_langfuse.sh.
# No borra los datos guardados (trazas, usuarios, proyectos) salvo que
# pases --volumes / -v, que además elimina la base de datos de Langfuse.
#
# Uso:  ./stop_langfuse.sh          (para los contenedores, conserva los datos)
#       ./stop_langfuse.sh -v       (para los contenedores Y borra los datos)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "Docker no está disponible o no está arrancado; no hay nada que parar." >&2
    exit 0
fi

docker compose -f "$SCRIPT_DIR/docker-compose.yml" down "$@"

echo "==> Langfuse detenido."
