#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh — Arranca ReFlow en local o despliega en AWS ECS Fargate.
#
# Uso:
#   ./deploy.sh local                    Arranca los 4 servicios en local
#   ./deploy.sh local stop               Para los servicios locales
#   ./deploy.sh secrets                  Sincroniza .env → Secrets Manager (AWS)
#   ./deploy.sh aws                      Despliega en AWS (apply + secrets + push + wait)
#   ./deploy.sh aws destroy              Destruye toda la infraestructura AWS
#
# Prerequisitos AWS:
#   - stskeygen instalado y configurado
#   - terraform >= 1.6  (brew install terraform)
#   - docker corriendo
#   - aws cli instalado  (brew install awscli)
#   - .env con los valores reales
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$SCRIPT_DIR/infra"
ENV_FILE="$SCRIPT_DIR/.env"

MODE="${1:-}"

# ── Configuración AWS ─────────────────────────────────────────────────────────
# Perfil y región por defecto. Terraform los lee de terraform.tfvars;
# los comandos aws CLI los usan via AWS_PROFILE y AWS_DEFAULT_REGION.
AWS_CLI_PROFILE="${AWS_PROFILE:-admin@admin}"
AWS_CLI_REGION="${AWS_DEFAULT_REGION:-eu-west-1}"

# Shortcut: cualquier llamada a `aws` usará automáticamente perfil y región.
aws() { command aws --profile "$AWS_CLI_PROFILE" --region "$AWS_CLI_REGION" "$@"; }

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
  echo "  local              Arranca los 4 servicios en local (Mac/Linux)"
  echo "  local stop         Para los servicios locales"
  echo "  secrets            Sincroniza .env → AWS Secrets Manager"
  echo "  aws                Despliega en AWS (terraform + secrets + docker + ECS)"
  echo "  aws destroy        Destruye toda la infraestructura AWS"
  echo ""
  echo "Variables de entorno opcionales:"
  echo "  AWS_PROFILE        Perfil AWS a usar (default: admin@admin)"
  echo "  AWS_DEFAULT_REGION Region AWS (default: eu-west-1)"
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

# ── Verificar credenciales activas ────────────────────────────────────────────
check_aws_auth() {
  info "Verificando credenciales AWS (perfil: $AWS_CLI_PROFILE)..."
  local arn
  arn=$(aws sts get-caller-identity --query 'Arn' --output text 2>&1) || {
    error "Credenciales expiradas o invalidas para el perfil '$AWS_CLI_PROFILE'.\n\
Opciones:\n\
  - Cuenta personal:   aws configure  (introduce tu Access Key)\n\
  - Cuenta corporativa: genera credenciales con tu herramienta de SSO/roles\n\
  - Cambia el perfil:  edita aws_profile en infra/terraform.tfvars"
  }
  info "Cuenta activa: $arn"
}

# ── Terraform apply ────────────────────────────────────────────────────────────
terraform_apply() {
  info "Ejecutando terraform apply..."
  cd "$INFRA_DIR"
  terraform init -input=false -upgrade -no-color 2>&1 | tail -3
  terraform apply -auto-approve -no-color
  cd "$SCRIPT_DIR"
}

# ── Sincronizar secrets desde .env → Secrets Manager ─────────────────────────
sync_secrets() {
  info "Sincronizando secrets desde .env a Secrets Manager..."
  info "  Perfil: $AWS_CLI_PROFILE  |  Region: $AWS_CLI_REGION"

  [ -f "$ENV_FILE" ] || error "No se encontro .env en $ENV_FILE"

  # Lee el valor de una clave del .env sin ejecutar el fichero
  get_env_value() {
    local key="$1"
    local val
    # grep la línea key=valor, ignora comentarios, elimina comillas
    val=$(grep -E "^${key}=" "$ENV_FILE" | head -1 | cut -d'=' -f2- | sed "s/#.*$//" | xargs 2>/dev/null || true)
    echo "$val"
  }

  # Empuja un secret si tiene valor real (no vacío ni CHANGE_ME)
  push_secret() {
    local env_var="$1"
    local secret_id="$2"
    local value
    value=$(get_env_value "$env_var")
    if [ -n "$value" ] && [ "$value" != "CHANGE_ME" ]; then
      echo "  ✓  $env_var → $secret_id"
      aws secretsmanager put-secret-value \
        --secret-id "$secret_id" \
        --secret-string "$value" \
        --output text > /dev/null
      return 0
    else
      warning "  -  $env_var no encontrado en .env — $secret_id omitido"
      return 1
    fi
  }

  local updated=0 skipped=0
  _push() { push_secret "$1" "$2" && ((updated++)) || ((skipped++)) || true; }

  _push "OPENAI_API_KEY"     "reflow/openai-api-key"
  _push "SUPABASE_URL"       "reflow/supabase-url"
  _push "SUPABASE_SERVICE_KEY" "reflow/supabase-service-key"
  _push "SUPABASE_DB_URL"    "reflow/supabase-db-url"
  _push "JWT_SECRET"         "reflow/jwt-secret"
  _push "ADMIN_PASSWORD"     "reflow/admin-password"
  _push "LANGFUSE_SECRET_KEY" "reflow/langfuse-secret-key"
  _push "LANGFUSE_PUBLIC_KEY" "reflow/langfuse-public-key"

  info "$updated secrets actualizados, $skipped omitidos."
  [ "$skipped" -gt 0 ] && warning "Los servicios que usen esos secrets fallaran al arrancar."
}

# ── Build + push imágenes a ECR ───────────────────────────────────────────────
push_images() {
  info "Construyendo y subiendo imágenes a ECR..."
  cd "$INFRA_DIR"

  local account ecr_base api_url mcp_url fe_url
  account=$(aws sts get-caller-identity --query 'Account' --output text)
  ecr_base="$account.dkr.ecr.$AWS_CLI_REGION.amazonaws.com"

  info "  Docker login a ECR ($ecr_base)..."
  aws ecr get-login-password | \
    docker login --username AWS --password-stdin "$ecr_base"

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

# ── Esperar a que ECS esté estable ────────────────────────────────────────────
wait_ecs() {
  info "Esperando a que los servicios ECS esten estables (puede tardar ~3 min)..."
  local cluster
  cluster=$(cd "$INFRA_DIR" && terraform output -raw cluster_name)

  aws ecs wait services-stable \
    --cluster "$cluster" \
    --services fastapi mcp-supabase mcp-logistics frontend

  info "Todos los servicios estan activos."
}

# ── Mostrar URL ───────────────────────────────────────────────────────────────
show_url() {
  local app_url
  app_url=$(cd "$INFRA_DIR" && terraform output -raw alb_url)
  echo ""
  echo -e "${GREEN}================================================${NC}"
  echo -e "${GREEN}  ReFlow desplegado en AWS                      ${NC}"
  echo -e "${GREEN}  URL: $app_url  ${NC}"
  echo -e "${GREEN}================================================${NC}"
  echo ""
}

# ── Destroy ───────────────────────────────────────────────────────────────────
terraform_destroy() {
  warning "Esto destruira TODA la infraestructura en AWS."
  read -r -p "Escribe 'destruir' para confirmar: " confirm
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

  secrets)
    check_aws_auth
    sync_secrets
    ;;

  aws)
    SUBMODE="${2:-deploy}"
    check_aws_auth

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
