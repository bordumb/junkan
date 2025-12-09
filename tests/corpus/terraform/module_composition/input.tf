# Terraform module composition - tests module source resolution

terraform {
  required_version = ">= 1.0"
}

# Local module
module "vpc" {
  source = "./modules/vpc"
  
  cidr_block = var.vpc_cidr
  name       = "main"
}

# Registry module
module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.3.0"
  
  identifier = "main-db"
  
  engine            = "postgres"
  engine_version    = "15"
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  
  db_name  = "myapp"
  username = var.db_username
  password = var.db_password
  
  vpc_security_group_ids = [module.vpc.security_group_id]
  subnet_ids             = module.vpc.private_subnet_ids
  
  family = "postgres15"
  major_engine_version = "15"
}

# GitHub module
module "lambda" {
  source = "github.com/terraform-aws-modules/terraform-aws-lambda?ref=v6.0.0"
  
  function_name = "my-function"
  handler       = "index.handler"
  runtime       = "python3.11"
  source_path   = "../src/lambda"
}

# Variables
variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "db_username" {
  type      = string
  sensitive = true
}

variable "db_password" {
  type      = string
  sensitive = true
}

# Outputs that reference module outputs
output "vpc_id" {
  value = module.vpc.vpc_id
}

output "db_endpoint" {
  value = module.rds.db_instance_endpoint
}

output "lambda_arn" {
  value = module.lambda.lambda_function_arn
}
