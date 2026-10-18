# ── Security Groups ───────────────────────────────────────────────────────────
#
# Traffic flow:
#   Browser → sg_alb → sg_frontend (Streamlit :8501)
#                       sg_frontend → sg_api (FastAPI :8000, via Service Connect)
#                                     sg_api → sg_mcp (MCP :8001/:8002)
#
# FastAPI is NOT behind the ALB. Streamlit calls it directly via Service Connect.

# ── Security group definitions (empty, rules added separately to avoid cycles) ─

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "ALB: accepts HTTP from internet, forwards to Streamlit"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name}-alb" }
}

resource "aws_security_group" "frontend" {
  name        = "${local.name}-frontend"
  description = "Streamlit :8501 - accessible from ALB, calls FastAPI directly"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name}-frontend" }
}

resource "aws_security_group" "api" {
  name        = "${local.name}-api"
  description = "FastAPI :8000 - accessible from Streamlit via Service Connect"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name}-api" }
}

resource "aws_security_group" "mcp" {
  name        = "${local.name}-mcp"
  description = "MCP servers :8001/:8002 - only accessible from FastAPI"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name}-mcp" }
}

# ── ALB rules ─────────────────────────────────────────────────────────────────

resource "aws_security_group_rule" "alb_ingress_http" {
  security_group_id = aws_security_group.alb.id
  type              = "ingress"
  description       = "HTTP from internet (restricted by IP)"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidr_blocks
}

resource "aws_security_group_rule" "alb_ingress_https" {
  security_group_id = aws_security_group.alb.id
  type              = "ingress"
  description       = "HTTPS from internet (restricted by IP)"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidr_blocks
}

resource "aws_security_group_rule" "alb_egress_frontend" {
  security_group_id        = aws_security_group.alb.id
  type                     = "egress"
  description              = "To Streamlit :8501"
  from_port                = 8501
  to_port                  = 8501
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.frontend.id
}

# ── Frontend rules ─────────────────────────────────────────────────────────────

resource "aws_security_group_rule" "frontend_ingress_alb" {
  security_group_id        = aws_security_group.frontend.id
  type                     = "ingress"
  description              = "From ALB"
  from_port                = 8501
  to_port                  = 8501
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.alb.id
}

# Streamlit calls FastAPI directly via Service Connect (port 8000)
resource "aws_security_group_rule" "frontend_egress_api" {
  security_group_id        = aws_security_group.frontend.id
  type                     = "egress"
  description              = "To FastAPI :8000 via Service Connect"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.api.id
}

resource "aws_security_group_rule" "frontend_egress_https" {
  security_group_id = aws_security_group.frontend.id
  type              = "egress"
  description       = "HTTPS outbound (ECR image pull)"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
}

# ── API rules ──────────────────────────────────────────────────────────────────

# FastAPI accepts traffic from Streamlit directly (Service Connect)
resource "aws_security_group_rule" "api_ingress_frontend" {
  security_group_id        = aws_security_group.api.id
  type                     = "ingress"
  description              = "From Streamlit via Service Connect"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.frontend.id
}

resource "aws_security_group_rule" "api_egress_mcp_supabase" {
  security_group_id        = aws_security_group.api.id
  type                     = "egress"
  description              = "To MCP Supabase :8001"
  from_port                = 8001
  to_port                  = 8001
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.mcp.id
}

resource "aws_security_group_rule" "api_egress_mcp_logistics" {
  security_group_id        = aws_security_group.api.id
  type                     = "egress"
  description              = "To MCP Logistics :8002"
  from_port                = 8002
  to_port                  = 8002
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.mcp.id
}

resource "aws_security_group_rule" "api_egress_https" {
  security_group_id = aws_security_group.api.id
  type              = "egress"
  description       = "HTTPS outbound (Supabase, OpenAI, Langfuse, ECR)"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
}

resource "aws_security_group_rule" "api_egress_postgres" {
  security_group_id = aws_security_group.api.id
  type              = "egress"
  description       = "PostgreSQL outbound - Supabase pooler :6543 and direct :5432"
  from_port         = 5432
  to_port           = 6543
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
}

# ── MCP rules ──────────────────────────────────────────────────────────────────

resource "aws_security_group_rule" "mcp_ingress_supabase" {
  security_group_id        = aws_security_group.mcp.id
  type                     = "ingress"
  description              = "MCP Supabase :8001 from FastAPI"
  from_port                = 8001
  to_port                  = 8001
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.api.id
}

resource "aws_security_group_rule" "mcp_ingress_logistics" {
  security_group_id        = aws_security_group.mcp.id
  type                     = "ingress"
  description              = "MCP Logistics :8002 from FastAPI"
  from_port                = 8002
  to_port                  = 8002
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.api.id
}

resource "aws_security_group_rule" "mcp_egress_https" {
  security_group_id = aws_security_group.mcp.id
  type              = "egress"
  description       = "HTTPS outbound (Supabase, OpenAI, ECR)"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
}
