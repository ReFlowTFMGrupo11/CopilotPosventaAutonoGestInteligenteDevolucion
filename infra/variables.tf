variable "aws_region" {
  description = "Región AWS donde se despliega la aplicación"
  type        = string
  default     = "eu-west-1"
}

variable "aws_profile" {
  description = "Perfil AWS (~/.aws/credentials) que usa Terraform. Sobreescribe con tu perfil en terraform.tfvars."
  type        = string
  default     = "default"
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

variable "allowed_cidr_blocks" {
  description = <<-EOT
    CIDRs con acceso al ALB (puertos 80 y 443).
    Por defecto abierto a internet. Para la cuenta de trabajo, restringe
    a tu IP: ["1.2.3.4/32"] o a la red de la empresa: ["10.0.0.0/8"].
    Obtén tu IP pública con: curl ifconfig.me
  EOT
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "ses_sender_email" {
  description = "Email verificado en SES usado como remitente. Vacío = envío simulado (solo log)."
  type        = string
  default     = ""
}

variable "ses_recipient_override" {
  description = "Si se define, todos los correos de la demo van a esta dirección. En sandbox debe estar verificada en SES."
  type        = string
  default     = ""
}
