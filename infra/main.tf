terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Estado local por defecto. Para equipos o despliegues multi-máquina,
  # migra a S3 añadiendo backend.hcl y ejecutando:
  #   terraform init -backend-config=backend.hcl -migrate-state
  #
  # Ejemplo de backend.hcl (no subir a git):
  #   bucket = "mi-bucket-de-terraform-state"
  #   key    = "reflow/production/terraform.tfstate"
  #   region = "eu-west-1"
  #
  # backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "reflow"
      Environment = "tfm"
      ManagedBy   = "terraform"
    }
  }
}

locals {
  app  = "reflow"
  env  = "tfm"
  name = "${local.app}-${local.env}"
}
