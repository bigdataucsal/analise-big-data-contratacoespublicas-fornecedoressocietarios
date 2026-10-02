variable "aiven_api_token" {
  description = "Token de API da Aiven (gerado no console). Nunca no repositório: use TF_VAR_aiven_api_token."
  type        = string
  sensitive   = true
}

variable "project_name" {
  description = "Nome do projeto na Aiven (aparece no canto superior esquerdo do console). Sem default: cada pessoa informa o seu."
  type        = string
}

variable "service_name" {
  description = "Nome do serviço PostgreSQL"
  type        = string
  default     = "pg-contratacoes"
}

variable "cloud_name" {
  description = "Nuvem/região do serviço. O plano gratuito só oferece algumas; confirme no console ao criar um serviço gratuito."
  type        = string
  default     = "do-sfo"
}

variable "plan" {
  description = "Plano do serviço. free-1-1gb é o plano gratuito (1 GB)."
  type        = string
  default     = "free-1-1gb"
}
