terraform {
  required_version = "~> 1.9"
  backend "s3" { bucket = "atlas-tfstate" dynamodb_table = "atlas-tflock" }
}
