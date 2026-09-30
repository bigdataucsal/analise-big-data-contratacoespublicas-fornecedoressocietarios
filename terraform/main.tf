terraform {
  required_providers {
    aiven = {
      source  = "aiven/aiven"
      version = ">= 4.0.0"
    }
  }
}

provider "aiven" {
  api_token = var.aiven_api_token
}

resource "aiven_pg" "banco_projeto" {
  project      = var.project_name
  cloud_name = "do-sfo"
  plan         = "free-1-1gb"
  service_name = "pg-contratacoes"
}