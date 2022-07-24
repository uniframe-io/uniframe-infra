from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import aws_ssm as ssm
from aws_cdk import core

from helpers.prop_loader import CommonProperties, EnvDepProperties
from helpers.utils import id_gen


class DBStack(core.Stack):
    def __init__(
        self,
        app: core.App,
        stack_id: str,
        env: core.Environment,
        deploy_env: str,
        comm_props: CommonProperties,
        env_props: EnvDepProperties,
        vpc: ec2.Vpc,
    ) -> None:
        super().__init__(app, stack_id, env=env)

        """ Create Postgres in RDS """
        secret_generator = sm.SecretStringGenerator(
            secret_string_template='{ "username": "postgres" }',
            generate_string_key="password",
            password_length=8,
            exclude_punctuation=True,
        )
        secret = sm.Secret(
            self,
            "api-db-secret",
            generate_secret_string=secret_generator,
            secret_name=id_gen(deploy_env, comm_props, "api-db-secret"),
        )

        ssm.StringParameter(
            self,
            "ssm-pg-secret-name",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-pg-secret-name"
            ),  # hardcode the name because Github action will use it
            string_value=secret.secret_name,
        )

        DB_NAME = "nm"

        api_db = rds.DatabaseInstance(
            self,
            "api-pg",
            instance_identifier=id_gen(deploy_env, comm_props, "api-pg"),
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_12_2
            ),
            database_name=DB_NAME,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE2, ec2.InstanceSize.MICRO
            ),
            credentials=rds.Credentials.from_secret(secret),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.ISOLATED
            ),
            auto_minor_version_upgrade=False,
            multi_az=False,
            allocated_storage=10,
            storage_type=rds.StorageType.GP2,
            cloudwatch_logs_exports=["postgresql"],
            cloudwatch_logs_retention=logs.RetentionDays.ONE_WEEK,
            deletion_protection=False,
            delete_automated_backups=False,
            backup_retention=core.Duration.days(7),
            removal_policy=core.RemovalPolicy.DESTROY,
        )
        # only open 5432 for internal traffic
        api_db.connections.allow_from(
            other=ec2.Peer.ipv4(comm_props.vpc_default_cidr),
            port_range=ec2.Port.tcp(5432),
        )

        self.api_db = api_db

        ssm.StringParameter(
            self,
            "ssm-api-db-dns",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-api-db-dns"
            ),  # hardcode the name because Github action will use it
            string_value=api_db.db_instance_endpoint_address,
        )
        ssm.StringParameter(
            self,
            "ssm-api-db-name",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-api-db-name"
            ),  # hardcode the name because Github action will use it
            string_value=DB_NAME,
        )
