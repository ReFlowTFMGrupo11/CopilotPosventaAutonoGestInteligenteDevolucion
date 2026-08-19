# Langfuse (observabilidad de LLM) — self-hosted con Docker

Esta carpeta agrupa todo lo relacionado con [Langfuse](https://langfuse.com):
traza cada llamada al LLM dentro del grafo de agentes (prompts, respuestas,
tokens, latencia, coste, tool calls) para poder depurar y auditar
conversaciones desde un panel web, en vez de solo leer logs de consola.

## Qué hay en esta carpeta

| Archivo | Para qué |
|---|---|
| `docker-compose.yml` | Levanta el stack Langfuse v4 completo (Postgres + ClickHouse + Redis + MinIO + langfuse-web/worker), en local. |
| `.env.example` | Plantilla de variables para el docker-compose (secretos de cada servicio + bootstrap automático). |
| `start_langfuse.sh` | Comprueba que Docker esté instalado y arrancado, y hace `docker compose up -d`. |
| `stop_langfuse.sh` | Hace `docker compose down` (con `-v` si además quieres borrar los datos). |
| `tracing.py` | El único punto de integración con el código de la app: crea el `CallbackHandler` de Langfuse y lo añade al `config` que se le pasa al grafo de LangGraph. |
| `__init__.py` | Hace de `langfuse_docker` un paquete Python importable desde `backend/`. |

**Por qué una carpeta aparte y no dentro de `backend/agents/`:** todo lo que
toca a Langfuse (infraestructura Docker + el pequeño adaptador Python) vive
junto, igual que `data/rag/` agrupa lo del RAG o `backend/mcp/` agrupa los
servers MCP. Se llama `langfuse_docker` (no `langfuse`) a propósito: un
paquete Python con el mismo nombre que la librería instalada (`pip install
langfuse`) taparía a esa librería al hacer `import langfuse` desde la raíz
del proyecto.

### Por qué este stack (Postgres+ClickHouse+Redis+MinIO) y no algo más simple

La primera versión de esta carpeta usaba solo Postgres (self-host "v2" de
Langfuse), pero no funcionaba: el SDK de Python `langfuse` 4.x (el que
resulta compatible con `langchain>=1.3.0`, ya usado en el resto del
proyecto) envía las trazas por OpenTelemetry a un endpoint que **solo
existe en el servidor Langfuse v3+**, y ese servidor necesita Postgres
(datos relacionales) + ClickHouse (analítica de trazas) + Redis (colas de
ingesta) + almacenamiento tipo S3 (MinIO, para eventos/adjuntos). No hay
combinación más ligera que hable el mismo protocolo que el SDK 4.x — la
alternativa (bajar el SDK a la serie 2.x) rompe porque esa versión antigua
importa `langchain.callbacks.base`, una ruta que ya no existe en
`langchain` 1.x.

## Cómo levantarlo (paso a paso)

### Requisito previo: tener Docker instalado y arrancado

Necesitas Docker con el subcomando `docker compose` disponible. Cómo
instalarlo depende del sistema operativo:

- **Windows** (el caso de este proyecto, pensado para Git Bash):
  instala **Docker Desktop**: https://www.docker.com/products/docker-desktop/
  Docker Compose v2 va incluido, no hace falta instalarlo aparte.
  `start_langfuse.sh` detecta si el daemon no está arrancado y, si
  Docker Desktop está instalado en la ruta habitual
  (`C:\Program Files\Docker\Docker\Docker Desktop.exe`), lo abre él
  mismo y espera a que arranque (hasta 2 minutos) antes de continuar —
  no hace falta abrirlo a mano salvo que falle esa ruta automática.

- **macOS**: también **Docker Desktop**:
  https://www.docker.com/products/docker-desktop/ (o `brew install --cask docker`).
  Ábrelo desde Launchpad/Spotlight antes de ejecutar el script — a
  diferencia de Windows, aquí el script no lo abre automáticamente.

- **Linux**: no hace falta Docker Desktop, con el **motor de Docker** +
  el plugin de Compose basta. Por ejemplo, en Ubuntu/Debian:
  ```
  sudo apt install docker.io docker-compose-plugin
  sudo systemctl enable --now docker
  ```
  En distros basadas en Fedora/RHEL: `sudo dnf install docker-ce docker-compose-plugin`
  y también `sudo systemctl enable --now docker`. El daemon corre como
  servicio del sistema (no como una app de escritorio), así que si no
  responde, arráncalo con `sudo systemctl start docker` en vez de abrir
  ninguna aplicación.

Sea cual sea el sistema, comprueba que todo está listo con:

```
docker info
```

Si da un error tipo "no se puede conectar al daemon de Docker", el daemon
no está arrancado — sigue las instrucciones de tu sistema operativo arriba.

**Recursos**: este stack son 6 contenedores (Postgres, ClickHouse, Redis,
MinIO, langfuse-web, langfuse-worker). La primera vez tarda unos minutos en
descargar las imágenes; en máquinas con poca RAM puede ir justo — cierra
otras apps pesadas si Docker Desktop se queda corto de memoria.

### Paso 1 — Crear tu `.env` para Langfuse

Este `.env` es **distinto** del `.env` de la raíz del proyecto: solo lo lee
`docker-compose.yml`, sirve para configurar el stack de Langfuse, no la app
ReFlow. Cópialo desde la plantilla, dentro de esta misma carpeta:

```
cd langfuse_docker
cp .env.example .env
```

### Paso 2 — Rellenar los secretos

`docker-compose.yml` no arranca si falta alguno de los secretos marcados
como obligatorios en `.env.example` (a propósito, para no arrancar con
algo en blanco): `POSTGRES_PASSWORD`, `CLICKHOUSE_PASSWORD`,
`MINIO_ROOT_PASSWORD`, `REDIS_AUTH`, `NEXTAUTH_SECRET`, `SALT` y
`ENCRYPTION_KEY`. Genera cada uno:

- Si tienes `openssl` (Git Bash lo trae):
  ```
  openssl rand -base64 32          # para POSTGRES_PASSWORD, CLICKHOUSE_PASSWORD,
                                    # MINIO_ROOT_PASSWORD, REDIS_AUTH, NEXTAUTH_SECRET, SALT
  openssl rand -hex 32             # solo para ENCRYPTION_KEY (formato fijo, 32 bytes hex)
  ```
- Si no, con Python (ya lo tienes instalado para el proyecto):
  ```
  python -c "import secrets; print(secrets.token_urlsafe(32))"   # los 6 primeros
  python -c "import secrets; print(secrets.token_hex(32))"       # ENCRYPTION_KEY
  ```

**Además**, rellena el bloque `LANGFUSE_INIT_*` del `.env.example` (org,
proyecto, usuario admin, y el par de API keys que tú elijas). Con eso
relleno, Langfuse se auto-configura en el primer arranque — te ahorras los
pasos de registrarte en la UI y generar las keys a mano que hacía falta en
la versión anterior de este README:

```
python -c "import secrets; print('pk-lf-' + secrets.token_hex(16))"
python -c "import secrets; print('sk-lf-' + secrets.token_hex(16))"
```

Copia ese mismo par de claves, más `LANGFUSE_HOST=http://localhost:3000`,
al **`.env` de la RAÍZ del proyecto** (el mismo donde ya tienes
`OPENAI_API_KEY`, `SUPABASE_*`, etc. — no en el `.env` de esta carpeta):

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

### Paso 3 — Arrancar los contenedores

```
./langfuse_docker/start_langfuse.sh
```

El script comprueba, en orden, que: (1) `docker` esté instalado, (2)
`docker compose` responda, y (3) el daemon de Docker esté arrancado (y en
Windows, si no lo está, abre Docker Desktop él mismo). Si todo está bien,
arranca los 6 contenedores (`-d` = segundo plano, no bloquea la terminal) y
al final imprime su estado — deberías ver los 6 como `running` (o
`healthy`; ClickHouse/MinIO/Redis tardan unos segundos en pasar el
healthcheck antes de que `langfuse-web`/`langfuse-worker` arranquen, es
normal que tarde un poco más que un `docker compose up` de un solo
servicio).

### Paso 4 — Reiniciar el backend

Las variables de entorno solo se leen al arrancar cada proceso, así que hay
que reiniciar para que las recoja:

```
./stop_all.sh
./start_all.sh
```

(o, si usas la tarea de VS Code: "Terminal → Kill All Terminals" y vuelve a
lanzar "ReFlow: Start All").

### Paso 5 — Verificar que llegan trazas

Abre **http://localhost:3000** — con el bootstrap del Paso 2 ya puedes
entrar directamente con el `LANGFUSE_INIT_USER_EMAIL` / `_PASSWORD` que
elegiste, sin pasar por ningún registro. Manda un mensaje de prueba por el
chat de Streamlit (http://localhost:8501); en unos segundos debería
aparecer una traza nueva en **Traces**, con el detalle de cada llamada al
LLM dentro del grafo (prompt, respuesta, tokens, tiempo).

Si no aparece nada, revisa la consola del backend (ventana "API FastAPI
(8000)"): si ves el mensaje `Langfuse no configurado`, significa que las
claves del Paso 2 no están en el `.env` de la raíz o el backend no se
reinició. Si el mensaje no aparece pero tampoco hay trazas, comprueba que
`LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `_SECRET_KEY` del `.env` de esta
carpeta coinciden EXACTAMENTE con `LANGFUSE_PUBLIC_KEY` / `_SECRET_KEY` del
`.env` de la raíz.

### Para pararlo

```
./langfuse_docker/stop_langfuse.sh
```

Añade `-v` al final (`./stop_langfuse.sh -v`) si además quieres borrar los
datos guardados (usuarios, proyectos, trazas) y empezar de cero la próxima
vez.

## Cómo está integrado en el código

Un único punto de enganche, en
[`backend/api/routers/chat.py`](../backend/api/routers/chat.py): los dos
sitios donde se invoca el grafo (`graph.ainvoke` en el endpoint síncrono y
`graph.astream` en el de streaming) construyen su `config` con
`with_langfuse(...)` en vez de un dict a pelo. Esa función:

- Si `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` no están en el entorno, o el
  paquete `langfuse` no está instalado, **devuelve el config tal cual**: la
  app sigue funcionando exactamente igual, sin trazas. Langfuse es opcional,
  no un requisito para arrancar ReFlow.
- Si están configuradas, añade el `CallbackHandler` de Langfuse a
  `config["callbacks"]` y etiqueta las trazas con el `thread_id` de la
  conversación como `langfuse_session_id`, para poder ver en el panel todos
  los turnos de una misma conversación agrupados.

No se ha tocado nada más: ni los nodos del grafo (`triage`, `evaluator`,
`resolver`...) ni los servers MCP saben que Langfuse existe — LangChain
propaga el callback automáticamente a cada llamada al LLM dentro del grafo,
aunque el nodo no reciba `config` como parámetro explícito (comprobado
empíricamente: LangGraph lo propaga vía contextvars).

## Nota sobre la base de datos

El `docker-compose.yml` levanta su **propia** Postgres (para Langfuse), no
usa la Supabase del proyecto. Son cosas independientes: si borras los
volúmenes de Langfuse no afecta a pedidos/devoluciones, y viceversa.
