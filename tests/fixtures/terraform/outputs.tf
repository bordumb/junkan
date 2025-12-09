output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "database_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.payment_db_host.endpoint
}

output "database_host" {
  description = "RDS hostname"
  value       = aws_db_instance.payment_db_host.address
}
