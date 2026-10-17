# ── Security Groups ───────────────────────────────────────────────────────────
#
# Los SGs se crean vacíos primero y las reglas se añaden después como
# recursos separados (aws_security_group_rule). Esto rompe la dependencia
# circular que ocurre cuando un SG referencia a otro en la misma definición.
#
# Arquitectura:
#   internet → sg_alb → sg_frontend (Streamlit :8501)
#                    → sg_api      (FastAPI :8000)
#                                 → sg_mcp (MCP :8001/:8002)

# ── Definiciones vacías ───────────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "ALB: acepta HTTP/HTTPS de internet, reenvía a frontend y api"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name}-alb" }
}

resource "aws_security_group" "frontend" {
  name        = "${local.name}-frontend"
  description = "Streamlit :8501 — solo accesible desde el ALB"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name}-frontend" }
}

resource "aws_security_group" "api" {
  name        = "${local.name}-api"
  description = "FastAPI :8000 — solo accesible desde el ALB"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name}-api" }
}

resource "aws_security_group" "mcp" {
  name        = "${local.name}-mcp"
  description = "MCP servers :8001/:8002 — solo accesibles desde FastAPI"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name}-mcp" }
}

# ── Reglas ALB ────────────────────────────────────────────────────────────────

resource "aws_security_group_rule" "alb_ingress_http" {
  security_group_id = aws_security_group.alb.id
  type              = "ingress"
  description       = "HTTP desde internet"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidr_blocks
}

resource "aws_security_group_rule" "alb_ingress_https" {
  security_group_id = aws_security_group.alb.id
  type              = "ingress"
  description       = "HTTPS desde internet"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidr_blocks
}

resource "aws_security_group_rule" "alb_egress_frontend" {
  security_group_id        = aws_security_group.alb.id
  type                     = "egress"
  description              = "Hacia Streamlit"
  from_port                = 8501
  to_port                  = 8501
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.frontend.id
}

resource "aws_security_group_rule" "alb_egress_api" {
  security_group_id        = aws_security_group.alb.id
  type                     = "egress"
  description              = "Hacia FastAPI"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.api.id
}

# ── Reglas Frontend ───────────────────────────────────────────────────────────

resource "aws_security_group_rule" "frontend_ingress_alb" {
  security_group_id        = aws_security_group.frontend.id
  type                     = "ingress"
  description              = "Desde el ALB"
  from_port                = 8501
  to_port                  = 8501
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.alb.id
}

resource "aws_security_group_rule" "frontend_egress_https" {
  security_group_id = aws_security_group.frontend.id
  type              = "egress"
  description       = "HTTPS saliente (ALB, internet)"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
}

# ── Reglas API ────────────────────────────────────────────────────────────────

resource "aws_security_group_rule" "api_ingress_alb" {
  security_group_id        = aws_security_group.api.id
  type                     = "ingress"
  description              = "Desde el ALB"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.alb.id
}

resource "aws_security_group_rule" "api_egress_mcp_supabase" {
  security_group_id        = aws_security_group.api.id
  type                     = "egress"
  description              = "Hacia MCP Supabase :8001"
  from_port                = 8001
  to_port                  = 8001
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.mcp.id
}

resource "aws_security_group_rule" "api_egress_mcp_logistics" {
  security_group_id        = aws_security_group.api.id
  type                     = "egress"
  description              = "Hacia MCP Logistics :8002"
  from_port                = 8002
  to_port                  = 8002
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.mcp.id
}

resource "aws_security_group_rule" "api_egress_https" {
  security_group_id = aws_security_group.api.id
  type              = "egress"
  description       = "HTTPS saliente (Supabase, OpenAI, Langfuse, ECR)"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
}

# ── Reglas MCP ────────────────────────────────────────────────────────────────

resource "aws_security_group_rule" "mcp_ingress_supabase" {
  security_group_id        = aws_security_group.mcp.id
  type                     = "ingress"
  description              = "MCP Supabase :8001 desde FastAPI"
  from_port                = 8001
  to_port                  = 8001
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.api.id
}

resource "aws_security_group_rule" "mcp_ingress_logistics" {
  security_group_id        = aws_security_group.mcp.id
  type                     = "ingress"
  description              = "MCP Logistics :8002 desde FastAPI"
  from_port                = 8002
  to_port                  = 8002
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.api.id
}

resource "aws_security_group_rule" "mcp_egress_https" {
  security_group_id = aws_security_group.mcp.id
  type              = "egress"
  description       = "HTTPS saliente (Supabase, OpenAI, ECR)"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
}
