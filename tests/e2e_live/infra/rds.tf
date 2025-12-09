resource "aws_db_instance" "payment_db_host" {
  allocated_storage    = 10
  db_name              = "mydb"
  engine               = "mysql"
  instance_class       = "db.t3.micro"
}
