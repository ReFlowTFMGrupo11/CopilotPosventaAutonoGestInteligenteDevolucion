#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh — Arranca ReFlow en local o despliega en AWS ECS Fargate.
#
# Uso:
#   ./deploy.sh local                    Arranca los 4 servicios en local
#   ./deploy.sh local stop               Para los servicios locales
#   ./deploy.sh aws <cuenta>             Despliega en AWS (apply + push + wait)
#   ./deploy.sh aws <cuenta> destroy     Destruye toda la infraestructura AWS
#
# Prerequisitos AWS:
#   - stskeygen instalado y configurado
#   - terraform >= 1.6  (brew install terraform)
#   - docker corriendo
#   - aws cli instalado  (brew install awscli)
#   - .env con los valores reales (se sincronizan automáticamente a Secrets Manager)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$SCRIPT_DIR/infra"
ENV_FILE="$SCRIPT_DIR/.env"

MODE="${1:-}"

# ── Colores ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}==>${NC} $*"; }
warning() { echo -e "${YELLOW}AVISO:${NC} $*"; }
error()   { echo -e "${RED}ERROR:${NC} $*" >&2; exit 1; }

# ── Ayuda ─────────────────────────────────────────────────────────────────────
usage() {
  echo ""
  echo "Uso: $0 <modo> [opciones]"
  echo ""
  echo "  local                    Arranca los 4 servicios en local"
  echo "  local stop               Para los servicios locales"
  echo "  aws <cuenta>             Despliega en AWS ECS Fargate"
  echo "  aws <cuenta> destroy     Destruye toda la infraestructura AWS"
  echo ""
  exit 1
}

# ════════════════════════════════════════════════════════════════════════════ #
#  MODO LOCAL                                                                  #
# ════════════════════════════════════════════════════════════════════════════ #

start_local() {
  local subcmd="${1:-}"
  if [ "$subcmd" == "stop" ]; then
    exec "$SCRIPT_DIR/scripts/start_mac.sh" stop
  else
    exec "$SCRIPT_DIR/scripts/start_mac.sh"
  fi
}

# ════════════════════════════════════════════════════════════════════════════ #
#  MODO AWS                                                                    #
# ════════════════════════════════════════════════════════════════════════════ #

# ── 1. Autenticación AWS ──────────────────────────────────────────────────────
aws_auth() {
  local account="$1"
  info "Autenticando en AWS (cuenta: $account)..."
  stskeygen --account "$account"
  local current_account
  current_account=$(aws sts get-caller-identity --query 'Account' --output text)
  info "Cuenta activa: $current_account"
}

# ── 2. Terraform apply ────────────────────────────────────────────────────────
terraform_apply() {
  info "Ejecutando terraform apply..."
  cd "$INFRA_DIR"
  terraform init -input=false -upgrade -no-color 2>&1 | tail -3
  terraform apply -auto-approve -no-color
  cd "$SCRIPT_DIR"
}

