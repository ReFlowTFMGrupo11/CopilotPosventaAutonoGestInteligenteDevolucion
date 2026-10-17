# ── Application Load Balancer ─────────────────────────────────────────────────
#
# Un solo ALB público en las dos subnets públicas (AWS exige ≥2 AZs).
# Escucha en HTTP :80 — para el TFM es suficiente; en producción se añadiría
# un listener HTTPS :443 con certificado ACM y redirección 80→443.
#
# Routing:
#   /api/*  /health  /docs  /openapi.json  →  FastAPI :8000
#   /*  (todo lo demás)                    →  Streamlit :8501

resource "aws_lb" "main" {
  name               = local.name
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]

  tags = { Name = local.name }
}

# ── Target groups ─────────────────────────────────────────────────────────────
# target_type = "ip": obligatorio en Fargate (awsvpc network mode).
# El ALB registra directamente la IP privada de cada tarea.

resource "aws_lb_target_group" "api" {
  name        = "${local.name}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200"
  }

  tags = { Name = "${local.name}-api" }
}

resource "aws_lb_target_group" "frontend" {
  name        = "${local.name}-frontend"
  port        = 8501
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/_stcore/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200"
  }

  tags = { Name = "${local.name}-frontend" }
}

# ── Listener HTTP :80 ─────────────────────────────────────────────────────────

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  # Regla por defecto: todo va al frontend
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}

# Regla prioritaria: rutas del backend van a FastAPI
resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/health", "/docs", "/openapi.json"]
    }
  }
}

# ── Output ────────────────────────────────────────────────────────────────────

output "alb_url" {
  description = "URL del ALB (punto de entrada de la aplicación)"
  value       = "http://${aws_lb.main.dns_name}"
}
