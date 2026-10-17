# ── Outputs ───────────────────────────────────────────────────────────────────
#
# Valores útiles tras `terraform apply`.
# Consultarlos con:  terraform output
#                    terraform output -raw alb_url
#                    terraform output -json ecr_urls

output "aws_region" {
  description = "Región AWS del despliegue"
  value       = var.aws_region
}

output "cluster_name" {
  description = "Nombre del cluster ECS"
  value       = aws_ecs_cluster.main.name
}

output "account_id" {
  description = "ID de la cuenta AWS (necesario para los comandos docker push)"
  value       = data.aws_caller_identity.current.account_id
}

# ── Comandos listos para copiar y pegar ───────────────────────────────────────

output "docker_login_cmd" {
  description = "Comando para autenticarse en ECR antes de hacer docker push"
  value       = "aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
}

output "docker_push_cmds" {
  description = "Comandos para construir y subir las tres imágenes a ECR"
  value = {
    api = join(" && ", [
      "docker build -f Dockerfile.api -t ${aws_ecr_repository.repos["reflow-api"].repository_url}:latest .",
      "docker push ${aws_ecr_repository.repos["reflow-api"].repository_url}:latest"
    ])
    mcp = join(" && ", [
      "docker build -f Dockerfile.mcp -t ${aws_ecr_repository.repos["reflow-mcp"].repository_url}:latest .",
      "docker push ${aws_ecr_repository.repos["reflow-mcp"].repository_url}:latest"
    ])
    frontend = join(" && ", [
      "docker build -f Dockerfile.frontend -t ${aws_ecr_repository.repos["reflow-frontend"].repository_url}:latest .",
      "docker push ${aws_ecr_repository.repos["reflow-frontend"].repository_url}:latest"
    ])
  }
}

output "update_secrets_cmds" {
  description = "Comandos para actualizar los secrets con valores reales antes del primer deploy"
  value = {
    jwt_secret      = "aws secretsmanager put-secret-value --secret-id reflow/jwt-secret --secret-string \"$(openssl rand -hex 32)\""
    admin_password  = "aws secretsmanager put-secret-value --secret-id reflow/admin-password --secret-string \"TU_CONTRASEÑA_ADMIN\""
    openai_api_key  = "aws secretsmanager put-secret-value --secret-id reflow/openai-api-key --secret-string \"sk-proj-...\""
    supabase_url    = "aws secretsmanager put-secret-value --secret-id reflow/supabase-url --secret-string \"https://xxx.supabase.co\""
    supabase_key    = "aws secretsmanager put-secret-value --secret-id reflow/supabase-service-key --secret-string \"eyJ...\""
    supabase_db_url = "aws secretsmanager put-secret-value --secret-id reflow/supabase-db-url --secret-string \"postgresql://postgres:pwd@host:6543/postgres\""
  }
}
