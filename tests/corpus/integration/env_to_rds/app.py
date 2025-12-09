"""Application that reads env vars provisioned by Terraform."""
import os

# Database connection - should stitch to aws_db_instance.main
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT", "5432")
DATABASE_NAME = os.getenv("DATABASE_NAME", "myapp")
DATABASE_USER = os.getenv("DATABASE_USER")
DATABASE_PASSWORD = os.environ["DATABASE_PASSWORD"]

# Redis connection - should stitch to aws_elasticache_cluster.main
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")

# S3 bucket - should stitch to aws_s3_bucket.uploads
S3_BUCKET = os.getenv("S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")


def get_database_url():
    """Construct database URL from env vars."""
    return f"postgresql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
