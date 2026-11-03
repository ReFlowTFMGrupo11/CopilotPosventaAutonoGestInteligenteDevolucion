# ReFlow — Copiloto de Posventa Autónomo y Gestión Inteligente de Devoluciones

TFM — sistema multi-agente de IA Generativa para automatizar la gestión de devoluciones en e-commerce.
Stack: **LangGraph** · **MCP** · **Supabase** (PostgreSQL + pgvector) · **OpenAI** · **FastAPI** · **Streamlit** · **AWS ECS Fargate**

> 📐 [Diagrama de arquitectura](docs/architecture.drawio)

---

## Requisitos previos

| Requisito | Para qué |
|-----------|----------|
| [Python 3.12](https://python.org) | Backend, servidores MCP y frontend (la misma versión que usan las imágenes Docker) |
| [Git](https://git-scm.com) (en Windows, **Git for Windows**, que incluye Git Bash) | Clonar el repo y ejecutar los scripts `.sh` |
| Proyecto de [Supabase](https://supabase.com) (el plan gratuito es suficiente) | Base de datos PostgreSQL + `pgvector` |
| API key de [OpenAI](https://platform.openai.com) | Modelos de los agentes (`gpt-5-mini`) y embeddings del RAG |
| Cuenta de [Langfuse Cloud](https://cloud.langfuse.com) — *opcional* | Trazas de LLM; sin ella la app funciona igual |

---

## Configuración inicial (una sola vez)

### 1. Clonar y crear entorno virtual

```bash
git clone https://github.com/ReFlowTFMGrupo11/CopilotPosventaAutonoGestInteligenteDevolucion.git
cd CopilotPosventaAutonoGestInteligenteDevolucion

python3 -m venv .venv              # en Windows: python -m venv .venv
source .venv/bin/activate          # Mac/Linux
# source .venv/Scripts/activate    # Windows Git Bash
pip install -r requirements.txt
```

> Los scripts de arranque (`./deploy.sh local`, `./scripts/start_win.sh`) también crean el `.venv`
> e instalan las dependencias si no existen, así que este paso es opcional si vas a usarlos.

### 2. Variables de entorno

```bash
cp .env.example .env
```

Edita `.env`. Estas son las variables que hacen falta para arrancar (las de `JWT_SECRET`,
`ADMIN_PASSWORD` y `SUPABASE_DB_URL` vienen **comentadas** en `.env.example`: quita el `#`):

| Variable | ¿Obligatoria? | Dónde se obtiene / qué pasa si falta |
|----------|---------------|---------------------------------------|
| `SUPABASE_URL` | Sí | Supabase → *Project Settings* → *API* → *Project URL* |
| `SUPABASE_SERVICE_KEY` | Sí | Supabase → *Project Settings* → *API* → clave `service_role` (no la `anon`) |
| `OPENAI_API_KEY` | Sí | platform.openai.com → *API keys* |
| `JWT_SECRET` | Sí, para iniciar sesión | Genérala con `openssl rand -hex 32`. Sin ella, el login devuelve error 500 |
| `ADMIN_PASSWORD` | Sí, para el panel admin | La que elijas. Sin ella, el login de administrador devuelve error 500 |
| `SUPABASE_DB_URL` | Recomendada | Supabase → *Connect* → *Connection pooler* (puerto `6543`). Sin ella, la memoria de las conversaciones y las pausas HITL se guardan solo en RAM y se pierden al reiniciar la API |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | No | Langfuse Cloud. Sin ellas se desactiva el tracing |

```
SUPABASE_URL=https://<proyecto>.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
SUPABASE_DB_URL=postgresql://postgres.<ref>:<pwd>@<host>.pooler.supabase.com:6543/postgres
OPENAI_API_KEY=sk-proj-...
JWT_SECRET=<openssl rand -hex 32>
ADMIN_PASSWORD=<contraseña-del-panel-admin>
```

El resto de variables de `.env.example` (modelos por nodo, timeouts, umbral HITL, umbral RAG…) son
opcionales y ya tienen valores por defecto.

### 3. Base de datos en Supabase

Sin este paso la app arranca, pero no hay clientes, pedidos ni políticas: no podrás iniciar sesión
ni el RAG encontrará nada. Hazlo en este orden:

1. **Esquema** — En Supabase → *SQL Editor*, pega y ejecuta el contenido de
   [`supabase/run_all.sql`](supabase/run_all.sql) (las 17 migraciones de `supabase/migrations/`,
   incluida la extensión `vector`).
2. **Datos de prueba** — Ejecuta [`supabase/seed_synthetic.sql`](supabase/seed_synthetic.sql)
   (320 clientes, ~1.100 pedidos, 16 políticas de devolución, 480 devoluciones). Pesa ~1,1 MB; si el
   SQL Editor no lo acepta de una vez, cárgalo con `psql`:

   ```bash
   psql "<SUPABASE_DB_URL>" -f supabase/seed_synthetic.sql
   ```

3. **Embeddings de las políticas (RAG)** — Con el `.venv` activado y el `.env` relleno:

   ```bash
   python -m data.rag.ingest_policy_embeddings            # trocea data/rag/policies/*.md y llama a OpenAI
   # python -m data.rag.ingest_policy_embeddings --dry-run  # solo trocea y cuenta, sin coste
   ```

   Es idempotente: si lo repites, reemplaza los fragmentos en vez de duplicarlos.

Detalle del dataset y de cómo regenerarlo: [`data/README.md`](data/README.md).

---

## Levantar en local — Mac / Linux

```bash
./deploy.sh local        # arranca los 4 servicios en background
./deploy.sh local stop   # para todo
```

Logs de cada servicio en `/tmp/reflow_*.log`.

## Levantar en local — Windows (Git Bash)

```bash
./scripts/start_win.sh   # abre 4 ventanas Git Bash, una por servicio
./scripts/stop_win.sh    # cierra todas las ventanas
```

Si tienes Git instalado fuera de `C:\Program Files\Git`, edita la variable `GIT_BASH` al principio de
`scripts/start_win.sh`.

## Levantar a mano (cualquier sistema)

Si prefieres no usar los scripts, abre 4 terminales con el `.venv` activado, desde la raíz del repo, y
lánzalos **en este orden** (cada uno depende del anterior):

```bash
python -m backend.mcp.mcp_supabase                       # 1. MCP datos y políticas  → :8001/mcp
python -m backend.mcp.mcp_logistics                      # 2. MCP logística          → :8002/mcp
python -m backend.api.run --reload --port 8000           # 3. API FastAPI            → :8000
streamlit run frontend/app.py --server.port 8501         # 4. Frontend Streamlit     → :8501
```

> Usa `python -m backend.api.run` en vez de `uvicorn backend.api.main:app`: en Windows evita una
> espera de ~30 s al conectar con Postgres (explicado en `backend/api/run.py`). Y lanza
> `frontend/app.py`, no `Chat.py`: `app.py` es el que monta la navegación entre Chat, Admin y Costes.

## Comprobar que funciona

| Servicio | URL |
|----------|-----|
| Chat cliente | http://localhost:8501 |
| Panel admin | http://localhost:8501 → pestaña *Panel de administración* |
| API (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

- **Login cliente:** el email de cualquier cliente de la BD, p. ej. `claudia.flores@outlook.com`
  (viene en `seed_synthetic.sql`). No pide contraseña.
- **Login admin:** el valor de `ADMIN_PASSWORD` de tu `.env`.

## Problemas frecuentes

| Síntoma | Causa / solución |
|---------|------------------|
| `Address already in use` / puerto ocupado | Quedó un servicio de una ejecución anterior: `./deploy.sh local stop` (Mac/Linux) o `./scripts/stop_win.sh` (Windows) |
| El chat muestra un aviso de que el backend no responde | La API (`:8000`) no está levantada o falló al arrancar: revisa su log/ventana |
| Error 500 al iniciar sesión | Falta `JWT_SECRET` (o `ADMIN_PASSWORD` para el admin) en `.env` |
| "Email no encontrado" al iniciar sesión con un email de ejemplo | No se ha cargado `supabase/seed_synthetic.sql` (paso 3.2) |
| El agente nunca encuentra políticas | Falta la ingesta de embeddings (paso 3.3) |
| Windows: `FileNotFoundError` o errores SSL en `httpx` | Hay un `SSL_CERT_FILE` heredado (típico de conda). Ver el comentario `SSL_CERT_FILE` en `.env.example` |

---

## Desplegar en AWS ECS Fargate

### Requisitos (una sola vez)

- `terraform >= 1.6` — `brew install terraform`
- `aws` CLI — `brew install awscli`
- Docker corriendo
- Acceso a la cuenta AWS con perfil admin en `~/.aws/credentials`

### Paso 1 — Credenciales AWS

#### Cuenta personal (recomendado para evaluadores)

1. Crea una cuenta en [aws.amazon.com](https://aws.amazon.com) si no tienes una.
2. En la consola AWS → **IAM** → **Users** → crea un usuario con la política `AdministratorAccess`.
3. Genera una **Access Key** para ese usuario (IAM → Users → Security credentials → Create access key).
4. Configura las credenciales en tu máquina:

```bash
aws configure
# AWS Access Key ID: AKIA...
# AWS Secret Access Key: ...
# Default region name: eu-west-1
# Default output format: json
```

5. Verifica que funciona:

```bash
aws sts get-caller-identity
```

#### Cuenta corporativa con SSO/roles temporales

Si tu empresa usa herramientas propias para generar credenciales temporales,
asegúrate de que el perfil resultante tenga permisos de admin y configura
su nombre en `infra/terraform.tfvars`:

```bash
aws sts get-caller-identity --profile <tu-perfil-admin>
```

### Paso 2 — Configurar perfil e IP en `infra/terraform.tfvars` (no se sube a git)

```hcl
aws_profile         = "admin@admin"
allowed_cidr_blocks = ["<tu-ip>/32"]   # curl ifconfig.me
```

### Paso 3 — Desplegar todo

```bash
./deploy.sh aws
```

Hace en orden: `terraform apply` → sincroniza `.env` a Secrets Manager → `docker build + push` a ECR → espera a que los 4 servicios ECS estén healthy → muestra la URL.

Coste estimado por hora de uso: **< $0.20**.

### Parar y destruir al terminar

```bash
./deploy.sh aws destroy   # elimina TODOS los recursos en ~5 min, coste 0
```

### Solo sincronizar secrets (si cambias el `.env` sin recrear infra)

```bash
./deploy.sh secrets
```

---

## Estructura del repositorio

```
backend/          FastAPI + agentes LangGraph + servidores MCP + servicios
frontend/         Streamlit (app.py = entrada; chat cliente + panel admin + costes)
infra/            Terraform — VPC, ECR, ECS, ALB, Secrets Manager
scripts/          start_mac.sh · start_win.sh · stop_win.sh
deploy.sh         Script unificado: local | aws | aws destroy | secrets
Dockerfile.api    Imagen FastAPI + LangGraph
Dockerfile.mcp    Imagen MCP servers
Dockerfile.frontend Imagen Streamlit
requirements/     Dependencias por imagen Docker (api · mcp · frontend)
requirements.txt  Todas las dependencias (dev local + CI)
data/             Dataset sintético + políticas RAG
supabase/         Migraciones SQL + seed de datos
tests/            unit/ + integration/
docs/             Diagramas (architecture.drawio, ER_diagram.md, graph_diagram.md)
```

---

## Tests

```bash
pytest tests/unit tests/integration
```

---

## API — Endpoints principales

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/health` | — | Health check |
| POST | `/api/auth/login` | — | Login cliente por email |
| POST | `/api/auth/admin/login` | — | Login admin por contraseña |
| POST | `/api/chat/new` | cliente | Crear sesión de chat |
| POST | `/api/chat/stream` | cliente | Chat con streaming SSE |
| GET | `/api/admin/pending` | admin | Devoluciones pendientes HITL |
| POST | `/api/admin/{id}/approve` | admin | Aprobar devolución |
| POST | `/api/admin/{id}/reject` | admin | Rechazar devolución |

Swagger UI: http://localhost:8000/docs
