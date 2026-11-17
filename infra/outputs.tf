output "agency_name" {
  description = "已创建的委托名称"
  value       = huaweicloud_identity_agency.hss_coverage.name
}

output "delegated_domain_name" {
  description = "受托方（管理账号）域名"
  value       = huaweicloud_identity_agency.hss_coverage.delegated_domain_name
}

output "project" {
  description = "委托生效的项目"
  value       = var.region
}
