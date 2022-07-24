import aws_cdk.aws_ssm as ssm
from aws_cdk import aws_iam as iam
from aws_cdk import core

from helpers.prop_loader import CommonProperties, EnvDepProperties
from helpers.utils import id_gen


class AssumeRoleStack(core.Stack):
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

        backend_role_arn = ssm.StringParameter.value_for_string_parameter(
            self, id_gen(deploy_env, comm_props, "ssm-backend-task-role")
        )
        backend_task_role = iam.Role.from_role_arn(
            self, id="backend-task-role", role_arn=backend_role_arn
        )

        ecr_readonly_arn = ssm.StringParameter.value_for_string_parameter(
            self, id_gen(deploy_env, comm_props, "ssm-ecr-readonly-role")
        )
        ecr_readonly_role = iam.Role.from_role_arn(
            self,
            id="ecr-readonly-role",
            role_arn=ecr_readonly_arn,
            mutable=True,
        )

        # add assume role policy to backend task role
        backend_task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                effect=iam.Effect.ALLOW,
                resources=[ecr_readonly_role.role_arn],
            )
        )

        # --------------------
        # N.B. failed to add trust relationship to ecr_readonly_role by CDK!
        # Do it in backend code by boto3
        # --------------------
        # add trust relationship
        # ecr_readonly_role.grant(
        #     iam.ArnPrincipal(backend_task_role.role_arn),
        #     "sts:AssumeRole"
        # )
