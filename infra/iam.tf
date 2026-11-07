# ── IAM: roles para ECS y GitHub Actions ─────────────────────────────────────

# ── ECS Task Execution Role ───────────────────────────────────────────────────
#
# ECS/Fargate asume este rol para ARRANCAR cada tarea:
#   1. Descargar la imagen Docker desde ECR.
#   2. Leer los secrets de Secrets Manager e inyectarlos como variables
#      de entorno en el contenedor (JWT_SECRET, OPENAI_API_KEY, etc.).
#   3. Crear el log group y escribir los logs del contenedor en CloudWatch.
#
# Es distinto del Task Role (de abajo): este lo usa la infraestructura de ECS,
# no el código de la aplicación.

resource "aws_iam_role" "ecs_execution" {
  name = "${local.name}-ecs-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Política gestionada de AWS: cubre ECR pull + CloudWatch Logs.
resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Política inline: permite leer los secrets de reflow/* en Secrets Manager.
# Los secrets se crean en secrets.tf con el prefijo "reflow/".
resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "secrets-manager-read"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ]
      Resource = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:reflow/*"
    }]
  })
}

# ── ECS Task Role ─────────────────────────────────────────────────────────────
#
# La APLICACIÓN asume este rol mientras está corriendo. Nuestra app solo
# llama a servicios externos (Supabase, OpenAI, Langfuse) vía HTTP — no
# necesita ningún permiso AWS. Se define igualmente como buena práctica
# (separación execution role / task role) y para poder añadir permisos
# en el futuro sin tocar el execution role.

resource "aws_iam_role" "ecs_task" {
  name = "${local.name}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# ── GitHub Actions OIDC Role ──────────────────────────────────────────────────
# Pendiente — se añadirá en la fase de CI/CD una vez confirmado con la empresa
# que está permitido crear roles OIDC en la cuenta de trabajo.

# ── SES (envío de etiquetas por email) ────────────────────────────────────────
#
# Solo lo necesita el servicio mcp-logistics. Se limita a la identidad
# verificada del remitente; en sandbox, el destinatario también debe estar
# verificado en SES. No hay credenciales: boto3 usa las temporales del role.

resource "aws_iam_role_policy" "ecs_task_ses" {
  count = var.ses_sender_email == "" ? 0 : 1

  name = "ses-send-email"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ]
      Resource = "arn:aws:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:identity/${var.ses_sender_email}"
    }]
  })
}
