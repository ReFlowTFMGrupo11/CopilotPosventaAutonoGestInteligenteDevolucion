# ── ECR: repositorios de imágenes Docker ─────────────────────────────────────
#
# Tres repositorios, uno por imagen:
#   reflow-api      ← Dockerfile.api      (FastAPI + LangGraph)
#   reflow-mcp      ← Dockerfile.mcp      (MCP Supabase + MCP Logistics)
#   reflow-frontend ← Dockerfile.frontend (Streamlit)
#
# force_delete = true: permite `terraform destroy` aunque los repos
# contengan imágenes. Sin esto, destroy falla con "repository not empty".
# Imprescindible para poder destruir todo limpiamente al acabar las pruebas.

locals {
  ecr_repos = ["reflow-api", "reflow-mcp", "reflow-frontend"]
}

resource "aws_ecr_repository" "repos" {
  for_each = toset(local.ecr_repos)

  name                 = each.key
  image_tag_mutability = "MUTABLE" # permite sobreescribir :latest en cada push
  force_delete         = true      # destruye el repo aunque tenga imágenes

  image_scanning_configuration {
    scan_on_push = true # escaneo de vulnerabilidades gratuito en cada push
  }

  tags = { Name = each.key }
}

# ── Lifecycle policy ──────────────────────────────────────────────────────────
#
# Limita el almacenamiento (y su coste) en ECR:
#   - Imágenes sin tag (capas intermedias de builds): borrar tras 1 día.
#   - Imágenes con tag: conservar solo las últimas 5 por repo.
# Para el TFM con pocos deploys es más que suficiente.

resource "aws_ecr_lifecycle_policy" "repos" {
  for_each   = aws_ecr_repository.repos
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Borrar imágenes sin tag tras 1 día"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Conservar solo las últimas 5 imágenes con tag"
        selection = {
          tagStatus   = "tagged"
          tagPrefixList = ["latest", "v"]
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = { type = "expire" }
      }
    ]
  })
}

# ── Outputs útiles ────────────────────────────────────────────────────────────
#
# Las URLs de los repos se usan en los comandos docker push y en las
# task definitions de ECS (ecs.tf). Se exponen también en outputs.tf.

output "ecr_urls" {
  description = "URLs de los repositorios ECR (para docker push y task definitions)"
  value       = { for k, v in aws_ecr_repository.repos : k => v.repository_url }
}
