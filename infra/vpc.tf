# ── VPC propia: tfm-reflow ───────────────────────────────────────────────────
#
# Arquitectura de red:
#   Subnet pública A  (eu-west-1a) → ALB + Streamlit (ECS Fargate)
#   Subnet pública B  (eu-west-1b) → ALB únicamente (AWS exige ≥2 AZs en ALB)
#   Subnet privada A  (eu-west-1a) → FastAPI + MCP Supabase + MCP Logistics
#
# Los servicios privados salen a internet (Supabase, OpenAI, ECR) vía NAT
# Gateway. Coste: ~$0.045/hora — destruye con `terraform destroy` al acabar.
#
# Todos los recursos heredan los tags Project/Environment/ManagedBy definidos
# en main.tf (default_tags del provider). Los tags Name se añaden aquí.

# ── VPC ──────────────────────────────────────────────────────────────────────

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "tfm-reflow" }
}

# ── Internet Gateway (salida a internet para subnets públicas) ────────────────

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "tfm-reflow-igw" }
}

# ── Subnets públicas ──────────────────────────────────────────────────────────

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = { Name = "tfm-reflow-public-a" }
}

# Segunda subnet pública requerida por el ALB (necesita ≥2 AZs distintas).
resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "${var.aws_region}b"
  map_public_ip_on_launch = true

  tags = { Name = "tfm-reflow-public-b" }
}

# ── Subnet privada ────────────────────────────────────────────────────────────

resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.10.0/24"
  availability_zone = "${var.aws_region}a"

  tags = { Name = "tfm-reflow-private-a" }
}

# ── NAT Gateway (salida a internet para la subnet privada) ────────────────────
#
# Coste: ~$0.045/hora mientras esté activo.
# Se destruye con `terraform destroy` al acabar las pruebas.

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = { Name = "tfm-reflow-nat-eip" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public_a.id

  tags = { Name = "tfm-reflow-nat" }

  # El IGW debe existir antes de crear el NAT Gateway.
  depends_on = [aws_internet_gateway.main]
}

# ── Route tables ──────────────────────────────────────────────────────────────

# Pública: tráfico saliente va directamente al Internet Gateway.
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "tfm-reflow-rt-public" }
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

# Privada: tráfico saliente va al NAT Gateway (que está en la subnet pública).
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = { Name = "tfm-reflow-rt-private" }
}

resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private.id
}
