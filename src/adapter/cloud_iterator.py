"""跨项目安全覆盖报告 —— 跨项目迭代器。

在多个项目与区域上并发执行给定函数，提供跨项目的只读访问能力。
本实现通过 IAM 委托（Agency）获取临时访问密钥，实现对成员项目资源的只读访问。

核心能力：
  - 枚举项目（keystone_list_auth_projects）与区域（keystone_list_regions）
  - 为每个（项目, 区域）通过委托获取临时凭证
  - 并发执行用户提供的函数，返回 {项目: {区域: 结果}} 结构
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.http.http_config import HttpConfig
from huaweicloudsdkcore.exceptions import exceptions

from huaweicloudsdkiam.v3 import (
    IamClient,
    AgencyAuth,
    AgencyAuthIdentity,
    IdentityAssumerole,
    CreateTemporaryAccessKeyByAgencyRequest,
    CreateTemporaryAccessKeyByAgencyRequestBody,
)

MAX_WORKERS = 10
IAM_ENDPOINT = "https://iam.myhuaweicloud.com"


class CloudIterator:
    """枚举项目与区域，并为每个（项目, 区域）构建临时凭证后并发执行函数。"""

    def __init__(self, agency_name, management_region="cn-north-4", delegated_domain_id=None):
        self.agency_name = agency_name
        self.management_region = management_region
        self.delegated_domain_id = delegated_domain_id or os.environ.get("HW_DELEGATED_DOMAIN_ID")

        self.projects = set()
        self.regions = set()

        ak = os.environ.get("HW_ACCESS_KEY")
        sk = os.environ.get("HW_SECRET_KEY")
        if not ak or not sk:
            raise RuntimeError("环境变量 HW_ACCESS_KEY / HW_SECRET_KEY 未设置")
        # 管理账号凭证（用于枚举项目/区域、并假定委托获取临时密钥）
        # 默认采用域级（Domain-Scoped）令牌；若显式设置 HW_PROJECT_ID 则使用项目级令牌。
        # 注意：HW_PROJECT_ID 必须是真实项目 ID（UUID）；传入区域名（如 cn-north-4）会导致鉴权失败。
        project_id = os.environ.get("HW_PROJECT_ID") or None
        self._mgmt_cred = BasicCredentials(ak=ak, sk=sk, project_id=project_id)
        self.iam_client = (
            IamClient.new_builder()
            .with_http_config(HttpConfig.get_default_config())
            .with_credentials(self._mgmt_cred)
            .with_endpoint(IAM_ENDPOINT)
            .build()
        )

    def all_projects(self):
        """枚举当前账号可访问的全部项目。"""
        resp = self.iam_client.keystone_list_auth_projects()
        for p in (resp.projects or []):
            self.projects.add(p.id)
        return self

    def add_projects(self, values):
        self.projects.update(set(values))
        return self

    def all_regions(self):
        """枚举全部区域。"""
        resp = self.iam_client.keystone_list_regions()
        for r in (resp.regions or []):
            self.regions.add(r.id)
        return self

    def add_regions(self, values):
        self.regions.update(set(values))
        return self

    def _build_temporary_credentials(self, project_id):
        """通过委托获取目标项目的临时访问密钥。"""
        if not self.delegated_domain_id:
            raise RuntimeError("缺少受托域 ID（HW_DELEGATED_DOMAIN_ID）")
        req = CreateTemporaryAccessKeyByAgencyRequest()
        req.body = CreateTemporaryAccessKeyByAgencyRequestBody(
            auth=AgencyAuth(
                identity=AgencyAuthIdentity(
                    methods=["assume_role"],
                    assume_role=IdentityAssumerole(
                        agency_name=self.agency_name,
                        domain_id=self.delegated_domain_id,
                    ),
                )
            )
        )
        resp = self.iam_client.create_temporary_access_key_by_agency(req)
        cred = resp.credential
        # 临时凭证需通过 with_security_token 注入安全令牌（huaweicloudsdkcore 该版本
        # 的 BasicCredentials 构造器不接受 security_token 关键字参数）
        return (
            BasicCredentials(ak=cred.access, sk=cred.secret, project_id=project_id)
            .with_security_token(cred.securitytoken)
        )

    def iterate(self, function, payload=None):
        print("开始迭代")
        results = {}
        futures = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for project_id in self.projects:
                for region in self.regions:
                    creds = self._build_temporary_credentials(project_id)
                    futures.append(
                        executor.submit(
                            self._run, function, project_id, region, creds, payload
                        )
                    )
        for future in as_completed(futures):
            try:
                res = future.result()
                results.setdefault(res["project_id"], {})[res["region"]] = res.get("response")
            except Exception as error:
                print(f"迭代异常: {error}")
        return results

    @staticmethod
    def _run(function, project_id, region, creds, payload):
        return function(project_id=project_id, region=region, credential=creds, payload=payload)
