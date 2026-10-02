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

# ATENÇÃO: o nome do recurso (banco_projeto) é o que está no tfstate da T1.
# Renomear este bloco faz o Terraform DESTRUIR o serviço e criar outro.
# Se precisar renomear, use um bloco "moved" e confira o plan antes.
resource "aiven_pg" "banco_projeto" {
  project      = var.project_name
  cloud_name   = var.cloud_name
  plan         = var.plan
  service_name = var.service_name

  # Proteção: o banco está em uso. Qualquer plan que peça destruição ou
  # recriação falha em vez de apagar os dados. Para um teste "do zero"
  # (terraform destroy), apague este bloco em uma cópia descartável.
  lifecycle {
    prevent_destroy = true
  }
}
