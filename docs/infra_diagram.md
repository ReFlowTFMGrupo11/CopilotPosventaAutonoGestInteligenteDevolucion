# Diagrama de Infraestructura Cloud (AWS ECS Fargate)

> Reflejo del código Terraform en `infra/` (11 archivos `.tf`).  
> Región: **eu-west-1**. Orquestación: **ECS Fargate** con Service Connect (AWS Cloud Map).  
> Script de despliegue end-to-end: `deploy.sh aws`.

## Topología de red y flujo de tráfico

```mermaid
graph TD
    USER([Usuario / Browser])

    subgraph AWS["AWS · eu-west-1"]

        subgraph VPC["VPC  10.0.0.0/16  ·  tfm-reflow"]

            ALB["ALB · sg_alb<br/>HTTP :80 → Target Group :8501<br/>Subnets públicas A + B"]

            subgraph PUB_A["Subnet pública A · 10.0.1.0/24 · eu-west-1a"]
                FRONTEND["reflow-frontend<br/>Streamlit :8501 · Fargate<br/>sg_frontend · 0.25 vCPU / 512 MB<br/>assign_public_ip = true"]
                NAT["NAT Gateway<br/>+ Elastic IP"]
            end

            subgraph PRIV_A["Subnet privada A · 10.0.10.0/24 · eu-west-1a"]
                API["reflow-api<br/>FastAPI :8000 · Fargate<br/>sg_api · 0.5 vCPU / 1024 MB"]
                MCP_S["reflow-mcp · mcp-supabase<br/>:8001 · Fargate<br/>sg_mcp · 0.25 vCPU / 512 MB"]
                MCP_L["reflow-mcp · mcp-logistics<br/>:8002 · Fargate<br/>sg_mcp · 0.25 vCPU / 512 MB"]
            end

            IGW[Internet Gateway]
        end

        subgraph SUPPORT["Servicios de soporte AWS"]
            ECR["ECR<br/>reflow-api · reflow-mcp · reflow-frontend"]
            SM["Secrets Manager<br/>reflow/* · 8 secretos"]
            CW["CloudWatch Logs<br/>4 log groups · 7 días"]
            IAM["IAM<br/>ecs-execution · ecs-task"]
        end

    end

    subgraph EXT["Servicios externos"]
        SUPABASE[("Supabase Cloud<br/>PostgreSQL + pgvector")]
        OPENAI["OpenAI API"]
        LANGFUSE["Langfuse Cloud"]
    end

    %% ── Flujo principal de tráfico ──────────────────────────────────────────
    USER -->|"HTTP :80"| ALB
    ALB -->|"Target Group :8501"| FRONTEND
    FRONTEND -->|"Service Connect<br/>http://fastapi:8000"| API
    API -->|"Service Connect<br/>http://mcp-supabase:8001/mcp"| MCP_S
    API -->|"Service Connect<br/>http://mcp-logistics:8002/mcp"| MCP_L

    %% ── Salida a Internet ────────────────────────────────────────────────────
    FRONTEND -->|":443 (ECR pull — IP pública)"| IGW
    API -->|":443 / :5432–:6543"| NAT
    MCP_S -->|":443 / :5432–:6543"| NAT
    MCP_L -->|":443 / :5432"| NAT
    NAT --> IGW
    IGW --> SUPABASE
    IGW --> OPENAI
    IGW --> LANGFUSE

    %% ── Servicios de soporte ─────────────────────────────────────────────────
    SM -.->|"vars inyectadas al arrancar"| API
    SM -.-> MCP_S
    SM -.-> MCP_L
    ECR -.->|"image pull"| FRONTEND
    ECR -.-> API
    ECR -.-> MCP_S
    ECR -.-> MCP_L
    FRONTEND -.->|"logs"| CW
    API -.-> CW
    MCP_S -.-> CW
    MCP_L -.-> CW
    IAM -.->|"permite pull ECR<br/>lectura SM · escritura CW"| API
```

> **Nota sobre la subnet pública B** (`10.0.2.0/24 · eu-west-1b`): AWS exige al menos
> dos zonas de disponibilidad para un ALB; esta subnet solo sirve como segunda AZ del
> balanceador y no aloja ninguna tarea ECS.

## Servicios ECS

| Servicio | Imagen ECR | CPU / RAM | Subnet | IP pública | Puerto | Health check path |
|----------|-----------|-----------|--------|:----------:|--------|-------------------|
| `fastapi` | `reflow-api:latest` | 512 / 1024 MB | privada A | No | :8000 | `GET /health` |
| `mcp-supabase` | `reflow-mcp:latest` | 256 / 512 MB | privada A | No | :8001 | `GET /mcp` |
| `mcp-logistics` | `reflow-mcp:latest` | 256 / 512 MB | privada A | No | :8002 | `GET /mcp` |
| `frontend` | `reflow-frontend:latest` | 256 / 512 MB | pública A | Sí | :8501 | `GET /_stcore/health` |

Todos los servicios tienen `desired_count = 1` (variable `var.desired_count`).

## Service Connect (AWS Cloud Map)

