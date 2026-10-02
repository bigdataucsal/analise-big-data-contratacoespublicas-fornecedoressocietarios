output "pg_host" {
  description = "Hostname do serviço PostgreSQL"
  value       = aiven_pg.banco_projeto.service_host
}

output "pg_port" {
  description = "Porta do serviço PostgreSQL"
  value       = aiven_pg.banco_projeto.service_port
}

output "pg_database" {
  description = "Banco padrão criado pela Aiven (confirme o nome no console)"
  value       = "defaultdb"
}

output "pg_user" {
  description = "Usuário padrão do serviço"
  value       = aiven_pg.banco_projeto.service_username
  sensitive   = true
}

output "pg_password" {
  description = "Senha do usuário padrão"
  value       = aiven_pg.banco_projeto.service_password
  sensitive   = true
}

output "pg_uri" {
  description = "URI de conexão do PostgreSQL"
  value       = aiven_pg.banco_projeto.service_uri
  sensitive   = true
}
