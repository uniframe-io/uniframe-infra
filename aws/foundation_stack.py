import aws_cdk.aws_certificatemanager as acm
import aws_cdk.aws_route53 as route53
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import aws_ssm as ssm
from aws_cdk import core

from helpers.prop_loader import CommonProperties, EnvDepProperties
from helpers.utils import id_gen


class FoundationStack(core.Stack):
    def __init__(
        self,
        app: core.App,
        id: str,
        env: core.Environment,
        deploy_env: str,
        comm_props: CommonProperties,
        env_props: EnvDepProperties,
    ) -> None:
        """
        FoundationStack init these resources:
        - CD deployment related
            - CD service account: Github action use it to connect AWS for CI/CD purpose
            - cd_service_role: role binded with cd service account
            - nm_iam_service_account_group: user group with CD permission
        - ECR repository
            - backend_(local): backend application
            - frontend_(local): frontend application
            - doc_(local): documentation application
            - pg_local: postgres image for local deployment
            - redis: redis repository, to avoid docker pull error from dockerhub
        - ECR read only role: a role can only read ECR local repository for local deployment
        - VPC: the vpc
        - bastion instance for DB connection
        - certication manager: certificates connect with route53
        - Elastic load balancer security group: security group for ELB, used by ECS and EKS
        """

        super().__init__(app, id, env=env)

        """ Service account for external application which needs AWS resources """
        cd_service_role = iam.Role(
            self,
            "iam-cd-service-role",
            assumed_by=iam.ArnPrincipal(comm_props.cd_user_arn),
            external_ids=["github.com"],
            role_name=id_gen(deploy_env, comm_props, "cd-service-role"),
            description="This role is used by CD application to test/build/deploy code",
            max_session_duration=core.Duration.minutes(60),
        )

        cd_service_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:GetAuthorizationToken",
                ],
                effect=iam.Effect.ALLOW,
                resources=["*"],
            )
        )
        cd_service_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:CreateRepository",
                    "ecr:ReplicateImage",
                    "ecr:GetAuthorizationToken",
                    "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:PutImage",
                ],
                effect=iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:ecr:{env.region}:{env.account}:repository/{comm_props.product_prefix}-{deploy_env}-*"
                ],
            )
        )
        cd_service_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecs:UpdateService",
                ],
                effect=iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:ecs:{env.region}:{env.account}:service/{comm_props.product_prefix}-{deploy_env}-*"
                ],
            )
        )
        cd_service_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ssm:GetParameters",
                ],
                effect=iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:ssm:{env.region}:{env.account}:parameter/{comm_props.product_prefix}-{deploy_env}-*"
                ],
            )
        )

        # need to aws eks update-context
        cd_service_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "eks:DescribeCluster",
                ],
                effect=iam.Effect.ALLOW,
                resources=["*"],
            )
        )

        cd_service_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "secretsmanager:GetSecretValue",
                ],
                effect=iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:secretsmanager:{env.region}:{env.account}:secret:{comm_props.product_prefix}-{deploy_env}-*"
                ],
            )
        )

        ssm.StringParameter(
            self,
            "ssm-iam-cd-role-arn",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-iam-cd-role-arn"
            ),  # hardcode the name because Github action will use it
            string_value=cd_service_role.role_arn,
        )

        """ Create ECR repository and parameter store """
        backend_repository = ecr.Repository(
            self,
            "ecr-backend-repo",
            repository_name=id_gen(deploy_env, comm_props, "backend"),
        )
        backend_repo_ssm_name = id_gen(
            deploy_env, comm_props, "ssm-backend-repo-name"
        )
        ssm.StringParameter(
            self,
            "ssm-backend-repo-name",
            parameter_name=backend_repo_ssm_name,  # hardcode the name because Github action will use it
            string_value=backend_repository.repository_name,
        )

        # backend local repository dedicated for local deployment
        backend_local_repository = ecr.Repository(
            self,
            "ecr-backend-local-repo",
            repository_name=id_gen(deploy_env, comm_props, "backend-local"),
        )
        backend_local_repo_ssm_name = id_gen(
            deploy_env, comm_props, "ssm-backend-local-repo-name"
        )
        ssm.StringParameter(
            self,
            "ssm-backend-local-repo-name",
            parameter_name=backend_local_repo_ssm_name,  # hardcode the name because Github action will use it
            string_value=backend_local_repository.repository_name,
        )

        # Postgres repostiory is only used for store PG image for local deployment
        # reason: we override PG image, and add some sql scripts to the image
        pg_local_repository = ecr.Repository(
            self,
            "ecr-pg-local",
            repository_name=id_gen(deploy_env, comm_props, "pg-local"),
        )
        pg_repo_local_ssm_name = id_gen(
            deploy_env, comm_props, "ssm-pg-local-repo-name"
        )
        ssm.StringParameter(
            self,
            "ssm-pg-local-repo-name",
            parameter_name=pg_repo_local_ssm_name,  # hardcode the name because Github action will use it
            string_value=pg_local_repository.repository_name,
        )

        frontend_repository = ecr.Repository(
            self,
            "ecr-frontend-repo",
            repository_name=id_gen(deploy_env, comm_props, "frontend"),
        )
        frontend_repo_ssm_name = id_gen(
            deploy_env, comm_props, "ssm-frontend-repo-name"
        )
        ssm.StringParameter(
            self,
            "ssm-frontend-repo-name",
            parameter_name=frontend_repo_ssm_name,  # hardcode the name because Github action will use it
            string_value=frontend_repository.repository_name,
        )

        # frontend local repository dedicated for local deployment
        frontend_local_repository = ecr.Repository(
            self,
            "ecr-frontend-local-repo",
            repository_name=id_gen(deploy_env, comm_props, "frontend-local"),
        )
        frontend_local_repo_ssm_name = id_gen(
            deploy_env, comm_props, "ssm-frontend-local-repo-name"
        )
        ssm.StringParameter(
            self,
            "ssm-frontend-local-repo-name",
            parameter_name=frontend_local_repo_ssm_name,  # hardcode the name because Github action will use it
            string_value=frontend_local_repository.repository_name,
        )

        redis_repository = ecr.Repository.from_repository_name(
            self, "ecr-redis", "redis"
        )

        doc_repository = ecr.Repository(
            self,
            "ecr-doc-repo",
            repository_name=id_gen(deploy_env, comm_props, "doc"),
        )
        doc_repo_ssm_name = id_gen(deploy_env, comm_props, "ssm-doc-repo-name")
        ssm.StringParameter(
            self,
            "ssm-doc-repo-name",
            parameter_name=doc_repo_ssm_name,  # hardcode the name because Github action will use it
            string_value=doc_repository.repository_name,
        )

        # doc local repository dedicated for local deployment
        doc_local_repository = ecr.Repository(
            self,
            "ecr-doc-local-repo",
            repository_name=id_gen(deploy_env, comm_props, "doc-local"),
        )
        doc_local_repo_ssm_name = id_gen(
            deploy_env, comm_props, "ssm-doc-local-repo-name"
        )
        ssm.StringParameter(
            self,
            "ssm-doc-local-repo-name",
            parameter_name=doc_local_repo_ssm_name,  # hardcode the name because Github action will use it
            string_value=doc_local_repository.repository_name,
        )

        """ Create a ECR repositories read-only role"""
        ecr_readonly_role = iam.Role(
            self,
            "iam-ecr-readonly-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            role_name=id_gen(deploy_env, comm_props, "ecr-readonly"),
            description="This role is used by local deploy enable user to pull images from ECR repository",
            max_session_duration=core.Duration.minutes(
                comm_props.ecr_assume_role_expiration_min
            ),
        )

        ecr_readonly_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:GetRepositoryPolicy",
                    "ecr:DescribeRepositories",
                    "ecr:ListImages",
                    "ecr:DescribeImages",
                    "ecr:BatchGetImage",
                    "ecr:GetLifecyclePolicy",
                    "ecr:GetLifecyclePolicyPreview",
                    "ecr:ListTagsForResource",
                    "ecr:DescribeImageScanFindings",
                ],
                effect=iam.Effect.ALLOW,
                resources=[
                    backend_local_repository.repository_arn,
                    frontend_local_repository.repository_arn,
                    doc_local_repository.repository_arn,
                    pg_local_repository.repository_arn,
                ],
            )
        )

        ecr_readonly_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:GetAuthorizationToken",
                ],
                effect=iam.Effect.ALLOW,
                resources=[
                    "*",
                ],
            )
        )

        ecr_readonly_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ssm:GetParameters",
                ],
                effect=iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:ssm:{env.region}:{env.account}:parameter/{doc_local_repo_ssm_name}",
                    f"arn:aws:ssm:{env.region}:{env.account}:parameter/{backend_local_repo_ssm_name}",
                    f"arn:aws:ssm:{env.region}:{env.account}:parameter/{frontend_local_repo_ssm_name}",
                    f"arn:aws:ssm:{env.region}:{env.account}:parameter/{pg_repo_local_ssm_name}",
                ],
            )
        )

        self.ecr_readonly_role = ecr_readonly_role

        ssm.StringParameter(
            self,
            "ssm-ecr-readonly-role",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-ecr-readonly-role"
            ),
            string_value=ecr_readonly_role.role_arn,
        )

        """ Create a VPC and ssm parameter store """
        vpc = ec2.Vpc(
            self,
            "vpc",
            max_azs=2,
            cidr=comm_props.vpc_default_cidr,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PUBLIC,
                    name="Public",
                    cidr_mask=comm_props.subnet_cidr_mask,
                ),
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PRIVATE,
                    name="Private",
                    cidr_mask=comm_props.subnet_cidr_mask,
                ),
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.ISOLATED,
                    name="DB",
                    cidr_mask=comm_props.subnet_cidr_mask,
                ),
            ],
            nat_gateways=1,
        )

        self.vpc = vpc
        self.backend_repo = backend_repository
        self.frontend_repo = frontend_repository
        self.doc_repo = doc_repository
        self.redis_repo = redis_repository

        """ System Session Manager role for EC2 instance """
        ssm_bastion_role = iam.Role(
            self,
            "iam-ssm-bastion-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            role_name=id_gen(deploy_env, comm_props, "ssm-bastion-role"),
            description="This role is for EC2 instance profile which will serving the SSM",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )

        ssm_bastion_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudwatch:PutMetricData",
                    "ec2:DescribeVolumes",
                    "ec2:DescribeTags",
                ],
                effect=iam.Effect.ALLOW,
                resources=["*"],
            )
        )

        """ Bastion """
        bastion_sg = ec2.SecurityGroup(
            self,
            "bastion-sg",
            vpc=self.vpc,
            allow_all_outbound=True,
            description="SG for bastion instance",
        )
        bastion_instance = ec2.Instance(
            self,
            "bastion-ssm",
            vpc=self.vpc,
            instance_name="bastion",
            instance_type=ec2.InstanceType("t3a.nano"),
            # ec2-instance-connect is requiring Amazon Linux 2 2.0.20190618
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2
            ),
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE
            ),
            security_group=bastion_sg,
            role=ssm_bastion_role,
        )
        self.ssm_bastion_instance = bastion_instance
        ssm.StringParameter(
            self,
            "ssm-bastion-instance-id",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-bastion-instance-id"
            ),
            string_value=bastion_instance.instance_id,
        )

        """ Certificate """
        # load existing route53 hosted zone
        # TODO: create the HostedZone by cdk directly?
        # CDK has a bug in from_hosted_zone_id https://github.com/aws/aws-cdk/issues/8406
        # use from_hosted_zone_attributes

        ssm.StringParameter(
            self,
            "ssm-eks-domain-name",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-eks-domain-name"
            ),
            string_value=env_props.eks_host_zone.domain_name,
        )

        eks_hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self,
            "eks_hosted_zone",
            hosted_zone_id=env_props.eks_host_zone.id,
            zone_name=env_props.eks_host_zone.domain_name,
        )

        ssm.StringParameter(
            self,
            "ssm-eks-hostzone-id",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-eks-hostzone-id"
            ),
            string_value=eks_hosted_zone.hosted_zone_id,
        )

        eks_acm_subdomains = acm.Certificate(
            self,
            "certificate-manager-subdomains",
            domain_name=f"*.{eks_hosted_zone.zone_name}",
            validation=acm.CertificateValidation.from_dns(eks_hosted_zone),
        )

        eks_acm_domain = acm.Certificate(
            self,
            "certificate-manager-domain",
            domain_name=f"{eks_hosted_zone.zone_name}",
            validation=acm.CertificateValidation.from_dns(eks_hosted_zone),
        )

        ssm.StringParameter(
            self,
            "ssm-eks-certificate-manager-arn",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-eks-certificate-manager-arn"
            ),
            string_value=f"{eks_acm_domain.certificate_arn},{eks_acm_subdomains.certificate_arn}",
        )

        """ API Token Secret """
        sm.Secret(
            self,
            "api-token-secret",
            generate_secret_string=sm.SecretStringGenerator(
                password_length=32,
                exclude_punctuation=True,
            ),
            secret_name=id_gen(deploy_env, comm_props, "api-token-secret"),
        )

        """ Redis Secret """
        sm.Secret(
            self,
            "redis-secret",
            generate_secret_string=sm.SecretStringGenerator(
                password_length=32,
                exclude_punctuation=True,
            ),
            secret_name=id_gen(deploy_env, comm_props, "redis-secret"),
        )

        """ Grafana Secret """
        sm.Secret(
            self,
            "grafana-admin-secret",
            generate_secret_string=sm.SecretStringGenerator(
                password_length=16,
                exclude_punctuation=True,
            ),
            secret_name=id_gen(deploy_env, comm_props, "grafana-admin-secret"),
        )

        # create load balancer security group
        """ Create security group """
        elb_sg = ec2.SecurityGroup(
            self,
            "elb-sg",
            vpc=vpc,  # type: ignore
            allow_all_outbound=True,
            description="SG for Elastic Load balancer",
        )

        ssm.StringParameter(
            self,
            "ssm-elb-sg-id",
            parameter_name=id_gen(deploy_env, comm_props, "ssm-elb-sg-id"),
            string_value=elb_sg.security_group_id,
        )

        elb_sg.add_ingress_rule(
            ec2.Peer.ipv4(comm_props.vpc_default_cidr),
            ec2.Port.all_tcp(),
            description="allow all internal traffic",
        )

        for whitelist_ip in env_props.whitelist_ips:
            elb_sg.add_ingress_rule(
                ec2.Peer.ipv4(whitelist_ip.ip),
                ec2.Port.tcp(443),  # 443 for load balancer listener
                description=f"allow 443 for {whitelist_ip.entity}",
            )
            
            if whitelist_ip.enable_80:
                elb_sg.add_ingress_rule(
                    ec2.Peer.ipv4(whitelist_ip.ip),
                    ec2.Port.tcp(80),  # 80 for load balancer listener
                    description=f"allow 80 for {whitelist_ip.entity}",
                )
        self.elb_sg = elb_sg


        """ demo account info+demo@uniframe.io limitation switch """
        ssm.StringParameter(
            self,
            "ssm-demo-account-limitation",
            parameter_name=id_gen(deploy_env, comm_props, "ssm-demo-account-limitation"),
            string_value="yes",  # by default (after each deployment), set the limitation
            description="'no' means demo account can do anything. Please change it to 'yes' after creating the task"
        )

        """ RapidAPI endpoint task id parameter """
        ssm.StringParameter(
            self,
            "rapidapi-task-id",
            parameter_name=id_gen(deploy_env, comm_props, "rapidapi-sanction-task-id"),
            string_value="0",  # by default set to 0
            description="Sanction list searching task id in the demo account"
        )
