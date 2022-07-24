import aws_cdk.aws_route53 as route53
import aws_cdk.aws_route53_targets as alias
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from aws_cdk import core

from helpers.prop_loader import CommonProperties, EnvDepProperties
from helpers.utils import id_gen


class LoadBalancerStack(core.Stack):
    def __init__(
        self,
        app: core.App,
        stack_id: str,
        env: core.Environment,
        deploy_env: str,
        comm_props: CommonProperties,
        env_props: EnvDepProperties,
        vpc: ec2.Vpc,
        log_s3_bucket: s3.Bucket,
        hosted_zone: route53.HostedZone,
        elb_sg: ec2.SecurityGroup,
    ) -> None:
        super().__init__(app, stack_id, env=env)

        lb = elbv2.ApplicationLoadBalancer(
            self,
            "lb",
            vpc=vpc,  # type: ignore
            internet_facing=True,
            security_group=elb_sg,
        )

        # Load balancer log: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-access-logs.html
        lb.log_access_logs(log_s3_bucket)

        ssm.StringParameter(
            self,
            "ssm-lb-dns-name",
            parameter_name=id_gen(
                deploy_env, comm_props, "ssm-lb-dns-name"
            ),  # hardcode the name because Github action will use it
            string_value=lb.load_balancer_dns_name,
        )

        self.lb = lb

        # add load balancer DNS as A record
        route53.ARecord(
            self,
            "alias-record-domain-name",
            zone=hosted_zone,
            target=route53.RecordTarget.from_alias(
                alias.LoadBalancerTarget(lb)
            ),
        )
        route53.ARecord(
            self,
            "alias-record-domain-name-www",
            zone=hosted_zone,
            record_name=f"www.{hosted_zone.zone_name}",
            target=route53.RecordTarget.from_alias(
                alias.LoadBalancerTarget(lb)
            ),
        )
