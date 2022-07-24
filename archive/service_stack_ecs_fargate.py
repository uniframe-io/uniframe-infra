import aws_cdk.aws_certificatemanager as acm
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_ssm as ssm
from aws_cdk import core

from helpers.prop_loader import CommonProperties, EnvDepProperties
from helpers.utils import id_gen


class ServiceFargateStack(core.Stack):
    def __init__(
        self,
        app: core.App,
        stack_id: str,
        env: core.Environment,
        deploy_env: str,
        comm_props: CommonProperties,
        env_props: EnvDepProperties,
        vpc: ec2.Vpc,
        api_db: rds.DatabaseInstance,
        lb: elbv2.ApplicationLoadBalancer,
        backend_repo: ecr.Repository,
        frontend_repo: ecr.Repository,
        redis_repo: ecr.Repository,
        cert_manager: acm.Certificate,
        doc_repo: ecr.Repository,
    ) -> None:
        super().__init__(app, stack_id, env=env)

        """ Create ECS cluster """
        cluster = ecs.Cluster(self, id="fargate-cluster", vpc=vpc)  # type: ignore
        cluster.node.add_dependency(api_db)

        """ ECS security group"""
        fargate_sg = ec2.SecurityGroup(
            self,
            "fargate-sg",
            vpc=vpc,  # type: ignore
            allow_all_outbound=True,
            description="SG for Fargate",
        )
        fargate_sg.add_ingress_rule(
            ec2.Peer.ipv4(comm_props.vpc_default_cidr),
            ec2.Port.all_tcp(),
            description="allow all internal traffic",
        )

        """ Backend ECS task definition """
        backend_task_role = iam.Role(
            self,
            "backend-task-iam-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        # TODO: refine the S3 policy!!!
        # Add a managed s3 policy to a Role
        backend_task_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess")
        )

        # TODO: refine the secret manager policy
        backend_task_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "SecretsManagerReadWrite"
            )
        )

        # The code below doesn't work. Why?
        # backend_task_role.add_to_policy(
        #     iam.PolicyStatement(
        #         actions=[
        #             "secretsmanager:*"
        #         ],
        #         effect=iam.Effect.ALLOW,
        #         resources=[
        #             f"arn:aws:secretsmanager:{env.region}:{env.account}:secret/{comm_props.product_prefix}-{deploy_env}-*"
        #         ],
        #     )
        # )

        backend_task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameters", "ssm:GetParameter"],
                effect=iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:ssm:{env.region}:{env.account}:parameter/{comm_props.product_prefix}-{deploy_env}-*"
                ],
            )
        )
        # TODO: refine the ECS Exec permissions
        backend_task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ssmmessages:CreateControlChannel",
                    "ssmmessages:CreateDataChannel",
                    "ssmmessages:OpenControlChannel",
                    "ssmmessages:OpenDataChannel",
                ],
                effect=iam.Effect.ALLOW,
                resources=["*"],
            )
        )

        backend_task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ses:SendEmail",
                ],
                effect=iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:ses:{env.region}:{env.account}:identity/*"
                ],
            )
        )

        ssm.StringParameter(
            self,
            "ssm-backend-task-role",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-backend-task-role"
            ),
            string_value=backend_task_role.role_arn,
        )

        """ CloudWatch logging for ECS containers """
        backend_server_logger = logs.LogGroup(
            self,
            "backend-log-group",
            log_group_name=id_gen(
                deploy_env, comm_props, "fargate-backend-server"
            ),
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        """ Backend ECS task definition and containers"""
        backend_task_def = ecs.FargateTaskDefinition(
            self,
            "backend-task-def",
            memory_limit_mib=env_props.backend_task_def.task_memory_limit_mib,
            cpu=env_props.backend_task_def.task_cpu,
            task_role=backend_task_role,
        )

        """ Containers """
        # We have 4 containers:
        # - fastapi
        # - redis
        # - 2 rq workers, one for realtime and one for batch
        for container_def in env_props.backend_task_def.container_def_l:
            # N.B. only redis uses redis docker image, for the rest use backend images
            # TODO: find a way to implement this more elegent instead of if/else
            if container_def.name == "redis":
                image = ecs.ContainerImage.from_ecr_repository(redis_repo)
            else:
                image = ecs.ContainerImage.from_ecr_repository(backend_repo)

            container = backend_task_def.add_container(
                container_def.name,
                image=image,
                essential=container_def.essential,
                memory_reservation_mib=container_def.memory_reservation_mib,
                memory_limit_mib=container_def.memory_limit_mib,
                cpu=container_def.cpu,
                command=container_def.command,
                environment={},
                logging=ecs.LogDriver.aws_logs(
                    stream_prefix=container_def.name,
                    log_group=backend_server_logger,
                ),
            )

            if container_def.ulimits is not None:
                container.add_ulimits(
                    ecs.Ulimit(
                        hard_limit=container_def.ulimits["hard_limit"],
                        soft_limit=container_def.ulimits["soft_limit"],
                        name=ecs.UlimitName(container_def.ulimits["name"]),
                    )
                )

            if container_def.port:
                container.add_port_mappings(
                    ecs.PortMapping(
                        container_port=container_def.port,
                        host_port=container_def.expose_port,
                        protocol=container_def.protocol,
                    )
                )

        """ Fargate Service """
        backend_service = ecs.FargateService(
            self,
            "fargate-backend-service",
            service_name=id_gen(
                deploy_env, comm_props, "fargate-service-backend"
            ),
            security_group=fargate_sg,
            cluster=cluster,
            task_definition=backend_task_def,
            vpc_subnets=ec2.SubnetSelection(subnet_group_name="Private"),
            desired_count=1,
            max_healthy_percent=100,
            min_healthy_percent=0,
        )

        """ Frontend ECS task definition """
        frontend_task_def = ecs.FargateTaskDefinition(
            self,
            "frontend-task-def",
            memory_limit_mib=env_props.frontend_task_def.task_memory_limit_mib,
            cpu=env_props.frontend_task_def.task_cpu,
        )

        frontend_server_logger = logs.LogGroup(
            self,
            "frontend-log-group",
            log_group_name=id_gen(
                deploy_env, comm_props, "fargate-frontend-server"
            ),
            retention=logs.RetentionDays.ONE_WEEK,  # TODO: change the retention days in future
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        """ Add frontend container """
        # we only have 1 frontend container
        for container_def in env_props.frontend_task_def.container_def_l:
            container = frontend_task_def.add_container(
                container_def.name,
                image=ecs.ContainerImage.from_ecr_repository(frontend_repo),
                memory_reservation_mib=container_def.memory_reservation_mib,
                memory_limit_mib=container_def.memory_limit_mib,
                cpu=container_def.cpu,
                command=container_def.command,
                environment={},
                logging=ecs.LogDriver.aws_logs(
                    stream_prefix=container_def.name,
                    log_group=frontend_server_logger,
                ),
            )

            container.add_port_mappings(
                ecs.PortMapping(
                    container_port=container_def.port,
                    host_port=container_def.expose_port,
                    protocol=container_def.protocol,
                )
            )

        frontend_service = ecs.FargateService(
            self,
            "fargate-frontend-service",
            service_name=id_gen(
                deploy_env, comm_props, "fargate-service-frontend"
            ),
            security_group=fargate_sg,
            cluster=cluster,  # type: ignore
            task_definition=frontend_task_def,
            vpc_subnets=ec2.SubnetSelection(subnet_group_name="Private"),
            desired_count=1,
            max_healthy_percent=100,
            min_healthy_percent=0,
        )

        """ Doc ECS task definition """
        doc_task_def = ecs.FargateTaskDefinition(
            self,
            "doc-task-def",
            memory_limit_mib=env_props.doc_task_def.task_memory_limit_mib,
            cpu=env_props.doc_task_def.task_cpu,
        )

        doc_server_logger = logs.LogGroup(
            self,
            "doc-log-group",
            log_group_name=id_gen(deploy_env, comm_props, "fargate-doc-server"),
            retention=logs.RetentionDays.THREE_DAYS,  # TODO: change the retention days in future
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        """ Add doc container """
        # we only have 1 doc container
        for container_def in env_props.doc_task_def.container_def_l:
            container = doc_task_def.add_container(
                container_def.name,
                image=ecs.ContainerImage.from_ecr_repository(doc_repo),
                memory_reservation_mib=container_def.memory_reservation_mib,
                memory_limit_mib=container_def.memory_limit_mib,
                cpu=container_def.cpu,
                command=container_def.command,
                environment={},
                logging=ecs.LogDriver.aws_logs(
                    stream_prefix=container_def.name,
                    log_group=doc_server_logger,
                ),
            )

            container.add_port_mappings(
                ecs.PortMapping(
                    container_port=container_def.port,
                    host_port=container_def.expose_port,
                    protocol=container_def.protocol,
                )
            )

        doc_service = ecs.FargateService(
            self,
            "fargate-doc-service",
            service_name=id_gen(deploy_env, comm_props, "fargate-service-doc"),
            security_group=fargate_sg,
            cluster=cluster,  # type: ignore
            task_definition=doc_task_def,
            vpc_subnets=ec2.SubnetSelection(subnet_group_name="Private"),
            desired_count=1,
            max_healthy_percent=100,
            min_healthy_percent=0,
        )

        """ Parameter stores """
        ssm.StringParameter(
            self,
            "ssm-fargate-cluster-name",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-fargate-cluster-name"
            ),  # hardcode the name because Github action will use it
            string_value=cluster.cluster_name,
        )

        """ HTTPS Backend LB listener and target """
        # Here, we setup listener certificate and protocol
        listener_backend_https = lb.add_listener(
            "listener-backend-https",
            port=env_props.backend_task_def.port,
            open=False,
            certificates=[
                elbv2.ListenerCertificate.from_certificate_manager(cert_manager)
            ],
            protocol=elbv2.ApplicationProtocol.HTTPS,
        )

        # N.B. in target group, we still use http port
        listener_backend_https.add_targets(
            "listener-target-backend-https",
            port=env_props.backend_task_def.port,
            targets=[backend_service],
            health_check=elbv2.HealthCheck(
                interval=core.Duration.seconds(60),
                path="/docs",
                timeout=core.Duration.seconds(5),
            ),
        )

        """ Frontent LB listener and target """
        # We use 443 port as the https port
        listener_frontend = lb.add_listener(
            "listener-frontend",
            port=443,
            open=False,
            certificates=[
                elbv2.ListenerCertificate.from_certificate_manager(cert_manager)
            ],
            protocol=elbv2.ApplicationProtocol.HTTPS,
        )

        listener_frontend.add_targets(
            "listener-target-frontend",
            port=env_props.frontend_task_def.port,
            targets=[frontend_service],
            health_check=elbv2.HealthCheck(
                interval=core.Duration.seconds(60),
                path="/",
                timeout=core.Duration.seconds(5),
            ),
        )

        """ redirect http 80 request to https """
        lb.add_listener(
            "listener-redirect-http-to-https",
            port=80,
            open=False,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_action=elbv2.ListenerAction(
                action_json=elbv2.CfnListener.ActionProperty(
                    type="redirect",
                    order=1,
                    redirect_config=elbv2.CfnListener.RedirectConfigProperty(
                        protocol="HTTPS",
                        port="443",
                        host="#{host}",
                        path="/#{path}",
                        query="#{query}",
                        status_code="HTTP_301",
                    ),
                )
            ),
        )
        """ HTTPS Doc LB listener and target """
        listener_doc_https = lb.add_listener(
            "listener-doc-https",
            port=env_props.doc_task_def.port,
            open=False,
            certificates=[
                elbv2.ListenerCertificate.from_certificate_manager(cert_manager)
            ],
            protocol=elbv2.ApplicationProtocol.HTTPS,
        )

        # N.B. in target group, we still use http port
        listener_doc_https.add_targets(
            "listener-target-doc-https",
            port=env_props.doc_task_def.port,
            targets=[doc_service],
            health_check=elbv2.HealthCheck(
                interval=core.Duration.seconds(60),
                path="/",
                timeout=core.Duration.seconds(5),
            ),
            protocol=elbv2.ApplicationProtocol.HTTP,
        )