# ── 3. Sincronizar secrets desde .env → Secrets Manager ──────────────────────
sync_secrets() {
  info "Sincronizando secrets desde .env a Secrets Manager..."

  [ -f "$ENV_FILE" ] || error "No se encontró .env en $ENV_FILE"

  # Mapeo env var → secret ID en Secrets Manager
  declare -A SECRET_MAP=(
    [OPENAI_API_KEY]="reflow/openai-api-key"
    [SUPABASE_URL]="reflow/supabase-url"
    [SUPABASE_SERVICE_KEY]="reflow/supabase-service-key"
    [SUPABASE_DB_URL]="reflow/supabase-db-url"
    [JWT_SECRET]="reflow/jwt-secret"
    [ADMIN_PASSWORD]="reflow/admin-password"
    [LANGFUSE_SECRET_KEY]="reflow/langfuse-secret-key"
    [LANGFUSE_PUBLIC_KEY]="reflow/langfuse-public-key"
  )

  # Leer .env sin ejecutarlo (evita efectos secundarios)
  declare -A ENV_VALUES
  while IFS='=' read -r key value; do
    # Saltar comentarios y líneas vacías
    [[ "$key" =~ ^[[:space:]]*# ]] && continue
    [[ -z "$key" ]] && continue
    # Eliminar comillas y espacios del valor
    value="${value%%#*}"         # eliminar comentarios inline
    value="${value%"${value##*[! ]}"}" # rtrim
    value="${value#\"}" ; value="${value%\"}"  # eliminar comillas dobles
    value="${value#\'}" ; value="${value%\'}"  # eliminar comillas simples
    ENV_VALUES["$key"]="$value"
  done < "$ENV_FILE"

  local updated=0
  local skipped=0
  for env_var in "${!SECRET_MAP[@]}"; do
    local secret_id="${SECRET_MAP[$env_var]}"
    local value="${ENV_VALUES[$env_var]:-}"

    if [ -n "$value" ] && [ "$value" != "CHANGE_ME" ]; then
      echo "  ✓ $secret_id"
      aws secretsmanager put-secret-value \
        --secret-id "$secret_id" \
        --secret-string "$value" \
        --output text > /dev/null
      ((updated++)) || true
    else
      warning "  $env_var no está en .env — $secret_id se queda sin actualizar"
      ((skipped++)) || true
    fi
  done

  info "$updated secrets actualizados, $skipped omitidos."
  [ "$skipped" -gt 0 ] && warning "Los servicios que usen secrets omitidos fallarán al arrancar."
}

# ── 4. Build + push imágenes a ECR ───────────────────────────────────────────
push_images() {
  info "Construyendo y subiendo imágenes a ECR..."
  cd "$INFRA_DIR"

  local region
  region=$(terraform output -raw aws_region)
  local account
  account=$(aws sts get-caller-identity --query 'Account' --output text)
  local ecr_base="$account.dkr.ecr.$region.amazonaws.com"

  # Docker login a ECR
  info "  Docker login a ECR ($ecr_base)..."
  aws ecr get-login-password --region "$region" | \
    docker login --username AWS --password-stdin "$ecr_base"

  local api_url mcp_url fe_url
  api_url=$(terraform output -json ecr_urls | python3 -c "import json,sys; print(json.load(sys.stdin)['reflow-api'])")
  mcp_url=$(terraform output -json ecr_urls | python3 -c "import json,sys; print(json.load(sys.stdin)['reflow-mcp'])")
  fe_url=$(terraform output -json ecr_urls  | python3 -c "import json,sys; print(json.load(sys.stdin)['reflow-frontend'])")

  cd "$SCRIPT_DIR"

  info "  Build + push reflow-api..."
  docker build -f Dockerfile.api      -t "$api_url:latest" . && docker push "$api_url:latest"

  info "  Build + push reflow-mcp..."
  docker build -f Dockerfile.mcp      -t "$mcp_url:latest" . && docker push "$mcp_url:latest"

  info "  Build + push reflow-frontend..."
  docker build -f Dockerfile.frontend -t "$fe_url:latest"  . && docker push "$fe_url:latest"
}

# ── 5. Esperar a que ECS esté estable ────────────────────────────────────────
wait_ecs() {
  info "Esperando a que los servicios ECS estén estables (puede tardar ~3 min)..."
  local cluster
  cluster=$(cd "$INFRA_DIR" && terraform output -raw cluster_name)

  aws ecs wait services-stable \
    --cluster "$cluster" \
    --services fastapi mcp-supabase mcp-logistics frontend \
    --region "$(cd "$INFRA_DIR" && terraform output -raw aws_region)"

  info "Todos los servicios están activos."
}

# ── 6. Mostrar URL ────────────────────────────────────────────────────────────
show_url() {
  local app_url
  app_url=$(cd "$INFRA_DIR" && terraform output -raw alb_url)
  echo ""
  echo -e "${GREEN}════════════════════════════════════════${NC}"
  echo -e "${GREEN}  ReFlow desplegado en AWS              ${NC}"
  echo -e "${GREEN}  URL: $app_url          ${NC}"
  echo -e "${GREEN}════════════════════════════════════════${NC}"
  echo ""
}

# ── Destroy ───────────────────────────────────────────────────────────────────
terraform_destroy() {
  warning "Esto destruirá TODA la infraestructura en AWS (VPC, ECS, ECR, secrets...)."
  read -r -p "¿Estás segura? Escribe 'destruir' para confirmar: " confirm
  [ "$confirm" == "destruir" ] || { echo "Cancelado."; exit 0; }

  info "Ejecutando terraform destroy..."
  cd "$INFRA_DIR"
  terraform destroy -auto-approve -no-color
  info "Todo destruido. No quedan recursos activos en AWS."
}

# ════════════════════════════════════════════════════════════════════════════ #
#  MAIN                                                                        #
# ════════════════════════════════════════════════════════════════════════════ #

case "$MODE" in
  local)
    start_local "${2:-}"
    ;;

  aws)
    ACCOUNT="${2:-}"
    SUBMODE="${3:-deploy}"

    [ -n "$ACCOUNT" ] || error "Especifica el nombre de la cuenta AWS.\n  Uso: $0 aws <cuenta>"

    aws_auth "$ACCOUNT"

    if [ "$SUBMODE" == "destroy" ]; then
      terraform_destroy
    else
      terraform_apply
      sync_secrets
      push_images
      wait_ecs
      show_url
    fi
    ;;

  *)
    usage
    ;;
esac
