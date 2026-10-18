# ── Secrets Manager ───────────────────────────────────────────────────────────
#
# Todos los secrets siguen el prefijo "reflow/" — coincide con el ARN
# permitido en la política inline del execution role (iam.tf):
#   arn:aws:secretsmanager:REGION:ACCOUNT:secret:reflow/*
#
# recovery_window_in_days = 0: elimina el secret inmediatamente con
# `terraform destroy`, sin el periodo de retención de 30 días por defecto.
# Sin esto, un destroy + apply en el mismo día falla porque AWS considera
# que el nombre todavía existe (pendiente de expirar).
#
# Los secrets se crean con valor "CHANGE_ME". Después de `terraform apply`,
# actualiza cada uno con el valor real antes de arrancar los servicios ECS:
#
#   aws secretsmanager put-secret-value \
#     --secret-id reflow/openai-api-key \
#     --secret-string "sk-proj-..."
#
# O desde la consola AWS: Secrets Manager → selecciona el secret → "Retrieve
# secret value" → "Edit".

locals {
  # Secrets compartidos por FastAPI y los MCP servers
  secrets = {
    "reflow/openai-api-key"      = "CHANGE_ME"  # sk-proj-...
    "reflow/supabase-url"        = "CHANGE_ME"  # https://<project>.supabase.co
    "reflow/supabase-service-key" = "CHANGE_ME" # service_role key del proyecto
    "reflow/supabase-db-url"     = "CHANGE_ME"  # postgresql://postgres:[pwd]@[host]:6543/postgres

    # Solo FastAPI
    "reflow/jwt-secret"    = "CHANGE_ME"  # openssl rand -hex 32
    "reflow/admin-password" = "CHANGE_ME" # contraseña del panel de admin

    # Langfuse (opcional — si no se configura, el tracing se desactiva)
    "reflow/langfuse-secret-key" = "CHANGE_ME"  # sk-lf-...
    "reflow/langfuse-public-key" = "CHANGE_ME"  # pk-lf-...
  }
}

resource "aws_secretsmanager_secret" "secrets" {
  for_each = local.secrets

  name                    = each.key
  recovery_window_in_days = 0

  tags = { Name = each.key }
}

resource "aws_secretsmanager_secret_version" "secrets" {
  for_each = aws_secretsmanager_secret.secrets

  secret_id     = each.value.id
  secret_string = local.secrets[each.key]

  # Ignorar cambios en el valor: Terraform solo gestiona la creación inicial.
  # Los valores reales se actualizan fuera de Terraform (CLI o consola),
  # y no queremos que un `terraform apply` posterior los sobreescriba.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ── Outputs ───────────────────────────────────────────────────────────────────
#
# Los ARNs se usan en ecs.tf para referenciar los secrets en las
# task definitions (secrets = [{ name, valueFrom }]).

output "secret_arns" {
  description = "ARNs de los secrets (para referenciarlos en las task definitions de ECS)"
  value       = { for k, v in aws_secretsmanager_secret.secrets : k => v.arn }
}
