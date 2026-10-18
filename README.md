# ReFlow — Copiloto de Posventa Autónomo y Gestión Inteligente de Devoluciones

TFM — sistema multi-agente de IA Generativa para automatizar la gestión de devoluciones en e-commerce.
Stack: **LangGraph** · **MCP** · **Supabase** (PostgreSQL + pgvector) · **OpenAI** · **FastAPI** · **Streamlit** · **AWS ECS Fargate**

> 📐 [Diagrama de arquitectura](docs/architecture.drawio)

---

## Configuración inicial (una sola vez)

### 1. Clonar y crear entorno virtual

```bash
git clone https://github.com/ReFlowTFMGrupo11/CopilotPosventaAutonoGestInteligenteDevolucion.git
cd CopilotPosventaAutonoGestInteligenteDevolucion

python3 -m venv .venv
source .venv/bin/activate          # Mac/Linux
# source .venv/Scripts/activate    # Windows Git Bash
pip install -r requirements.txt
```

### 2. Variables de entorno

```bash
cp .env.example .env
```

Edita `.env` con tus valores:

```
SUPABASE_URL=https://<proyecto>.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
SUPABASE_DB_URL=postgresql://postgres:<pwd>@<host>:5432/postgres
OPENAI_API_KEY=sk-proj-...
JWT_SECRET=<openssl rand -hex 32>
ADMIN_PASSWORD=<contraseña-del-panel-admin>
```

---

## Levantar en local — Mac / Linux

```bash
./deploy.sh local        # arranca los 4 servicios en background
./deploy.sh local stop   # para todo
```

- Chat cliente: http://localhost:8501
- API (Swagger): http://localhost:8000/docs

Login en el frontend: email de un cliente de la BD (ej. `claudia.flores@outlook.com`).
Login admin: contraseña del `ADMIN_PASSWORD` del `.env`.

---

## Levantar en local — Windows (Git Bash)

```bash
./scripts/start_win.sh   # abre 4 ventanas Git Bash, una por servicio
./scripts/stop_win.sh    # cierra todas las ventanas
```

Requisitos: [Python 3.12](https://python.org) + [Git for Windows](https://git-scm.com).

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
frontend/         Streamlit (chat cliente + panel admin)
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
