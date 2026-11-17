# 部署指导书

本指导书说明如何把「主机安全跨项目覆盖报告」这套实践落地。整体分为两步：先在每个成员项目中部署 **IAM 委托**，再在管理项目中配置并运行报告工具。

> 所有命令中的路径均使用相对路径；请在仓库根目录下执行。

## 1. 前置准备

- 一台可联网的主机（推荐 Python 3.9 及以上）。
- 安装 Terraform（>= 1.5）。
- 具备「管理项目」的访问密钥（AK/SK），以及各「成员项目」的部署权限（用于创建委托）。
- 记录以下信息，后续步骤会用到：
  - 管理项目域名（运行报告工具的账号域名）。
  - 各成员项目的项目 ID。

## 2. 在每个成员项目部署跨项目委托

依次在每个成员项目中创建授权委托。以成员项目 A 为例：

```bash
# 进入基础设施目录
cd infra

# 配置该成员项目的访问密钥（仅用于本次部署，请勿硬编码进文件）
export HW_ACCESS_KEY="<成员项目 AK>"
export HW_SECRET_KEY="<成员项目 SK>"

# 预览即将创建的资源
terraform init
terraform plan \
  -var="management_domain_name=<管理项目域名>"

# 确认无误后创建委托
terraform apply \
  -var="management_domain_name=<管理项目域名>"
```

对每一个成员项目重复上述步骤（替换对应的访问密钥与项目上下文）。`terraform.tfvars.example` 给出了变量示例，可复制为 `terraform.tfvars` 后填写。

部署完成后，成员项目中会出现一个名为 `HssCoverageAgency` 的委托，受托方为管理项目域名，拥有 HSS 只读权限。

## 3. 配置运行环境（管理项目）

回到运行报告工具的主机，配置管理项目的访问密钥与受托域信息：

```bash
# 进入仓库根目录
cd <本仓库根目录>

# 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
python3 -m pip install -r requirements.txt

# 配置管理项目凭据与受托域
export HW_ACCESS_KEY="<管理项目 AK>"
export HW_SECRET_KEY="<管理项目 SK>"
export HW_DELEGATED_DOMAIN_ID="<成员项目所属域 ID>"
```

`HW_DELEGATED_DOMAIN_ID` 为成员项目所属域的 ID（即委托创建所在的域）。同一企业组织下的成员项目通常同属一个域 ID。

## 4. 运行覆盖报告

全量巡检（枚举所有可访问项目与所有区域）：

```bash
python3 src/coverage_report.py \
  --agency-name HssCoverageAgency \
  --all-projects --all-regions
```

指定范围巡检：

```bash
python3 src/coverage_report.py \
  --agency-name HssCoverageAgency \
  --project-ids <项目ID1>,<项目ID2> \
  --regions cn-north-4,cn-east-3
```

工具会在当前目录生成 `report.csv`。

## 5. 查看结果

用表格软件打开 `report.csv`，或直接在终端查看：

```bash
cat report.csv
```

重点关注 `CoverageStatus` 列为 `NO_PROTECTION` 或 `UNHEALTHY` 的主机，它们代表防护缺口或 Agent 上报异常。

## 6. 释放资源（可选）

若不再需要跨项目委托，可在各成员项目的 `infra` 目录下执行：

```bash
cd infra
terraform destroy
```

执行后委托被移除，相关临时密钥随之失效。
