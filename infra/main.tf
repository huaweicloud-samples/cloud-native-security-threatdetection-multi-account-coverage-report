# ============================================================================
# 主机安全（HSS）覆盖报告 —— 跨项目委托（Delegation）IaC
# ============================================================================
# 本配置在每个成员项目中创建一个 IAM 委托（Agency），受托方为管理账号域名，
# 授予 HSS 只读权限。管理账号凭借该委托，可跨项目读取主机安全防护状态，
# 从而生成覆盖报告。
#
# 说明：
#   - 委托创建在“成员项目”所在域，受托方为“管理账号”域名。
#   - 每个成员项目均需执行一次本配置（见 docs/deployment-guide.md）。
#   - AK/SK 从环境变量读取，不硬编码。
# ============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    huaweicloud = {
      source  = "huaweicloud/huaweicloud"
      version = "~> 1.70"
    }
  }

  # 生产环境建议将状态文件存入 OBS 桶（替换 backend "local"）
  backend "local" {}
}

# ============================================================================
# Provider 配置
# ============================================================================

provider "huaweicloud" {
  region = var.region
  # AK/SK 由环境变量 HW_ACCESS_KEY / HW_SECRET_KEY 传入，不写入代码：
  # export HW_ACCESS_KEY="<AK>"
  # export HW_SECRET_KEY="<SK>"
}

# ============================================================================
# 跨项目委托：授予管理账号读取本成员项目 HSS 状态的权限
# 变量定义见 variables.tf
# ============================================================================

resource "huaweicloud_identity_agency" "hss_coverage" {
  name                  = var.agency_name
  description           = "Cross-project delegation for host security coverage reporting"
  duration              = "FOREVER"
  delegated_domain_name = var.management_domain_name

  project_role {
    # 委托生效后，管理账号可在本成员项目的默认项目中行使下列角色
    project = var.region
    roles = [
      "HSS ReadOnlyAccess",
    ]
  }
}
