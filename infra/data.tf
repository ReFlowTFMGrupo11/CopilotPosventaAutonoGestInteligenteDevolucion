data "aws_caller_identity" "current" {}

# OIDC provider de GitHub Actions — pendiente de fase CI/CD.
# Se recuperará cuando se añada el rol en iam.tf.
# data "aws_iam_openid_connect_provider" "github" {
#   url = "https://token.actions.githubusercontent.com"
# }
