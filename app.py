import os

from aws_cdk import core

from aws.db_stack import DBStack
from aws.foundation_stack import FoundationStack
from aws.s3_stack import S3Stack
from aws.service_stack_eks_managed import EksManagedStack
from helpers.prop_loader import CommonProperties, EnvDepProperties
from helpers.utils import id_gen

try:
    deploy_env = os.environ["DEPLOY_ENV"]
except KeyError:
    raise ValueError(
        "Must give a environment name! For example, a testing env is `xxx-test`"
    )

env_props = EnvDepProperties.load(f"./conf/env_props.{deploy_env}.yaml")
comm_props = CommonProperties.load("./conf/comm_props.yaml")


app = core.App()

env = core.Environment(
    account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region=os.environ["CDK_DEFAULT_REGION"],
)

foundation_stack = FoundationStack(
    app,
    id_gen(deploy_env, comm_props, "foundation"),
    env=env,
    deploy_env=deploy_env,
    comm_props=comm_props,
    env_props=env_props,
)

s3_stack = S3Stack(
    app,
    id_gen(deploy_env, comm_props, "s3"),
    env=env,
    deploy_env=deploy_env,
    comm_props=comm_props,
    env_props=env_props,
)

db_stack = DBStack(
    app,
    id_gen(deploy_env, comm_props, "db"),
    env=env,
    deploy_env=deploy_env,
    comm_props=comm_props,
    env_props=env_props,
    vpc=foundation_stack.vpc,
)

eks_managed_stack = EksManagedStack(
    app,
    id_gen(deploy_env, comm_props, "eks-service"),
    vpc=foundation_stack.vpc,
    api_db=db_stack.api_db,
    env=env,
    deploy_env=deploy_env,
    comm_props=comm_props,
    env_props=env_props,
    elb_sg=foundation_stack.elb_sg,
)

app.synth()
