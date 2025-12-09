# Infrastructure that provides values for the Python app's env vars

resource "aws_db_instance" "main" {
  identifier = "main-database"
  engine     = "postgres"
}

resource "aws_elasticache_cluster" "main" {
  cluster_id = "main-redis"
  engine     = "redis"
}

resource "aws_s3_bucket" "uploads" {
  bucket = "myapp-uploads"
}

output "database_host" {
  description = "Database host for DATABASE_HOST env var"
  value       = aws_db_instance.main.address
}

output "database_name" {
  description = "Database name for DATABASE_NAME env var"  
  value       = aws_db_instance.main.db_name
}

output "redis_host" {
  description = "Redis host for REDIS_HOST env var"
  value       = aws_elasticache_cluster.main.cache_nodes[0].address
}

output "s3_bucket" {
  description = "S3 bucket name for S3_BUCKET env var"
  value       = aws_s3_bucket.uploads.id
}
