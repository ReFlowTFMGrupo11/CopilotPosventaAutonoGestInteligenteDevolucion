# ReFlow — Copiloto de Posventa Autónomo y Gestión Inteligente de Devoluciones

> 📐 [Ver diagrama de arquitectura (Draw.io)](docs/architecture.drawio)

TFM que propone "ReFlow", un sistema de agentes de IA Generativa para automatizar la
gestión de devoluciones y el soporte posventa en e-commerce. La arquitectura combina
**LangGraph** (orquestación multi-agente con estado compartido y memoria persistente),
**MCP (Model Context Protocol)** como capa de herramientas hacia **Supabase**
(PostgreSQL + pgvector para RAG sobre políticas de devolución), y modelos de OpenAI
como motor de razonamiento.

## Estado del proyecto

| Bloque | Estado |
|---|---|
| Esquema Supabase (PostgreSQL + pgvector) — `supabase/` | ✅ |
| Servidor MCP de datos y políticas — `backend/mcp/mcp_supabase.py` | ✅ |
| Servidor MCP de logística — `backend/mcp/mcp_logistics.py` | ✅ |
| Grafo LangGraph (Triaje → Evaluador → Resolución) — `backend/agents/` | ✅ |
| HITL con `interrupt()` para reembolsos >100€ | ✅ |
| Memoria conversacional persistente (checkpointer PostgreSQL) | ✅ |
| Backend FastAPI (endpoints de chat y panel admin/HITL) — `backend/api/` | ✅ |
| Autenticación JWT (cliente por email, admin por contraseña) | ✅ |
| Frontend Streamlit (chat cliente + dashboard admin) — `frontend/` | ✅ |
| Observabilidad LLM (Langfuse Cloud) | ✅ (opcional) |
| Dockerfiles por servicio (api, mcp, frontend) | ✅ |
| Infraestructura AWS ECS Fargate (Terraform) — `infra/` | ✅ |

---

## Arranque rápido

### Mac / Linux

```bash
./deploy.sh local         # arranca los 4 servicios en background
./deploy.sh local stop    # para todo
```

### Windows (Git Bash)

```bash
./scripts/start_win.sh    # abre 4 ventanas Git Bash, una por servicio
./scripts/stop_win.sh     # cierra todas las ventanas
```

### Despliegue en AWS ECS Fargate

```bash
./deploy.sh aws <nombre-cuenta>          # crea infra + sube imágenes + arranca
./deploy.sh aws <nombre-cuenta> destroy  # destruye todo (para no generar costes)
```

