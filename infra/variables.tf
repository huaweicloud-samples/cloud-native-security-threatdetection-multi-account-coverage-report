# 变量集中定义（与 main.tf 拆分，便于复用与审阅）

variable "region" {
  description = "区域（同时用于默认项目名）"
  type        = string
  default     = "cn-north-4"
}

variable "project_name" {
  description = "项目名称，用于资源命名前缀"
  type        = string
  default     = "hss-coverage"
}

variable "agency_name" {
  description = "跨项目委托名称（所有成员项目保持一致，便于工具统一假定）"
  type        = string
  default     = "HssCoverageAgency"
}

variable "management_domain_name" {
  description = "管理账号域名（本委托的受托方，即运行报告工具的账号）"
  type        = string
}
