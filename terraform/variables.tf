variable "aiven_api_token" {
  description = "Token de API da Aiven"
  type        = string
  sensitive   = true
}

variable "project_name" {
  description = "Nome do projeto na Aiven"
  type        = string
  default     = "afonso-214a"
}