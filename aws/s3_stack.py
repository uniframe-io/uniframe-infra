from aws_cdk import aws_s3
from aws_cdk import aws_ssm as ssm
from aws_cdk import core
from aws_cdk.aws_s3 import BlockPublicAccess, LifecycleRule
from aws_cdk.core import Duration

from helpers.prop_loader import CommonProperties, EnvDepProperties
from helpers.utils import id_gen


class S3Stack(core.Stack):
    def __init__(
        self,
        app: core.App,
        id: str,
        env: core.Environment,
        deploy_env: str,
        comm_props: CommonProperties,
        env_props: EnvDepProperties,
    ) -> None:
        super().__init__(app, id, env=env)

        # S3 bucket for storing data
        # TODO: lifecycle need to be read from Customer Config
        # TODO: we might need a global configuration server, such as etcd or zookeeper
        data_bucket = aws_s3.Bucket(
            self,
            id="data",
            block_public_access=BlockPublicAccess(
                block_public_acls=True,
                block_public_policy=True,
                ignore_public_acls=True,
                restrict_public_buckets=True,
            ),
            bucket_name=id_gen(deploy_env, comm_props, "data"),
            lifecycle_rules=[LifecycleRule(expiration=Duration.days(30))],
        )

        """ Parameter stores for S3 """
        ssm.StringParameter(
            self,
            "ssm-s3-data-bucket-name",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-s3-data-bucket-name"
            ),  # hardcode the name because Github action will use it
            string_value=data_bucket.bucket_name,
        )

        # S3 bucket for load balancer logs
        lb_log_bucket = aws_s3.Bucket(
            self,
            id="lb-logs",
            block_public_access=BlockPublicAccess(
                block_public_acls=True,
                block_public_policy=True,
                ignore_public_acls=True,
                restrict_public_buckets=True,
            ),
            bucket_name=id_gen(deploy_env, comm_props, "lb-logs"),
            lifecycle_rules=[LifecycleRule(expiration=Duration.days(30))],
        )

        self.lb_log_bucket = lb_log_bucket
