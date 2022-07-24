import yaml
from typing import List, Optional, Dict


from pydantic import BaseModel, validator
from aws_cdk import aws_ecs as ecs


class FargateContainerDef(BaseModel):
    name: str
    essential: bool
    memory_limit_mib: int
    memory_reservation_mib: int
    cpu: int
    port: Optional[int] = None
    expose_port: Optional[int] = None
    protocol: Optional[ecs.Protocol] = ecs.Protocol.TCP
    command: Optional[List] = None
    ulimits: Optional[Dict] = None


class FargateTaskDef(BaseModel):
    task_memory_limit_mib: int
    task_cpu: int
    port: int
    container_def_l: List[FargateContainerDef]


class EksHostZone(BaseModel):
    id: str
    domain_name: str


class StorageConfig(BaseModel):
    volume_gb: int


class EbsStorage(BaseModel):
    general_storage: StorageConfig


class EksNodeGroup(BaseModel):
    id_surfix: str
    instance_type: str
    min_size: int
    max_size: int
    label: dict
    node_label: dict
    tags: dict
    taints: dict


class WhitelistIP(BaseModel):
    ip: str
    entity: str
    enable_80: Optional[bool] = True


class EksClusterCfg(BaseModel):
    whitelist_ips: List[WhitelistIP]
    node_group: List[EksNodeGroup]


class EnvDepProperties(BaseModel):
    whitelist_ips: List[WhitelistIP]
    ebs_storage: EbsStorage
    eks_host_zone: EksHostZone
    eks_cluster_cfg: EksClusterCfg
    backend_task_def: FargateTaskDef
    frontend_task_def: FargateTaskDef
    doc_task_def: FargateTaskDef

    @classmethod
    def load(
            cls,
            config_f: str,
    ) -> "EnvDepProperties":

        with open(config_f) as f:
            return EnvDepProperties(**yaml.load(f, Loader=yaml.FullLoader))


class CommonProperties(BaseModel):
    product_prefix: str
    vpc_default_cidr: str
    subnet_cidr_mask: int
    ecr_assume_role_expiration_min: int
    cd_user_arn: str

    @classmethod
    def load(
            cls,
            config_f: str,
    ) -> "CommonProperties":

        with open(config_f) as f:
            return CommonProperties(**yaml.load(f, Loader=yaml.FullLoader))