Comunicación interna sin DNS externo. El cluster ECS usa un namespace HTTP de Cloud Map
(`tfm-reflow`) y cada servicio publica un alias DNS resolvible solo dentro del cluster:

| Alias DNS interno | Puerto | Llamante | Receptor |
|-------------------|--------|----------|----------|
| `http://fastapi:8000` | :8000 | `frontend` | `fastapi` |
| `http://mcp-supabase:8001/mcp` | :8001 | `fastapi` | `mcp-supabase` |
| `http://mcp-logistics:8002/mcp` | :8002 | `fastapi` | `mcp-logistics` |

El frontend no expone ningún alias (solo actúa como cliente de `fastapi`).

## Security groups

| Security group | Ingreso | Egreso |
|----------------|---------|--------|
| `sg_alb` | :80 / :443 desde `allowed_cidr_blocks` | :8501 → `sg_frontend` |
| `sg_frontend` | :8501 desde `sg_alb` | :8000 → `sg_api`; :443 (ECR pull directo) |
| `sg_api` | :8000 desde `sg_frontend` | :8001 / :8002 → `sg_mcp`; :443 (Supabase / OpenAI / ECR); :5432–:6543 (Postgres Supabase) |
| `sg_mcp` | :8001 / :8002 desde `sg_api` | :443 (Supabase / OpenAI / ECR); :5432–:6543 (Postgres Supabase) |

## Repositorios ECR y Dockerfiles

| Repositorio | Dockerfile fuente | CMD por defecto | Política de retención |
|-------------|------------------|-----------------|----------------------|
| `reflow-api` | `Dockerfile.api` | `uvicorn backend.api.main:app --port 8000` | Últimas 5 etiquetas; sin etiqueta → 1 día |
| `reflow-mcp` | `Dockerfile.mcp` | Override por task definition ECS (supabase / logistics) | Últimas 5 etiquetas; sin etiqueta → 1 día |
| `reflow-frontend` | `Dockerfile.frontend` | `streamlit run app.py --port 8501` | Últimas 5 etiquetas; sin etiqueta → 1 día |

Todos los repositorios usan etiquetas `MUTABLE` (`:latest` se sobreescribe en cada push)
y tienen `scan_on_push = true` para escaneo gratuito de vulnerabilidades.

## Secrets Manager

Secretos creados con valor `CHANGE_ME` por `terraform apply`. Se rellenan con valores reales
mediante `deploy.sh secrets` (lee `.env` y llama a `aws secretsmanager put-secret-value`).  
Terraform solo gestiona la creación: `lifecycle { ignore_changes = [secret_string] }`.

| Secreto | Variable de entorno | Inyectado en |
|---------|---------------------|-------------|
| `reflow/openai-api-key` | `OPENAI_API_KEY` | fastapi, mcp-supabase |
| `reflow/supabase-url` | `SUPABASE_URL` | fastapi, mcp-supabase, mcp-logistics |
| `reflow/supabase-service-key` | `SUPABASE_SERVICE_KEY` | fastapi, mcp-supabase, mcp-logistics |
| `reflow/supabase-db-url` | `SUPABASE_DB_URL` | fastapi |
| `reflow/jwt-secret` | `JWT_SECRET` | fastapi |
| `reflow/admin-password` | `ADMIN_PASSWORD` | fastapi |
| `reflow/langfuse-secret-key` | `LANGFUSE_SECRET_KEY` | fastapi, mcp-supabase |
| `reflow/langfuse-public-key` | `LANGFUSE_PUBLIC_KEY` | fastapi, mcp-supabase |

## IAM

| Rol | Permisos principales | Propósito |
|-----|---------------------|-----------|
| `reflow-tfm-ecs-execution` | `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `secretsmanager:GetSecretValue`, `logs:CreateLogStream / PutLogEvents` | Infraestructura ECS: pull de imágenes, lectura de secretos, escritura de logs |
| `reflow-tfm-ecs-task` | (ninguno actualmente) | Permisos de aplicación en runtime — separación intencional, reservado para extensiones futuras |

El rol de GitHub Actions OIDC (`reflow-tfm-github-actions`) está pendiente de aprobación
corporativa; la infraestructura de datos fuente está en `infra/iam.tf` (comentada) y
`infra/data.tf`.

## Flujo de despliegue (`deploy.sh aws`)

```
terraform apply
   └─► crea VPC · subnets · IGW · NAT · ALB · ECR · ECS cluster · Secrets Manager · IAM · CWLogs

deploy.sh secrets
   └─► lee .env → aws secretsmanager put-secret-value (8 secretos)

docker build --platform linux/amd64 + push → ECR
   ├─► Dockerfile.api     → reflow-api:latest
   ├─► Dockerfile.mcp     → reflow-mcp:latest
   └─► Dockerfile.frontend → reflow-frontend:latest

aws ecs wait services-stable
   └─► espera a que los 4 servicios ECS arranquen con las nuevas imágenes

terraform output alb_url  →  http://<alb-dns>.eu-west-1.elb.amazonaws.com
```
