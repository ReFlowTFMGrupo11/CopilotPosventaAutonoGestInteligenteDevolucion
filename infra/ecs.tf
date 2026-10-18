# ── ECS Fargate ───────────────────────────────────────────────────────────────
#
# Cuatro servicios sobre un único cluster Fargate:
#   fastapi        → reflow-api:latest      subnet privada  :8000
#   mcp-supabase   → reflow-mcp:latest      subnet privada  :8001
#   mcp-logistics  → reflow-mcp:latest      subnet privada  :8002
#   frontend       → reflow-frontend:latest subnet pública  :8501
#
# Comunicación interna (fastapi ↔ mcp servers) via ECS Service Connect:
#   http://mcp-supabase:8001/mcp
#   http://mcp-logistics:8002/mcp
# No requiere Route53 ni DNS externo — AWS gestiona el namespace internamente.

# ── CloudWatch Log Groups ─────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "services" {
  for_each = toset(["fastapi", "mcp-supabase", "mcp-logistics", "frontend"])

  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = 7 # mínimo para el TFM; reducir costes de almacenamiento

  tags = { Name = "/ecs/${local.name}/${each.key}" }
}

# ── Service Connect namespace ─────────────────────────────────────────────────
# Namespace HTTP de Cloud Map: solo para ECS Service Connect, no crea
# registros DNS en Route53 ni en ningún servicio DNS externo.

resource "aws_service_discovery_http_namespace" "main" {
  name = local.name
  tags = { Name = local.name }
}

# ── ECS Cluster ───────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = local.name

  service_connect_defaults {
    namespace = aws_service_discovery_http_namespace.main.arn
  }

  tags = { Name = local.name }
}

# ── Locals: shortcuts a ARNs de secrets y URLs de ECR ────────────────────────

locals {
  secret = aws_secretsmanager_secret.secrets
  ecr    = aws_ecr_repository.repos

  log_config = { for svc in ["fastapi", "mcp-supabase", "mcp-logistics", "frontend"] :
    svc => {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.services[svc].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "ecs"
      }
    }
  }
}

# ── Task Definition: FastAPI ──────────────────────────────────────────────────

resource "aws_ecs_task_definition" "fastapi" {
  family                   = "${local.name}-fastapi"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "fastapi"
    image     = "${local.ecr["reflow-api"].repository_url}:latest"
    essential = true

    portMappings = [{
      name          = "fastapi"
      containerPort = 8000
      protocol      = "tcp"
    }]

    environment = [
      { name = "ENVIRONMENT", value = "production" },
      # Service Connect: MCP servers and Streamlit resolve these names internally
      { name = "MCP_SUPABASE_URL", value = "http://mcp-supabase:8001/mcp" },
      { name = "MCP_LOGISTICS_URL", value = "http://mcp-logistics:8002/mcp" },
    ]

    secrets = [
      { name = "JWT_SECRET", valueFrom = local.secret["reflow/jwt-secret"].arn },
      { name = "ADMIN_PASSWORD", valueFrom = local.secret["reflow/admin-password"].arn },
      { name = "OPENAI_API_KEY", valueFrom = local.secret["reflow/openai-api-key"].arn },
      { name = "SUPABASE_URL", valueFrom = local.secret["reflow/supabase-url"].arn },
      { name = "SUPABASE_SERVICE_KEY", valueFrom = local.secret["reflow/supabase-service-key"].arn },
      { name = "SUPABASE_DB_URL", valueFrom = local.secret["reflow/supabase-db-url"].arn },
      { name = "LANGFUSE_SECRET_KEY", valueFrom = local.secret["reflow/langfuse-secret-key"].arn },
      { name = "LANGFUSE_PUBLIC_KEY", valueFrom = local.secret["reflow/langfuse-public-key"].arn },
    ]

    logConfiguration = local.log_config["fastapi"]

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])

  tags = { Name = "${local.name}-fastapi" }
}

# ── Task Definition: MCP Supabase ─────────────────────────────────────────────

