# Diagrama de Infraestructura Cloud (AWS ECS Fargate)

> Reflejo del código Terraform en `infra/` (11 archivos `.tf`).  
> Región: **eu-west-1**. Orquestación: **ECS Fargate** con Service Connect (AWS Cloud Map).  
> Script de despliegue end-to-end: `deploy.sh aws`.

## Topología de red y flujo de tráfico

```mermaid
flowchart TD
    USER([Usuarios])

    subgraph REGION["Region: eu-west-1"]
        subgraph VPC["VPC  10.0.0.0/16  ·  tfm-reflow"]
            IGW([Internet Gateway])
            SGALB["sg_alb  ·  HTTP :80"]
            ALB[ALB]
            LST["Listener :80  →  Target Group :8501"]

            subgraph AZ_A["AZ: eu-west-1a"]
                subgraph PUB_A["Public subnet A  ·  10.0.1.0/24"]
                    FE["reflow-frontend<br/>Streamlit :8501"]
                    NAT["NAT Gateway"]
                end
                subgraph PRIV_A["Private subnet A  ·  10.0.10.0/24"]
                    subgraph ECSC["ECS Cluster"]
                        API["reflow-api<br/>FastAPI :8000"]
                        MCPS["mcp-supabase  :8001"]
                        MCPL["mcp-logistics  :8002"]
                    end
                end
            end

            subgraph AZ_B["AZ: eu-west-1b"]
                subgraph PUB_B["Public subnet B  ·  10.0.2.0/24"]
                    NB["2.ª AZ requerida por el ALB<br/>Sin tareas ECS"]
                end
            end
        end

        ECR["ECR  ·  3 repos"]
        SM["Secrets Manager  ·  8 secretos"]
        CW["CloudWatch Logs"]
    end

    SUP[(Supabase Cloud)]
    OAI[OpenAI API]
    LF[Langfuse Cloud]

    %% ── Flujo principal de tráfico ──────────────────────────────────
    USER        --> SGALB
    SGALB       --> ALB
    ALB         --> LST
    LST         -->|"Target Group :8501"| FE
    FE          -->|"Service Connect :8000"| API
    API         -->|":8001"| MCPS
    API         -->|":8002"| MCPL
    API         -->|":443 / :5432"| NAT
    MCPS        --> NAT
    MCPL        --> NAT
    FE          -->|":443  IP pública"| IGW
    NAT         --> IGW
    IGW         --> SUP
    IGW         --> OAI
    IGW         --> LF

    %% ── Configuración — líneas discontinuas ─────────────────────────
    ECR         -.->|"image pull"| FE
    ECR         -.->            API
    SM          -.->|"secretos"| API
    SM          -.->            MCPS
    API         -.->|"logs"|    CW
    FE          -.->            CW

    %% ══════════════════════════════════════════════════════════════
    %%  COLORES DE CONTENEDORES
    %%  Region   → gris claro
    %%  VPC      → morado claro
    %%  AZ       → azul claro, borde discontinuo
    %%  Public   → verde
    %%  Private  → azul
    %%  Cluster  → blanco, borde negro grueso
    %% ══════════════════════════════════════════════════════════════
    style REGION fill:#F5F5F5,stroke:#666666,stroke-width:2px,color:#333333
    style VPC    fill:#F9F0FF,stroke:#8C4FFF,stroke-width:2px,color:#6A0FBF
    style AZ_A   fill:#EBF5FB,stroke:#147EBA,stroke-width:2px,color:#0D6BA8
    style AZ_B   fill:#EBF5FB,stroke:#147EBA,stroke-width:2px,color:#0D6BA8
    style PUB_A  fill:#E8F5E9,stroke:#00A878,stroke-width:2px,color:#005C3E
    style PUB_B  fill:#E8F5E9,stroke:#00A878,stroke-width:2px,color:#005C3E
    style PRIV_A fill:#D6EAF8,stroke:#147EBA,stroke-width:2px,color:#0D6BA8
    style ECSC   fill:#FFFFFF,stroke:#232F3E,stroke-width:3px,color:#232F3E

    %% ── Clases de nodos ──────────────────────────────────────────
    classDef svc     fill:#F58534,stroke:#C05A00,color:#fff
    classDef sgbox   fill:#f8cecc,stroke:#b85450,color:#7B2D2D
    classDef gw      fill:#EDE0FF,stroke:#8C4FFF,color:#5A0FBF
    classDef support fill:#FFF3CD,stroke:#E6AC00,color:#5A4300
    classDef ext     fill:#DAE8FC,stroke:#6C8EBF,color:#1A3A5C
    classDef note    fill:#F0F0F0,stroke:#AAAAAA,color:#666666

    class FE,API,MCPS,MCPL svc
    class SGALB                sgbox
    class USER,IGW,NAT,ALB,LST gw
    class ECR,SM,CW            support
    class SUP,OAI,LF           ext
    class NB                   note
```

### Código de colores

| Color | Capa / elemento |
|-------|----------------|
| Fondo gris · borde gris | Region `eu-west-1` |
| Fondo **morado** claro · borde morado | VPC `10.0.0.0/16` |
| Fondo **azul** claro · borde azul | Availability Zone (AZ) |
| Fondo **verde** · borde verde | Public subnet |
| Fondo **azul** medio · borde azul sólido | Private subnet |
| Fondo blanco · borde **negro** grueso | ECS Cluster |
| **Naranja** | Servicio ECS Fargate |
| **Rojo** claro | Security group (`sg_alb`) |
| **Morado** claro (nodo) | Gateway / balanceador (ALB, NAT, IGW, Listener) |
| **Amarillo** claro | Soporte AWS (ECR, Secrets Manager, CloudWatch) |
| **Azul** claro (nodo) | Servicio externo (Supabase, OpenAI, Langfuse) |
| Flecha sólida `→` | Flujo de tráfico |
| Flecha discontinua `- ->` | Configuración (image pull / secretos / logs) |

---

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
