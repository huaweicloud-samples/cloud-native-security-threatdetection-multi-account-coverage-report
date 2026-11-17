"""主机安全（HSS）跨项目覆盖报告。

针对枚举到的每个项目与区域，查询主机安全防护状态，输出覆盖报告 CSV。
覆盖状态判定：
  - 未开启防护        → NO_PROTECTION（Issue: Protection disabled）
  - 已开启且 Agent 在线 → HEALTHY
  - 已开启但 Agent 离线 → UNHEALTHY（Issue: Agent <状态>）

用法示例：
  export HW_ACCESS_KEY=... HW_SECRET_KEY=... HW_DELEGATED_DOMAIN_ID=...
  python3 src/coverage_report.py --agency-name HssCoverageAgency \
      --all-projects --all-regions
"""

import argparse
import csv
import os
import sys

from huaweicloudsdkcore.http.http_config import HttpConfig
from huaweicloudsdkhss.v5 import HssClient, ListHostStatusRequest

# 将当前目录加入路径，便于导入 adapter 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adapter.cloud_iterator import CloudIterator  # noqa: E402

PAGE_LIMIT = 100
RESOURCE_TYPE = "ECS"


def _fetch_hosts(client, region, enterprise_project_id=None):
    """分页拉取某个区域下的全部主机状态。"""
    hosts = []
    offset = 0
    while True:
        req = ListHostStatusRequest()
        req.region = region
        req.limit = PAGE_LIMIT
        req.offset = offset
        if enterprise_project_id:
            req.enterprise_project_id = enterprise_project_id
        resp = client.list_host_status(req)
        batch = getattr(resp, "data_list", None) or []
        hosts.extend(batch)
        offset += PAGE_LIMIT
        total = getattr(resp, "total_num", None) or 0
        if not batch or offset >= total:
            break
    return hosts


def _coverage_status(protect_status, agent_status):
    """将防护状态与 Agent 状态映射为覆盖结论。"""
    protected = str(protect_status).strip().lower() in ("opened", "1", "enabled", "true")
    agent = str(agent_status).strip().upper()
    if not protected:
        return "NO_PROTECTION", "Protection disabled"
    if agent == "ONLINE":
        return "HEALTHY", "N.A"
    return "UNHEALTHY", f"Agent {agent or 'UNKNOWN'}"


def hss_coverage(project_id, region, credential, payload):
    """针对单个（项目, 区域）查询主机安全覆盖状态的回调函数。"""
    response = {"project_id": project_id, "region": region}
    try:
        enterprise_project_id = (payload or {}).get("enterprise_project_id")
        client = (
            HssClient.new_builder()
            .with_http_config(HttpConfig.get_default_config())
            .with_credentials(credential)
            .with_endpoint(f"https://hss.{region}.myhuaweicloud.com")
            .build()
        )
        hosts = _fetch_hosts(client, region, enterprise_project_id)
        rows = []
        for h in hosts:
            cs, issue = _coverage_status(
                getattr(h, "protect_status", ""), getattr(h, "agent_status", "")
            )
            rows.append(
                {
                    "ResourceId": getattr(h, "host_id", ""),
                    "ResourceType": RESOURCE_TYPE,
                    "ProtectStatus": getattr(h, "protect_status", ""),
                    "AgentStatus": getattr(h, "agent_status", ""),
                    "CoverageStatus": cs,
                    "Issue": issue,
                }
            )
        response["response"] = rows
    except Exception as error:
        response["response"] = [{"Error": str(error)}]
    return response


def _build_report_row(project_id, region, item):
    if "Error" in item:
        return [project_id, region, item.get("Error"), "", "", "", "", ""]
    return [
        project_id,
        region,
        item.get("ResourceId", ""),
        item.get("ResourceType", ""),
        item.get("ProtectStatus", ""),
        item.get("AgentStatus", ""),
        item.get("CoverageStatus", ""),
        item.get("Issue", ""),
    ]


def main():
    arg_parser = argparse.ArgumentParser(description="主机安全跨项目覆盖报告")
    arg_parser.add_argument(
        "--agency-name",
        default="HssCoverageAgency",
        help="成员项目中创建的 IAM 委托名称（须已存在）",
    )
    arg_parser.add_argument(
        "--all-projects", action="store_true", help="枚举当前账号可访问的全部项目"
    )
    arg_parser.add_argument(
        "--project-ids", type=str, default=None, help="逗号分隔的项目 ID 列表"
    )
    arg_parser.add_argument("--all-regions", action="store_true", help="枚举全部区域")
    arg_parser.add_argument(
        "--regions", type=str, default=None, help="逗号分隔的区域列表"
    )
    arg_parser.add_argument(
        "--enterprise-project-id",
        type=str,
        default=None,
        help="可选：按企业项目过滤主机（留空表示全部）",
    )
    arg_parser.add_argument(
        "--output", type=str, default="report.csv", help="输出 CSV 文件路径"
    )
    args = arg_parser.parse_args()

    if not args.all_projects and args.project_ids is None:
        print("必须指定 --all-projects 或 --project-ids")
        return 1
    if not args.all_regions and args.regions is None:
        print("必须指定 --all-regions 或 --regions")
        return 1

    iterator = CloudIterator(agency_name=args.agency_name)
    if args.all_projects:
        iterator.all_projects()
    else:
        iterator.add_projects(args.project_ids.split(","))
    if args.all_regions:
        iterator.all_regions()
    else:
        iterator.add_regions(args.regions.split(","))

    payload = {}
    if args.enterprise_project_id:
        payload["enterprise_project_id"] = args.enterprise_project_id

    all_results = iterator.iterate(hss_coverage, payload)

    print(f"写入结果到 {args.output}")
    with open(args.output, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                "ProjectId",
                "Region",
                "ResourceId",
                "ResourceType",
                "ProtectStatus",
                "AgentStatus",
                "CoverageStatus",
                "Issue",
            ]
        )
        for project_id, regions_data in all_results.items():
            for region, items in regions_data.items():
                if not items:
                    writer.writerow(
                        [project_id, region, "No Coverage Detected", "", "", "", "", ""]
                    )
                else:
                    for item in items:
                        writer.writerow(_build_report_row(project_id, region, item))
    return 0


if __name__ == "__main__":
    sys.exit(main())
