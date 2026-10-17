data "aws_caller_identity" "current" {}

# VPC por defecto de la cuenta (existe en todas las cuentas AWS nuevas)
data "aws_vpc" "default" {
  default = true
}

# Subnets de la VPC por defecto (una por zona de disponibilidad)
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# OIDC provider de GitHub Actions (prerequisito manual, ver README)
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}
