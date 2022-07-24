from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_eks as eks
from aws_cdk import aws_iam as iam
from aws_cdk import aws_rds as rds
from aws_cdk import aws_ssm as ssm
from aws_cdk import core
from aws_cdk.core import CfnJson

from helpers.prop_loader import CommonProperties, EnvDepProperties
from helpers.utils import id_gen
import json


class EksManagedStack(core.Stack):
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
        elb_sg: ec2.SecurityGroup,
    ) -> None:
        super().__init__(app, stack_id, env=env)

        """Create a dedicate role for the cluster"""
        # TODO: refine the permission level
        # TODO: check if we need S3 permission
        eks_cluster_role = iam.Role(
            self,
            "eks-cluster-iam-role",
            assumed_by=iam.ServicePrincipal("eks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchLogsFullAccess"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKSClusterPolicy"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "SecretsManagerReadWrite"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2FullAccess"
                ),
            ],
        )

        """ Create EKS cluster """

        # https://docs.aws.amazon.com/cli/latest/reference/eks/update-cluster-config.html#options
        # This is a bug https://github.com/aws/aws-cdk/issues/16661
        # waiting for CDK team to fix it
        # endpoint_access = eks.EndpointAccess.PUBLIC_AND_PRIVATE.only_from(",".join(env_props.eks_cluster_cfg.whitelist_ips))

        cluster = eks.Cluster(
            self,
            id="eks-cluster",
            vpc=vpc,
            vpc_subnets=[
                ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE)
            ],
            # security_group=eks_sg,   it doesn't work use security group here
            default_capacity=0,
            version=eks.KubernetesVersion.V1_21,
            role=eks_cluster_role,
            core_dns_compute_type=eks.CoreDnsComputeType.EC2,
            endpoint_access=eks.EndpointAccess.PUBLIC_AND_PRIVATE,
        )  # type: ignore

        # Add ELB security group as cluster connection rules
        cluster.connections.allow_from(
            other=elb_sg,
            port_range=ec2.Port.all_tcp(),
            description="enable traffic from AWS Load Balancer",
        )
        cluster.node.add_dependency(api_db)

        ssm.StringParameter(
            self,
            "ssm-eks-cluster-name",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-eks-cluster-name"
            ),  # hardcode the name because Github action will use it
            string_value=cluster.cluster_name,
        )

        """ EC2 node group by EKS """
        # TODO: fine tune all EKS note group policies
        eks_node_group_role = iam.Role(
            self,
            "eks-node-group-iam-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchLogsFullAccess"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2FullAccess"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKSClusterPolicy"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKSWorkerNodePolicy"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2ContainerRegistryReadOnly"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonRoute53FullAccess"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchAgentServerPolicy"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchReadOnlyAccess"
                ),
            ],
        )

        # route 53 policy refine
        # {
        # "Version": "2012-10-17",
        # "Statement": [
        #     {
        #     "Effect": "Allow",
        #     "Action": [
        #         "route53:ChangeResourceRecordSets"
        #     ],
        #     "Resource": [
        #         "arn:aws:route53:::hostedzone/*"
        #     ]
        #     },
        #     {
        #     "Effect": "Allow",
        #     "Action": [
        #         "route53:ListHostedZones",
        #         "route53:ListResourceRecordSets"
        #     ],
        #     "Resource": [
        #         "*"
        #     ]
        #     }
        # ]
        # }

        eks_node_group_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameters", "ssm:GetParameter"],
                effect=iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:ssm:{env.region}:{env.account}:parameter/{comm_props.product_prefix}-{deploy_env}-*"
                ],
            )
        )

        bucket_name = id_gen(deploy_env, comm_props, "data")
        eks_node_group_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:*"],
                effect=iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*",
                ],
            )
        )

        eks_node_group_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "SecretsManagerReadWrite"
            )
        )

        # Somehow, the way below for secretmanager doesn't work
        # eks_node_group_role.add_to_policy(
        #     iam.PolicyStatement(
        #         actions=[
        #             "secretsmanager:ListSecrets",
        #             "secretsmanager:GetSecretValue",
        #             "secretsmanager:GetRandomPassword",
        #             "secretsmanager:DescribeSecret",
        #             "secretsmanager:GetResourcePolicy",
        #         ],
        #         effect=iam.Effect.ALLOW,
        #         resources=[
        #             f"arn:aws:secretsmanager:{env.region}:{env.account}:secret:{comm_props.product_prefix}-{deploy_env}-*",
        #         ],
        #     )
        # )

        eks_node_group_role.add_to_policy(
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

        # TODO: use 2 nodegroup
        # - one for main application and log, monitor, redis, load balancer, etc
        # - one for nm pod
        # https://github.com/awslabs/amazon-eks-ami/blob/master/files/eni-max-pods.txt
        for node_group_conf in env_props.eks_cluster_cfg.node_group:
            cluster.add_nodegroup_capacity(
                f"eks-node-group-{node_group_conf.id_surfix}",
                nodegroup_name=f"eks-node-group-{node_group_conf.id_surfix}",
                instance_types=[
                    ec2.InstanceType(node_group_conf.instance_type)
                ],
                min_size=node_group_conf.min_size,
                max_size=node_group_conf.max_size,
                node_role=eks_node_group_role,
                labels=node_group_conf.label,
                tags=node_group_conf.tags,
            )

            # eks_auto_auto_scaling_group = cluster.add_auto_scaling_group_capacity(
            #     f"auto-scaling-group-{node_group_conf.id_surfix}",
            #     auto_scaling_group_name=f"eks-auto-scaling-group-{node_group_conf.id_surfix}",
            #     instance_type=ec2.InstanceType(node_group_conf.instance_type),
            #     min_capacity=node_group_conf.min_size,
            #     max_capacity=node_group_conf.max_size,
            #     map_role=True,
            #     group_metrics=[GroupMetrics.all()],
            #     bootstrap_options=eks.BootstrapOptions(
            #         kubelet_extra_args=f"--node-labels {node_group_conf.node_label.get('key')}={node_group_conf.node_label.get('value')} eks.amazonaws.com/nodegroup=node-group-{node_group_conf.node_label.get('value')}"
            #     ),
            # )

            # eks_auto_auto_scaling_group = aws_autoscaling.AutoScalingGroup(
            #     self,
            #     f"auto-scaling-group-{node_group_conf.id_surfix}",
            #     auto_scaling_group_name=f"eks-auto-scaling-group-{node_group_conf.id_surfix}",
            #     instance_type=ec2.InstanceType(node_group_conf.instance_type),
            #     machine_image=ec2.MachineImage.from_ssm_parameter("/aws/service/eks/optimized-ami/1.21/amazon-linux-2/recommended/image_id"),
            #     min_capacity=node_group_conf.min_size,
            #     max_capacity=node_group_conf.max_size,
            #     role=eks_node_group_role,
            #     group_metrics=[GroupMetrics.all()],
            #     vpc=vpc,
            # )
            #
            # cluster.connect_auto_scaling_group_capacity(
            #     eks_auto_auto_scaling_group
            # )

        """ temp access for debugging """
        # grant AWS admin role as EKS cluster sys:master
        cluster.aws_auth.add_role_mapping(
            iam.Role.from_role_arn(
                self,
                "org_account_access_role",
                role_arn=f"arn:aws:iam::{env.account}:role/OrganizationAccountAccessRole",
            ),
            groups=["system:masters"],
        )

        # also grant cd role EKS access
        cluster.aws_auth.add_role_mapping(
            iam.Role.from_role_arn(
                self,
                "cd_service_role",
                role_arn=f"arn:aws:iam::{env.account}:role/{id_gen(deploy_env, comm_props, 'cd-service-role')}",
            ),
            groups=["system:masters"],
        )

        # TODO: how to improve it? Now cd runner has the all EKS access!
        # also grant cd role with master EKS access
        cd_runner_role_arn = ssm.StringParameter.value_for_string_parameter(
            self, id_gen(deploy_env, comm_props, "ssm-iam-cd-role-arn")
        )
        cd_runner_eks_role = iam.Role.from_role_arn(
            self, "cd_runner_role_eks", cd_runner_role_arn
        )
        cluster.aws_auth.add_masters_role(cd_runner_eks_role)

        """ future production support role arrangement, disable for dev """
        # production_support_role = iam.Role(
        #     self,
        #     "iam-production-support-role",
        #     assumed_by=iam.AccountPrincipal(env.account),
        #     role_name=id_gen(deploy_env, comm_props, "production-support-role"),
        #     description="This role is used production support to interact with EKS cluster",
        # )
        #
        # cluster.aws_auth.add_role_mapping(
        #     production_support_role,
        #     groups=["system:masters"],
        # )

        eks_open_id_connect_provider_issuer = CfnJson(
            self,
            id="json-id",
            value={
                f"{cluster.open_id_connect_provider.open_id_connect_provider_issuer}:sub": "system:serviceaccount:kube-system:cluster-autoscaler",
                f"{cluster.open_id_connect_provider.open_id_connect_provider_issuer}:aud": "sts.amazonaws.com",
            },
        )

        eks_web_identity_provider = iam.WebIdentityPrincipal(
            identity_provider=cluster.open_id_connect_provider.open_id_connect_provider_arn,
            conditions={"StringEquals": eks_open_id_connect_provider_issuer},
        )

        eks_cluster_auto_scaler_role = iam.Role(
            self,
            "iam-eks-cluster-autoscaler-role",
            assumed_by=eks_web_identity_provider,
            role_name=id_gen(deploy_env, comm_props, "eks-cluster-autoscaler"),
            description="This role is used by EKS cluster node group to auto scale",
        )

        ssm.StringParameter(
            self,
            "ssm-eks-cluster-auto-scaler-role-arn",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-eks-cluster-auto-scaler-role-arn"
            ),
            string_value=eks_cluster_auto_scaler_role.role_arn,
        )

        eks_auto_scaling_policy = iam.Policy(
            self,
            "iam-eks-cluster-autoscaler-policy",
            policy_name=id_gen(
                deploy_env, comm_props, "eks-cluster-autoscaler-policy"
            ),
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "autoscaling:DescribeAutoScalingGroups",
                        "autoscaling:DescribeAutoScalingInstances",
                        "autoscaling:DescribeLaunchConfigurations",
                        "autoscaling:DescribeTags",
                        "autoscaling:SetDesiredCapacity",
                        "autoscaling:TerminateInstanceInAutoScalingGroup",
                        "ec2:DescribeLaunchTemplateVersions",
                    ],
                    effect=iam.Effect.ALLOW,
                    resources=["*"],
                )
            ],
        )

        eks_auto_scaling_policy.attach_to_role(eks_cluster_auto_scaler_role)