resource "aws_ecs_task_definition" "mcp_supabase" {
  family                   = "${local.name}-mcp-supabase"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "mcp-supabase"
    image     = "${local.ecr["reflow-mcp"].repository_url}:latest"
    essential = true
    command   = ["python", "-m", "backend.mcp.mcp_supabase"]

    portMappings = [{
      name          = "mcp-supabase"
      containerPort = 8001
      protocol      = "tcp"
    }]

    secrets = [
      { name = "OPENAI_API_KEY", valueFrom = local.secret["reflow/openai-api-key"].arn },
      { name = "SUPABASE_URL", valueFrom = local.secret["reflow/supabase-url"].arn },
      { name = "SUPABASE_SERVICE_KEY", valueFrom = local.secret["reflow/supabase-service-key"].arn },
    ]

    logConfiguration = local.log_config["mcp-supabase"]

    healthCheck = {
      command     = ["CMD-SHELL", "curl -s --connect-timeout 4 http://localhost:8001/mcp -o /dev/null || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 15
    }
  }])

  tags = { Name = "${local.name}-mcp-supabase" }
}

# ── Task Definition: MCP Logistics ────────────────────────────────────────────

resource "aws_ecs_task_definition" "mcp_logistics" {
  family                   = "${local.name}-mcp-logistics"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "mcp-logistics"
    image     = "${local.ecr["reflow-mcp"].repository_url}:latest"
    essential = true
    command   = ["python", "-m", "backend.mcp.mcp_logistics"]

    portMappings = [{
      name          = "mcp-logistics"
      containerPort = 8002
      protocol      = "tcp"
    }]

    secrets = [
      { name = "SUPABASE_URL", valueFrom = local.secret["reflow/supabase-url"].arn },
      { name = "SUPABASE_SERVICE_KEY", valueFrom = local.secret["reflow/supabase-service-key"].arn },
    ]

    logConfiguration = local.log_config["mcp-logistics"]

    healthCheck = {
      command     = ["CMD-SHELL", "curl -s --connect-timeout 4 http://localhost:8002/mcp -o /dev/null || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 15
    }
  }])

  tags = { Name = "${local.name}-mcp-logistics" }
}

# ── Task Definition: Frontend ─────────────────────────────────────────────────

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${local.name}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "frontend"
    image     = "${local.ecr["reflow-frontend"].repository_url}:latest"
    essential = true

    portMappings = [{
      name          = "frontend"
      containerPort = 8501
      protocol      = "tcp"
    }]

    environment = [
      # Streamlit calls FastAPI directly via Service Connect (no ALB hairpin)
      { name = "API_BASE_URL", value = "http://fastapi:8000" },
    ]

    logConfiguration = local.log_config["frontend"]

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8501/_stcore/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 15
    }
  }])

  tags = { Name = "${local.name}-frontend" }
}

# ── ECS Services ──────────────────────────────────────────────────────────────

resource "aws_ecs_service" "fastapi" {
  name            = "fastapi"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.fastapi.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.private_a.id]
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  # FastAPI registers itself as "fastapi" in Service Connect so Streamlit
  # can call it at http://fastapi:8000 without going through the ALB.
  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.main.arn

    service {
      port_name = "fastapi"
      client_alias {
        port     = 8000
        dns_name = "fastapi"
      }
    }
  }

  depends_on = [aws_lb_listener.http]

  tags = { Name = "${local.name}-fastapi" }
}

resource "aws_ecs_service" "mcp_supabase" {
  name            = "mcp-supabase"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.mcp_supabase.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.private_a.id]
    security_groups  = [aws_security_group.mcp.id]
    assign_public_ip = false
  }

  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.main.arn

    service {
      port_name = "mcp-supabase"
      client_alias {
        port     = 8001
        dns_name = "mcp-supabase"
      }
    }
  }

  tags = { Name = "${local.name}-mcp-supabase" }
}

resource "aws_ecs_service" "mcp_logistics" {
  name            = "mcp-logistics"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.mcp_logistics.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.private_a.id]
    security_groups  = [aws_security_group.mcp.id]
    assign_public_ip = false
  }

  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.main.arn

    service {
      port_name = "mcp-logistics"
      client_alias {
        port     = 8002
        dns_name = "mcp-logistics"
      }
    }
  }

  tags = { Name = "${local.name}-mcp-logistics" }
}

resource "aws_ecs_service" "frontend" {
  name            = "frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_a.id]
    security_groups  = [aws_security_group.frontend.id]
    assign_public_ip = true # public subnet: Fargate needs public IP to pull from ECR
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 8501
  }

  # Service Connect enabled as client so Streamlit can resolve "fastapi:8000"
  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.main.arn
  }

  depends_on = [aws_lb_listener.http]

  tags = { Name = "${local.name}-frontend" }
}
