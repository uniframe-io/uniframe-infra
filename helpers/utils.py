from typing import Dict
from helpers.prop_loader import CommonProperties
import requests


def id_gen(deploy_env: str, comm_props: CommonProperties, resource_name: str) -> str:
    return f"{comm_props.product_prefix}-{deploy_env}-{resource_name}"


def load_alb_policy_json(url: str) -> Dict:
    resp = requests.get(url=url)
    return resp.json()


def get_aws_load_balancer_controller_repo(region_name: str) -> str:
    alb_image_mapping = {
        'me-south-1': '558608220178',
        'eu-south-1': '590381155156',
        'ap-northeast-1': '602401143452',
        'ap-northeast-2': '602401143452',
        'ap-south-1': '602401143452',
        'ap-southeast-1': '602401143452',
        'ap-southeast-2': '602401143452',
        'ca-central-1': '602401143452',
        'eu-central-1': '602401143452',
        'eu-north-1': '602401143452',
        'eu-west-1': '602401143452',
        'eu-west-2': '602401143452',
        'eu-west-3': '602401143452',
        'sa-east-1': '602401143452',
        'us-east-1': '602401143452',
        'us-east-2': '602401143452',
        'us-west-1': '602401143452',
        'us-west-2': '602401143452',
        'ap-east-1': '800184023465',
        'af-south-1': '877085696533',
        'cn-north-1': '918309763551',
        'cn-northwest-1': '961992271922',
    }

    image_account_id = alb_image_mapping[region_name]

    return f"{image_account_id}.dkr.ecr.{region_name}.amazonaws.com/amazon/aws-load-balancer-controller"
