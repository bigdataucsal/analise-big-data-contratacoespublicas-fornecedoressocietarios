output "database_uri" {
  description = "URI de conexão do PostgreSQL"
  value       = aiven_pg.banco_projeto.service_uri
  sensitive   = true
}