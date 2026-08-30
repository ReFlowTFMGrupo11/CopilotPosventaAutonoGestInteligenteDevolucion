# Contenedores Docker de ReFlow

Esta carpeta agrupa el `Dockerfile` de cada uno de los 4 servicios de ReFlow
(uno por proceso de `start_all_mac.sh`), pensados para poder desplegarse
como tasks de **Amazon ECS Fargate**. El detalle completo del despliegue en
AWS (VPC, ALB, ECS, Secrets Manager, EFS...) vive en
[`docs/deployment_aws_ecs_fargate.md`](../docs/deployment_aws_ecs_fargate.md)
y en el diagrama [`docs/aws_architecture.drawio`](../docs/aws_architecture.drawio) — esta
carpeta es solo la parte de "construir la imagen", igual que `langfuse_infra/`
agrupa solo la infraestructura Docker de Langfuse (no el SDK Python).

## Qué hay en esta carpeta

| Archivo | Para qué |
|---|---|
| `api.Dockerfile` | Backend FastAPI (`backend/api/main.py`), puerto 8000. |
| `frontend.Dockerfile` | Frontend Streamlit (`frontend/Chat.py`), puerto 8501. |
| `mcp_supabase.Dockerfile` | MCP server de datos/políticas (`backend/mcp/mcp_supabase.py`), puerto 8001. |
| `mcp_logistics.Dockerfile` | MCP server de logística (`backend/mcp/mcp_logistics.py`), puerto 8002. |
| `docker-compose.yml` | Banco de pruebas local: levanta las 4 imágenes ya containerizadas juntas, antes de subirlas a ECR. |

No hay un único `Dockerfile` para los 4 servicios a propósito: cada proceso
tiene su propio ciclo de vida, sus propios recursos (CPU/memoria) y su
propio ritmo de despliegue en ECS — una task definition por servicio, no un
contenedor "monolito" que arranque los 4 procesos con supervisord.

## Por qué el contexto de build es la raíz del repo, no `docker/`

Cada `Dockerfile` copia `requirements.txt` y `backend/` (o `frontend/`)
desde la raíz del proyecto, así que el contexto de build tiene que ser la
raíz, no esta carpeta:

```bash
# Desde la raíz del repo, NO desde docker/:
docker build -f docker/api.Dockerfile -t reflow-api:latest .
docker build -f docker/frontend.Dockerfile -t reflow-frontend:latest .
docker build -f docker/mcp_supabase.Dockerfile -t reflow-mcp-supabase:latest .
docker build -f docker/mcp_logistics.Dockerfile -t reflow-mcp-logistics:latest .
```

## Probar las imágenes en local antes de subirlas a ECR

```bash
cp .env.example .env   # si no lo tienes ya, y rellena credenciales reales
docker compose -f docker/docker-compose.yml up --build
```

Esto levanta los mismos 4 servicios que `start_all_mac.sh`, pero cada uno
en su propio contenedor, conectados entre sí por el DNS interno de Docker
Compose (`http://mcp-supabase:8001/mcp`, no `localhost`) — la misma lógica
de red que usarán luego en ECS (Service Connect en vez de DNS de Compose).

Parar y limpiar:

```bash
docker compose -f docker/docker-compose.yml down
```

## Diferencias importantes frente a correr `start_all_mac.sh` sin Docker

- **`API_BASE_URL`**: el frontend ya no asume `http://localhost:8000` a
  secas — dentro de un contenedor, `localhost` es el propio contenedor del
  frontend, no el del backend (ver `frontend/lib/api.py`). El
  `docker-compose.yml` de aquí ya la fija a `http://api:8000`; en ECS se
  fija en la task definition a la URL de Service Connect del backend.
- **`generated_labels/` es efímero**: los PDFs de etiquetas y el log de
  notificaciones (`backend/services/logistics_service.py`) se escriben en
  el filesystem del propio contenedor. En local con Compose se resuelve
  montando un volumen (ya configurado en `docker-compose.yml`); en Fargate
  no hay filesystem persistente entre despliegues salvo que se monte un
  volumen EFS — ver la sección correspondiente en
  `docs/deployment_aws_ecs_fargate.md`.
- **Sin recarga en caliente**: las imágenes no usan `--reload` (uvicorn) ni
  el watcher de archivos — para desarrollo del día a día sigue siendo más
  rápido `start_all_mac.sh` sin Docker; estas imágenes son para probar el
  artefacto que de verdad se despliega, no para iterar código.

## Tamaño de imagen: `requirements.txt` incluye dependencias de test/lint

`requirements.txt` no distingue dependencias de producción de las de
desarrollo (`pytest`, `black`, `flake8`, `mypy`, `pip-audit` viven en el
mismo archivo — ver el comentario al final de `requirements.txt`). Estos
`Dockerfile` instalan el archivo completo tal cual, así que las imágenes
son más pesadas de lo estrictamente necesario para producción. Separar
`requirements.txt` en base/dev sería una mejora futura razonable, pero no
se ha hecho aquí para no tocar un archivo que usan tests/CI/instrucciones
de instalación existentes sin que se haya pedido explícitamente.
