variable "aws_region" {
  description = "Región AWS donde se despliega la aplicación"
  type        = string
  default     = "eu-west-1"
}

variable "github_repo" {
  description = "Repositorio GitHub en formato 'org/repo' (para el rol OIDC de GitHub Actions)"
  type        = string
  default     = "ReFlowTFMGrupo11/CopilotPosventaAutonoGestInteligenteDevolucion"
}

variable "desired_count" {
  description = "Número de réplicas de cada servicio ECS (1 para TFM/demo, >=2 para HA)"
  type        = number
  default     = 1
}
