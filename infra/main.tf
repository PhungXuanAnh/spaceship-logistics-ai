# =============================================================================
# Spaceship Logistics AI - minimal AWS deploy
# Architecture: single Ubuntu 22.04 EC2 (t3.small) running docker compose:
#   caddy (80/443, auto Let's Encrypt) -> backend (uvicorn :8000) + frontend (next :3000)
#   sqlite DB lives on the box (bind mount /var/spaceship/data)
# Why this shape: ~$15/mo, no ALB, no RDS, no NAT gateway. One IP to point Namecheap at.
# =============================================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.50" }
    tls = { source = "hashicorp/tls", version = "~> 4.0" }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile
  default_tags {
    tags = {
      Project     = "spaceship-logistics-ai"
      ManagedBy   = "terraform"
      Owner       = "phungxuananh"
      CostCenter  = "portfolio-demo"
    }
  }
}

variable "region"       { default = "ap-southeast-1" }
variable "aws_profile"  { default = "alexander.xuananh" }
variable "instance_type" { default = "t3.small" }
variable "domain"       { default = "spaceship.xuananh1.site" }
variable "demo_email"   { default = "demo@spaceship.test" }
variable "demo_password" {
  sensitive = true
  default   = "demo123"
}
variable "jwt_secret" {
  sensitive   = true
  description = "Random 32+ char secret. Override via TF_VAR_jwt_secret env var."
  default     = "change-me-in-production-use-a-32-char-random-string"
}

# ---------- key pair ----------
resource "tls_private_key" "deploy" {
  algorithm = "ED25519"
}

resource "aws_key_pair" "deploy" {
  key_name   = "spaceship-deploy"
  public_key = tls_private_key.deploy.public_key_openssh
}

resource "local_file" "private_key" {
  content         = tls_private_key.deploy.private_key_openssh
  filename        = "${path.module}/spaceship-deploy.pem"
  file_permission = "0600"
}

# ---------- networking: use default VPC ----------
data "aws_vpc" "default" { default = true }

# Default VPC exists but has no default subnets in this region — create one in AZ 'a'.
# aws_default_subnet only operates on the default VPC; safe to manage with terraform.
resource "aws_default_subnet" "a" {
  availability_zone = "${var.region}a"
  tags = { Name = "spaceship-default-${var.region}a" }
}

# Default VPC also has no internet gateway in this region — create + attach one.
# NOTE: a previous broken IGW had left a blackhole 0.0.0.0/0 route in the main
# route table (deleted manually before re-applying); we now manage the route here.
resource "aws_internet_gateway" "default" {
  vpc_id = data.aws_vpc.default.id
  tags   = { Name = "spaceship-default-igw" }
}

resource "aws_route" "default_igw" {
  route_table_id         = data.aws_vpc.default.main_route_table_id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.default.id
}

resource "aws_security_group" "web" {
  name        = "spaceship-web"
  description = "Spaceship Logistics demo: HTTP/HTTPS/SSH"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP for ACME challenge + redirect"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "SSH (deploy + ops)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---------- AMI: Canonical Ubuntu 22.04 LTS x86_64 ----------
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# ---------- EC2 ----------
resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.deploy.key_name
  vpc_security_group_ids = [aws_security_group.web.id]
  subnet_id              = aws_default_subnet.a.id
  associate_public_ip_address = true

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = <<-EOF
    #!/bin/bash
    set -eux
    apt-get update -y
    apt-get install -y ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    usermod -aG docker ubuntu
    mkdir -p /var/spaceship/{data,logs,caddy_data,caddy_config}
    chown -R 1000:1000 /var/spaceship
    touch /var/log/spaceship-bootstrap-done
  EOF

  tags = { Name = "spaceship-app" }
}

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
}

# ---------- outputs ----------
output "public_ip"   { value = aws_eip.app.public_ip }
output "ssh_command" { value = "ssh -i ${path.module}/spaceship-deploy.pem ubuntu@${aws_eip.app.public_ip}" }
output "domain"      { value = var.domain }
output "url"         { value = "https://${var.domain}" }
