# Despliegue en AWS con ECS Fargate

Esta guía explica cómo llevar los 4 servicios de ReFlow (frontend Streamlit,
API FastAPI, MCP Supabase, MCP Logistics — los mismos que arranca
`start_all_mac.sh` en local) a producción en AWS usando contenedores Docker
sobre **Amazon ECS con el modo de ejecución Fargate** (sin gestionar
instancias EC2).

Diagrama de referencia: [`docs/aws_architecture.drawio`](aws_architecture.drawio)
(ábrelo en [draw.io](https://app.diagrams.net/) o en la extensión de VS
Code). Dockerfiles de referencia: [`docker/`](../docker/).

## Por qué Supabase y Langfuse quedan fuera de AWS

Este proyecto ya usa **Supabase Cloud** (Postgres + pgvector + Storage) y,
por defecto, **Langfuse Cloud** (ver `backend/services/observability.py` y
`.env.example`: "Por defecto usa LangFuse Cloud") — ambos son servicios
SaaS con su propia infraestructura gestionada, fuera de cualquier cuenta de
AWS del proyecto. Por eso el diagrama los dibuja como una caja aparte,
"servicios cloud externos", conectada a la VPC solo por HTTPS/Postgres a
través de internet (vía NAT Gateway), **no** como recursos AWS (no hay RDS,
no hay OpenSearch, no hay un ECS Service para el stack de Langfuse
self-hosted de `langfuse_infra/`).

Esto simplifica mucho el diseño: no hay que gestionar backups de base de
datos, alta disponibilidad de Postgres ni el stack de 6 contenedores de
Langfuse (Postgres+ClickHouse+Redis+MinIO+web+worker, ver
`langfuse_infra/README.md`) dentro de AWS. Lo único que hay que desplegar en
AWS son los 4 servicios de la aplicación en sí.

Si en el futuro se decide self-hostear Langfuse en AWS en vez de usar
Langfuse Cloud, ese stack se añadiría como sus propios ECS Services (o,
más realista dado que necesita ClickHouse, en instancias EC2/EKS) — está
fuera del alcance de esta guía porque el proyecto usa Langfuse Cloud por
defecto.

## 1. Construir las imágenes Docker

Cada servicio tiene su propio `Dockerfile` en [`docker/`](../docker/):

| Servicio | Dockerfile | Puerto |
|---|---|---|
| Frontend (Streamlit) | `docker/frontend.Dockerfile` | 8501 |
| Backend API (FastAPI) | `docker/api.Dockerfile` | 8000 |
| MCP Supabase | `docker/mcp_supabase.Dockerfile` | 8001 |
| MCP Logistics | `docker/mcp_logistics.Dockerfile` | 8002 |

El contexto de build es la **raíz del repo** (necesitan `requirements.txt` y
`backend/`/`frontend/`):

```bash
docker build -f docker/api.Dockerfile            -t reflow-api:latest            .
docker build -f docker/frontend.Dockerfile       -t reflow-frontend:latest       .
docker build -f docker/mcp_supabase.Dockerfile   -t reflow-mcp-supabase:latest   .
docker build -f docker/mcp_logistics.Dockerfile  -t reflow-mcp-logistics:latest  .
```

Antes de subir nada a AWS, pruébalas juntas en local con Docker Compose
(ver [`docker/README.md`](../docker/README.md) para el detalle):

```bash
docker compose -f docker/docker-compose.yml up --build
```

Si todo va bien deberías poder abrir `http://localhost:8501` igual que con
`start_all_mac.sh`, pero esta vez cada proceso corriendo en su propio
contenedor.

## 2. Subir las imágenes a Amazon ECR

Un repositorio ECR por servicio (coincide 1:1 con las 4 cajas de
"Amazon ECR" del diagrama):

```bash
export AWS_REGION=eu-west-1          # o la región que uses
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

for repo in reflow-api reflow-frontend reflow-mcp-supabase reflow-mcp-logistics; do
  aws ecr create-repository --repository-name "$repo" --region "$AWS_REGION" || true
done

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
```

Etiquetar y subir cada imagen (repite para los 4 servicios, cambiando
`reflow-api` por el repo correspondiente):

```bash
docker tag reflow-api:latest "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/reflow-api:latest"
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/reflow-api:latest"
```

En CI/CD (sección 9) este paso se automatiza — aquí se documenta el comando
manual para poder desplegar sin depender de GitHub Actions la primera vez.

## 3. Red: VPC, subredes y salida a internet

Recomendado (ver caja "VPC 10.0.0.0/16" del diagrama), 2 zonas de
disponibilidad para tolerancia a fallos:

- 1 VPC, con **2 subredes públicas** (una por AZ) y **2 subredes privadas**
  (una por AZ).
- 1 **Internet Gateway**, asociado a las subredes públicas.
- 1 **NAT Gateway por AZ** (en la subred pública de esa AZ), para que las
  tasks de Fargate en subred privada puedan salir a internet (llamar a
  OpenAI, Supabase Cloud, Langfuse Cloud) sin tener IP pública propia.
- **Security Groups**:
  - `sg-alb`: entrada 443 desde `0.0.0.0/0`, salida libre.
  - `sg-frontend`: entrada 8501 solo desde `sg-alb`, salida libre (llama al
    backend).
  - `sg-backend`: entrada 8000 solo desde `sg-frontend`, salida libre
    (llama a los MCP servers y a los servicios cloud externos).
  - `sg-mcp`: entrada 8001/8002 solo desde `sg-backend`. Nada más puede
    llamar directamente a los MCP servers — ni siquiera el frontend.

La forma más rápida de crear todo esto es con el asistente de VPC de la
consola de AWS ("VPC and more"), eligiendo 2 AZs, NAT Gateway "1 per AZ" y
dejando que genere las tablas de rutas — replicar esto a mano con la CLI es
mucho más largo y no aporta nada distinto para este proyecto.

## 4. ECS Cluster (Fargate): task definitions y services

Un **cluster** (`reflow-cluster`) con **4 servicios**, uno por
contenedor — no un único servicio con los 4 procesos (misma filosofía que
`start_all_mac.sh`: 4 procesos independientes, cada uno con su ciclo de
vida). Cada servicio necesita su propia **task definition**.

Ejemplo de task definition para el backend API (JSON abreviado; sustituye
`<ACCOUNT_ID>`/`<REGION>`):

```json
{
  "family": "reflow-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::<ACCOUNT_ID>:role/reflow-ecs-execution-role",
  "taskRoleArn": "arn:aws:iam::<ACCOUNT_ID>:role/reflow-ecs-task-role",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/reflow-api:latest",
      "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
      "environment": [
        {"name": "MCP_SUPABASE_URL", "value": "http://mcp-supabase.reflow.internal:8001/mcp"},
        {"name": "MCP_LOGISTICS_URL", "value": "http://mcp-logistics.reflow.internal:8002/mcp"},
        {"name": "TRIAGE_MODEL", "value": "gpt-5-mini"},
        {"name": "EVALUATOR_MODEL", "value": "gpt-5-mini"},
        {"name": "RESOLVER_MODEL", "value": "gpt-5-mini"},
        {"name": "HITL_THRESHOLD_EUR", "value": "100"}
      ],
      "secrets": [
        {"name": "OPENAI_API_KEY", "valueFrom": "arn:aws:secretsmanager:<REGION>:<ACCOUNT_ID>:secret:reflow/openai-api-key"},
        {"name": "SUPABASE_URL", "valueFrom": "arn:aws:secretsmanager:<REGION>:<ACCOUNT_ID>:secret:reflow/supabase-url"},
        {"name": "SUPABASE_SERVICE_KEY", "valueFrom": "arn:aws:secretsmanager:<REGION>:<ACCOUNT_ID>:secret:reflow/supabase-service-key"},
        {"name": "SUPABASE_DB_URL", "valueFrom": "arn:aws:secretsmanager:<REGION>:<ACCOUNT_ID>:secret:reflow/supabase-db-url"},
        {"name": "LANGFUSE_PUBLIC_KEY", "valueFrom": "arn:aws:secretsmanager:<REGION>:<ACCOUNT_ID>:secret:reflow/langfuse-public-key"},
        {"name": "LANGFUSE_SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:<REGION>:<ACCOUNT_ID>:secret:reflow/langfuse-secret-key"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/reflow-api",
          "awslogs-region": "<REGION>",
          "awslogs-stream-prefix": "api"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)\" || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 15
      }
    }
  ]
}
```

Notas importantes al adaptar esto a los otros 3 servicios:

- **`mcp-supabase`/`mcp-logistics`**: mismo patrón, pero el `healthCheck`
  usa el chequeo TCP (ver el `HEALTHCHECK` de sus `Dockerfile` en
  `docker/`) en vez de una URL HTTP — el protocolo MCP no tiene un `/health`
  simple. Solo necesitan `OPENAI_API_KEY`/`SUPABASE_*` como secreto
  (`mcp_supabase`) — `mcp_logistics` no necesita ningún secreto, no toca
  Supabase ni OpenAI.
- **`frontend`**: variable `API_BASE_URL=http://backend-api.reflow.internal:8000`
  en vez del `secrets` de arriba (el frontend no llama directamente a
  OpenAI/Supabase, solo a la API). Puerto 8501 en `portMappings`.
- **`networkMode: awsvpc`** es obligatorio en Fargate (asigna una ENI por
  task, con IP propia dentro de la subred) — no hay "modo bridge" como en
  ECS sobre EC2.
- **CPU/memoria**: los valores de arriba (0.5 vCPU / 1 GB) son un punto de
  partida razonable para `api`/`frontend`; los MCP servers son más
  ligeros (0.25 vCPU / 512 MB suele bastar) — ajusta según lo que veas en
  CloudWatch Container Insights (sección 8) tras las primeras cargas
  reales.

### Service Connect (DNS interno entre servicios)

En vez de IPs fijas o Elastic IPs por task (que cambian en cada
despliegue), usa **ECS Service Connect** (basado en AWS Cloud Map) al crear
cada servicio:

```bash
aws ecs create-service \
  --cluster reflow-cluster \
  --service-name backend-api \
  --task-definition reflow-api \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-priv-a>,<subnet-priv-b>],securityGroups=[<sg-backend>],assignPublicIp=DISABLED}" \
  --service-connect-configuration "enabled=true,namespace=reflow.internal,services=[{portName=api,discoveryName=backend-api,clientAliases=[{port=8000}]}]"
```

Con esto, cualquier otro servicio de la misma Service Connect namespace
puede llamar a `http://backend-api.reflow.internal:8000` sin conocer IPs.
Repite el patrón para `mcp-supabase`, `mcp-logistics` (ambos con
`assignPublicIp=DISABLED`, subredes privadas, sin necesidad de estar detrás
del ALB) y para `frontend` (que sí necesita estar en el target group del
ALB, ver sección 5).

## 5. Exposición pública: ALB + ACM + Route 53

Solo el **frontend** recibe tráfico de internet (ver la nota del diagrama:
"Solo el frontend recibe tráfico público"). Ni la API ni los MCP servers
necesitan estar detrás del ALB — se llaman entre sí por Service Connect,
dentro de la VPC.

1. **Certificado TLS**: pide uno en **AWS Certificate Manager** (ACM) para
   tu dominio (validación DNS, automática si el dominio ya está en Route
   53).
2. **Application Load Balancer**: en las 2 subredes públicas, con un
   listener HTTPS:443 usando ese certificado, y un **target group** de
   tipo `ip` (obligatorio en Fargate, no `instance`) apuntando al puerto
   8501.
3. **Service de ECS del frontend**: al crearlo, añade
   `--load-balancers targetGroupArn=<arn-target-group>,containerName=frontend,containerPort=8501`
   — ECS registra/desregistra automáticamente cada task en el target group
   conforme escala.
4. **Route 53**: un registro `A`/`ALIAS` del dominio (p. ej.
   `reflow.tudominio.com`) apuntando al DNS del ALB.

Opcional pero recomendado antes de exponerlo a usuarios reales: **AWS WAF**
delante del ALB (reglas gestionadas básicas: rate limiting, SQL
injection/XSS genérico) — no imprescindible para un TFM, pero es la
diferencia entre "funciona en la demo" y "aguanta tráfico de internet real"
sin esfuerzo adicional de desarrollo.

## 6. Secretos: AWS Secrets Manager

Todo lo que hoy vive en el `.env` de la raíz del proyecto (ver
`.env.example`) y es sensible (`OPENAI_API_KEY`, `SUPABASE_SERVICE_KEY`,
`SUPABASE_DB_URL`, `LANGFUSE_SECRET_KEY`...) se sube como un secreto por
variable:

```bash
aws secretsmanager create-secret --name reflow/openai-api-key --secret-string "sk-..."
aws secretsmanager create-secret --name reflow/supabase-service-key --secret-string "eyJ..."
aws secretsmanager create-secret --name reflow/supabase-db-url --secret-string "postgresql://..."
# ...una por cada secreto de la tabla de la task definition (sección 4)
```

La task definition referencia el ARN de cada secreto en el bloque
`secrets` (no `environment` — `environment` es para valores no sensibles
tipo `TRIAGE_MODEL`). ECS los inyecta como variables de entorno del
contenedor en el arranque de la task; el código no cambia nada
(`backend/config.py` sigue leyendo `os.environ`/`.env` exactamente igual,
container o no).

El **Task Execution Role** (no el Task Role) necesita permiso
`secretsmanager:GetSecretValue` sobre esos ARNs — es el rol que usa el
agente de ECS para arrancar el contenedor, no el que usa tu código en
runtime.

## 7. Almacenamiento persistente: EFS para `generated_labels/`

`backend/services/logistics_service.py` escribe PDFs de etiquetas y
`notifications_log.jsonl` en `generated_labels/`, en el filesystem local del
proceso (`LABELS_DIR = Path(__file__).parent.parent.parent / "generated_labels"`).
En Fargate, el filesystem de cada task es efímero y no se comparte entre
tasks — sin storage externo, cada etiqeta generada desaparece en el primer
redeploy/reinicio/escalado del servicio `mcp-logistics`, y con `desired-count > 1`
ni siquiera se compartiría entre tasks concurrentes.

La solución que **no requiere ningún cambio de código** es montar un
volumen **Amazon EFS** en la ruta `/app/generated_labels` dentro del
contenedor:

1. Crea un file system EFS en la misma VPC, con un mount target por AZ
   (subred privada).
2. En la task definition de `mcp-logistics`, añade:

```json
"volumes": [
  {
    "name": "generated-labels",
    "efsVolumeConfiguration": {
      "fileSystemId": "fs-xxxxxxxx",
      "transitEncryption": "ENABLED"
    }
  }
],
"containerDefinitions": [
  {
    "name": "mcp-logistics",
    "mountPoints": [
      {"sourceVolume": "generated-labels", "containerPath": "/app/generated_labels"}
    ]
  }
]
```

Como el `Dockerfile` ya define `WORKDIR /app` y el código crea
`generated_labels/` con `mkdir(exist_ok=True)` si no existe, montar EFS ahí
es transparente para la aplicación — el código sigue escribiendo con
`open()`/`Path` normales, solo que ahora esos archivos persisten fuera del
ciclo de vida de la task.

## 8. Observabilidad: CloudWatch Logs + Container Insights

Cada `containerDefinitions[].logConfiguration` con `logDriver: awslogs`
(ver el ejemplo de la sección 4) manda stdout/stderr del contenedor a un
log group de CloudWatch — por eso todos los `Dockerfile` fijan
`PYTHONUNBUFFERED=1`, si no los logs solo aparecerían al llenarse el buffer
o morir el proceso, con retraso y de forma poco predecible.

Activa **Container Insights** en el cluster (`aws ecs update-cluster-settings
--cluster reflow-cluster --settings name=containerInsights,value=enabled`)
para métricas de CPU/memoria/red por servicio y por task sin instrumentar
nada — es la referencia para ajustar los valores de CPU/memoria de la
sección 4 con datos reales en vez de a ojo.

Esto es observabilidad de **infraestructura** (¿está viva la task, cuánta
CPU usa?), complementaria a Langfuse Cloud (observabilidad de **LLM**:
prompts, tokens, coste, latencia por llamada) — no se solapan, cada una
responde una pregunta distinta.

## 9. CI/CD: GitHub Actions → ECR → ECS

El repo ya tiene un pipeline de CI en `.github/workflows/ci.yml` (lint,
tests, secret scanning, validación de `.drawio`). Añadir el despliegue
automático es un job adicional que se dispara solo en `push` a `main` (no
en cada PR, para no desplegar código sin revisar):

```yaml
  deploy:
    name: Build, push y deploy a ECS
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    needs: [lint, test]
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<ACCOUNT_ID>:role/github-actions-reflow-deploy
          aws-region: <REGION>
      - uses: aws-actions/amazon-ecr-login@v2
        id: ecr
      - name: Build y push de las 4 imágenes
        run: |
          for svc in api frontend mcp_supabase mcp_logistics; do
            repo="reflow-${svc//_/-}"
            docker build -f docker/$svc.Dockerfile -t "${{ steps.ecr.outputs.registry }}/$repo:${{ github.sha }}" .
            docker push "${{ steps.ecr.outputs.registry }}/$repo:${{ github.sha }}"
          done
      - name: Forzar nuevo despliegue en cada servicio ECS
        run: |
          for svc in backend-api frontend mcp-supabase mcp-logistics; do
            aws ecs update-service --cluster reflow-cluster --service "$svc" --force-new-deployment
          done
```

`role-to-assume` usa **OIDC** (GitHub Actions ↔ IAM, sin credenciales de
AWS de larga duración guardadas como secreto del repo) — configurar el
proveedor OIDC de IAM es un paso de una sola vez, fuera del alcance de este
documento (ver la [guía oficial de `aws-actions/configure-aws-credentials`](https://github.com/aws-actions/configure-aws-credentials)).
Este job no se ha añadido todavía a `ci.yml` en esta PR (necesita que exista
ya la infraestructura de las secciones 2-4 y los ARNs reales) — se deja
documentado aquí para cuando se decida activarlo.

## 10. Checklist de despliegue (primera vez)

1. [ ] VPC con 2 AZs, subredes públicas/privadas, NAT Gateway, Internet
   Gateway (sección 3).
2. [ ] 4 repositorios ECR creados, imágenes construidas y subidas
   (secciones 1-2).
3. [ ] Secretos en Secrets Manager (sección 6).
4. [ ] Cluster ECS Fargate + 4 task definitions + 4 services con Service
   Connect (sección 4).
5. [ ] Amazon EFS montado en `mcp-logistics` (sección 7) — sin esto, las
   etiquetas generadas se pierden en el primer redeploy.
6. [ ] ALB + target group `:8501` + certificado ACM + registro Route 53
   (sección 5) — solo para el servicio `frontend`.
7. [ ] Container Insights activado (sección 8).
8. [ ] Probar el flujo completo end-to-end contra la URL pública antes de
   anunciar el despliegue: abrir el chat, generar una devolución, y
   comprobar en Langfuse Cloud que llegan trazas y en CloudWatch que
   llegan logs.
9. [ ] (Opcional) Job de CI/CD de la sección 9, una vez validado el
   despliegue manual.

### Coste aproximado

Con los tamaños de CPU/memoria de la sección 4 (0.5 vCPU/1GB para
`api`/`frontend`, 0.25 vCPU/512MB para los MCP servers) y 1 task por
servicio corriendo 24/7, el coste de Fargate en `eu-west-1` es del orden de
**30-40 USD/mes** solo de cómputo — a eso hay que sumarle el ALB (~16
USD/mes fijos + tráfico), 2 NAT Gateways (~65 USD/mes fijos + tráfico
procesado — es habitualmente la partida más cara de esta arquitectura) y
EFS (por GB almacenado, marginal para PDFs de etiquetas). Para un entorno
de demo/TFM que no necesita estar disponible 24/7, reducir a **1 sola AZ /
1 solo NAT Gateway** (en vez de 2) recorta esa partida a la mitad, a costa
de perder tolerancia a fallos de zona — una decisión razonable dado el
contexto del proyecto.
