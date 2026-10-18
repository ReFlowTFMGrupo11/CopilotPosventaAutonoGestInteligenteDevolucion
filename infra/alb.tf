# ── Application Load Balancer ─────────────────────────────────────────────────
#
# One ALB in two public subnets (AWS requires ≥2 AZs).
# Listens on HTTP :80 and forwards ALL traffic to Streamlit.
# FastAPI is not behind the ALB — Streamlit calls it directly via Service Connect.

resource "aws_lb" "main" {
  name               = local.name
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]

  tags = { Name = local.name }
}

# One target group: Streamlit frontend only.
# target_type = "ip": required for Fargate (awsvpc network mode).

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

# One listener: forward everything to Streamlit.

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}

output "alb_url" {
  description = "URL of the ALB (entry point for the browser)"
  value       = "http://${aws_lb.main.dns_name}"
}
