#!/usr/bin/env bash
# Arranca Langfuse self-hosted (servidor + su propia Postgres) con Docker
# Compose. Comprueba antes que Docker esté instalado y el daemon arrancado,
# y crea el .env de esta carpeta desde la plantilla si todavía no existe.
#
# Uso:  ./start_langfuse.sh   (o  ./langfuse_infra/start_langfuse.sh  desde la raíz)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Docker instalado
if ! command -v docker >/dev/null 2>&1; then
    echo "No se encuentra el comando 'docker'." >&2
    echo "Instala Docker Desktop: https://www.docker.com/products/docker-desktop/" >&2
    echo "(Docker Compose v2 va incluido con Docker Desktop, no hace falta instalarlo aparte.)" >&2
    exit 1
fi

# 2. Subcomando 'docker compose' disponible (Compose v2, integrado en Docker Desktop)
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker está instalado pero 'docker compose' no responde." >&2
    echo "Actualiza Docker Desktop a una versión reciente (trae Compose v2 integrado)." >&2
    exit 1
fi

# 3. El daemon de Docker tiene que estar arrancado. Si no responde, se
# intenta abrir Docker Desktop automáticamente y se espera (con timeout) a
# que arranque, en vez de fallar directamente.
DOCKER_DESKTOP_EXE="/c/Program Files/Docker/Docker/Docker Desktop.exe"
DAEMON_WAIT_TIMEOUT=120  # segundos

if ! docker info >/dev/null 2>&1; then
    if [ -f "$DOCKER_DESKTOP_EXE" ]; then
        echo "==> El daemon de Docker no responde. Abriendo Docker Desktop..."
        "$DOCKER_DESKTOP_EXE" >/dev/null 2>&1 &
        disown 2>/dev/null || true

        echo -n "==> Esperando a que el daemon arranque (hasta ${DAEMON_WAIT_TIMEOUT}s)"
        elapsed=0
        until docker info >/dev/null 2>&1; do
            if [ "$elapsed" -ge "$DAEMON_WAIT_TIMEOUT" ]; then
                echo
                echo "El daemon sigue sin responder tras ${DAEMON_WAIT_TIMEOUT}s." >&2
                echo "Abre Docker Desktop a mano y espera a que el icono de la ballena se ponga verde, luego reintenta." >&2
                exit 1
            fi
            echo -n "."
            sleep 3
            elapsed=$((elapsed + 3))
        done
        echo
        echo "==> Docker Desktop arrancado."
    else
        echo "Docker está instalado pero el daemon no responde, y no se encuentra" >&2
        echo "Docker Desktop en la ruta esperada ($DOCKER_DESKTOP_EXE)." >&2
        echo "Ábrelo a mano (o edita DOCKER_DESKTOP_EXE en este script con la ruta correcta) y reintenta." >&2
        exit 1
    fi
fi

# 4. .env de esta carpeta (secretos del stack de Langfuse, no los de la app)
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "==> No existe .env en langfuse_infra/, copiando .env.example -> .env"
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    echo "    AVISO: rellena los secretos (POSTGRES_PASSWORD, CLICKHOUSE_PASSWORD,"
    echo "    MINIO_ROOT_PASSWORD, REDIS_AUTH, NEXTAUTH_SECRET, SALT, ENCRYPTION_KEY)"
    echo "    y el bloque LANGFUSE_INIT_* en langfuse_infra/.env antes de continuar"
    echo "    (ver README.md, Paso 2)."
    exit 1
fi

# 5. Arrancar los contenedores
echo "==> Arrancando Langfuse (6 contenedores: Postgres, ClickHouse, Redis, MinIO,"
echo "    langfuse-web, langfuse-worker). La primera vez tarda un poco, descarga las imágenes."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d

echo
echo "==> Comprobando estado de los contenedores..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" ps

cat <<EOF

==> Listo. Langfuse corriendo en http://localhost:3000

    Si rellenaste el bloque LANGFUSE_INIT_* del .env de esta carpeta, tu
    usuario/organización/proyecto/API-keys ya están creados: entra
    directamente con LANGFUSE_INIT_USER_EMAIL / _PASSWORD. Si no, regístrate
    a mano (el primer usuario es admin) y genera las keys en
    Settings -> API Keys.

    Copia LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST al .env
    de la RAÍZ del proyecto y reinicia el backend (./stop_all.sh &&
    ./start_all.sh) para que las recoja.

    Para pararlo: ./stop_langfuse.sh
EOF
