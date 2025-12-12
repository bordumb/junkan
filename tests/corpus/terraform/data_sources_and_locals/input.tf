# Test for Data Sources and Locals
provider "aws" {
  region = "us-west-2"
}

data "aws_s3_bucket" "existing" {
  bucket = "my-legacy-bucket"
}

data "aws_secretsmanager_secret_version" "creds" {
  secret_id = "db-creds"
}

locals {
  bucket_arn = data.aws_s3_bucket.existing.arn
  db_password = jsondecode(data.aws_secretsmanager_secret_version.creds.secret_string)["password"]
  
  common_tags = {
    Environment = "prod"
    Project     = "analytics"
  }
}

resource "aws_s3_object" "config" {
  bucket = local.bucket_arn # Indirect reference via local
  key    = "config.json"
  content = local.db_password
  tags    = local.common_tags
}