> Ver sección [Despliegue en AWS](#despliegue-en-aws-ecs-fargate) para el detalle completo.

---

## Configuración inicial (primera vez)

### 1. Entorno virtual y dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt
```

### 2. Variables de entorno

```bash
cp .env.example .env
```

Edita `.env` con tus valores reales:

```
SUPABASE_URL=https://<tu-proyecto>.supabase.co
SUPABASE_SERVICE_KEY=<tu-service-role-key>
SUPABASE_DB_URL=postgresql://postgres:<password>@<host>:5432/postgres
OPENAI_API_KEY=<tu-openai-api-key>

# Autenticación JWT
JWT_SECRET=<genera con: openssl rand -hex 32>
ADMIN_PASSWORD=<contraseña del panel de admin>
```

### 3. Verificar conexión a Supabase (opcional)

```bash
python -c "
import asyncio
from backend.db.supabase_client import get_supabase_client
async def test():
    client = await get_supabase_client()
    result = await client.table('customers').select('id').limit(1).execute()
    print('Conexión exitosa:', result.data)
asyncio.run(test())
"
```

---

## Autenticación JWT

Todos los endpoints de `/api/chat/*` y `/api/admin/*` requieren un token JWT
en la cabecera `Authorization: Bearer <token>`.

### Obtener un token

```bash
# Cliente (login por email — debe existir en la tabla customers)
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "ana.garcia@email.com"}'
# → {"token": "eyJhbGci...", "customer_id": "CLI-001"}

# Administrador (login por contraseña)
curl -X POST http://localhost:8000/api/auth/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password": "tu-admin-password"}'
# → {"token": "eyJhbGci..."}
```

### Usar el token

```bash
TOKEN="eyJhbGci..."

curl -X POST http://localhost:8000/api/chat/new \
  -H "Authorization: Bearer $TOKEN"

curl http://localhost:8000/api/admin/pending \
  -H "Authorization: Bearer $TOKEN"
```

El frontend gestiona el token automáticamente: muestra un formulario de login
al arrancar y lo pasa en cada llamada.

---

## Estructura del repositorio

```
backend/
  models/        Modelos Pydantic de dominio (returns.py) + estado LangGraph (state.py)
  api/           FastAPI
    main.py        App, lifespan, CORS, registro de routers
    schemas.py     DTOs de request/response
    dependencies.py  get_graph(), require_authenticated_customer(), require_admin()
    routers/
      auth.py      POST /api/auth/login  y  /api/auth/admin/login
      chat.py      POST /api/chat/*  (requiere token cliente)
      admin.py     GET/POST /api/admin/*  (requiere token admin)
      usage.py     GET /api/admin/usage/*
  agents/
    graph.py       StateGraph + routing determinista + checkpointer
    nodes/         triage.py, evaluator.py, policy_rules.py, resolution.py
    infra/         mcp_client.py (cliente MCP unificado)
  services/      Lógica de negocio pura (sin MCP/LLM)
    auth_service.py   create_token(), verify_token(), AuthError
    orders_service.py, returns_service.py, logistics_service.py, ...
  mcp/           Servidores MCP — wrappers finos sobre services/ (:8001 y :8002)
  db/            supabase_client.py — singleton cacheado
  config.py      Settings centralizadas (pydantic-settings)

frontend/
  app.py           Punto de entrada Streamlit (st.navigation, navegación condicional)
  Chat.py          Chat del cliente (login por email + streaming SSE)
  pages/
    1_Admin.py     Panel de administración (login por contraseña + HITL)
    2_Costes.py    Dashboard de costes LLM
  lib/
    api.py         Cliente HTTP hacia FastAPI (todas las funciones con token)
    styles.py      CSS y helpers visuales

infra/             Terraform — infraestructura AWS ECS Fargate
  main.tf            Provider AWS + tags Environment=tfm
  variables.tf       aws_region, desired_count, allowed_cidr_blocks
  data.tf            aws_caller_identity
  outputs.tf         URLs, comandos docker push, cluster_name
  vpc.tf             VPC tfm-reflow, subnets pública/privada, NAT Gateway
  ecr.tf             3 repositorios ECR (reflow-api, reflow-mcp, reflow-frontend)
  iam.tf             Roles ECS execution + task
  secrets.tf         Secrets Manager (JWT_SECRET, OPENAI_API_KEY, Supabase...)
  security_groups.tf Reglas de red alb→frontend→api→mcp
  alb.tf             ALB HTTP:80, target groups, routing /api/* → FastAPI
  ecs.tf             Cluster + 4 task definitions + 4 services + Service Connect

Dockerfile.api       Imagen FastAPI + LangGraph (~757 MB)
Dockerfile.mcp       Imagen MCP servers (~644 MB)
Dockerfile.frontend  Imagen Streamlit (~826 MB)
requirements/
  api.txt            Dependencias de Dockerfile.api
  mcp.txt            Dependencias de Dockerfile.mcp
  frontend.txt       Dependencias de Dockerfile.frontend
requirements.txt     Todas las dependencias (desarrollo local + CI)

scripts/
  start_mac.sh       Arranca los 4 servicios en background (Mac/Linux)
  start_win.sh       Arranca 4 ventanas Git Bash separadas (Windows)
  stop_win.sh        Cierra las ventanas Git Bash (Windows)
  sync_prompts_to_langfuse.py
  manual_checks/

deploy.sh            Script unificado: local | aws <cuenta> | aws <cuenta> destroy

data/              Dataset sintético + corpus de políticas RAG
supabase/          Migraciones SQL (001–017) + seed de datos
tests/             unit/ + integration/
evaluation/        Golden dataset + evaluación manual
docs/              Diagramas (architecture.drawio, graph_diagram.md, ER_diagram.md)
```

---

## API — Endpoints

Todos los endpoints excepto `/health` y `/api/auth/*` requieren
`Authorization: Bearer <token>`.

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/health` | — | Health check |
| POST | `/api/auth/login` | — | Login cliente por email → token |
| POST | `/api/auth/admin/login` | — | Login admin por contraseña → token |
| POST | `/api/chat/new` | cliente | Crear sesión de chat |
| POST | `/api/chat` | cliente | Enviar mensaje (respuesta JSON) |
| POST | `/api/chat/stream` | cliente | Enviar mensaje (SSE streaming) |
| GET | `/api/chat/{id}/state` | cliente | Estado actual del grafo |
| GET | `/api/admin/pending` | admin | Devoluciones pendientes de HITL |
| POST | `/api/admin/{id}/approve` | admin | Aprobar devolución (reanuda grafo) |
| POST | `/api/admin/{id}/reject` | admin | Rechazar devolución |
| GET | `/api/admin/returns` | admin | Listar devoluciones |
| GET | `/api/orders/{id}` | admin | Detalle de pedido |
| GET | `/api/stats` | admin | KPIs generales |

Documentación interactiva: http://localhost:8000/docs (Swagger UI)

---

## Tests

```bash
pytest tests/              # todos
pytest tests/unit/         # solo unitarios
pytest tests/integration/  # solo integración
```

Los tests de endpoints usan `dependency_overrides` para bypasear el JWT
automáticamente — no necesitan token real.

---

## Despliegue en AWS ECS Fargate

### Prerequisitos (una sola vez)

- `terraform >= 1.6` — `brew install terraform`
- `aws` CLI — `brew install awscli`
- `docker` corriendo
- `stskeygen` configurado para la cuenta de pruebas
- `.env` con todos los valores reales

### Desplegar

```bash
./deploy.sh aws <nombre-cuenta>
```

El script hace en orden:
1. `stskeygen` — credenciales temporales AWS
2. `terraform apply` — crea VPC, ECR, ECS cluster, ALB, Secrets Manager...
3. Sincroniza `.env` → Secrets Manager automáticamente
4. `docker build + push` de las 3 imágenes a ECR
5. Espera a que los 4 servicios ECS estén healthy
6. Muestra la URL del ALB

### Restringir acceso por IP (recomendado en cuenta de trabajo)

```hcl
# infra/terraform.tfvars  (no se sube a git)
allowed_cidr_blocks = ["1.2.3.4/32"]   # tu IP: curl ifconfig.me
```

### Destruir todo al terminar

```bash
./deploy.sh aws <nombre-cuenta> destroy
# terraform destroy elimina TODOS los recursos en ~5 minutos
```

Coste estimado con `desired_count=1` y uso de ~1 hora: **< $0.20**.

---

## Observabilidad (Langfuse, opcional)

[Langfuse](https://langfuse.com) traza cada llamada al LLM (prompts, tokens,
latencia, coste). Es opcional: sin configurar, la app funciona igual sin trazas.

Usa Langfuse Cloud (tier gratuito): crea una cuenta en
[cloud.langfuse.com](https://cloud.langfuse.com), copia las keys al `.env`:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

---

## Linting y formato

```bash
black backend/ frontend/ data/ tests/        # formatear
black --check backend/ frontend/ data/ tests/ # comprobar (CI)
flake8 backend/ frontend/ data/ tests/        # linting
```
