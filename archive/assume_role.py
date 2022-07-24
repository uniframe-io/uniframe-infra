import sys

import boto3

from helpers.prop_loader import CommonProperties, EnvDepProperties
from helpers.utils import id_gen

print("\nUse Boto3 update ecr readonly role assume role principal")

try:
    deploy_env = sys.argv[1]
except KeyError:
    raise ValueError(
        "Must give a environment name! For example, a testing env is `xxx-test`"
    )

env_props = EnvDepProperties.load(f"./conf/env_props.{deploy_env}.yaml")
comm_props = CommonProperties.load("./conf/comm_props.yaml")


iam = boto3.client("iam")
ssm = boto3.client("ssm")
ecr_readonly_role_arn = ssm.get_parameter(
    Name=id_gen(deploy_env, comm_props, "ssm-ecr-readonly-role")
)["Parameter"]["Value"]
backend_task_role_arn = ssm.get_parameter(
    Name=id_gen(deploy_env, comm_props, "ssm-backend-task-role")
)["Parameter"]["Value"]

ecr_readonly_role_name = ecr_readonly_role_arn.split("/")[-1]

response = iam.update_assume_role_policy(
    PolicyDocument=f"""{{
  "Version": "2012-10-17",
  "Statement": [
    {{
      "Effect": "Allow",
      "Principal": {{
        "AWS": ["{backend_task_role_arn}"]
      }},
      "Action": "sts:AssumeRole"
    }}
  ]
}}
    """,
    RoleName=ecr_readonly_role_name,
)
