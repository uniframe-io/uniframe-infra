# This script installs L2 components, including
# - prometheus
# - Redis
# - fluent-bit
PRODUCT_PREFIX=uniframe
AWS_REGION=eu-west-1
NAMESPACE=nm

if [ $# -eq 0 ]; then
    echo "You must at least input --deploy_env=prod|dev"
    exit 1
fi

while [ "$1" != "" ]; do
 case $1 in
    -p | --product-prefix)
       shift
       PRODUCT_PREFIX=$1
      ;;
    -e | --deploy-env)
       shift
       DEPLOY_ENV=$1
      ;;

 esac
 shift
done

# setup kubectl context
EKS_NAME=$(aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-eks-cluster-name --query "Parameters[0].Value" | tr -d '"')
aws eks update-kubeconfig --name ${EKS_NAME}

GRAFANA_PASSWORD=$(aws secretsmanager get-secret-value --secret-id ${PRODUCT_PREFIX}-${DEPLOY_ENV}-grafana-admin-secret --region ${AWS_REGION} --query SecretString --output text)
# install prometheus
# TODO: deploy prometheus into monitoring namespace
echo "[prometheus-suite] starting to install"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack -f k8s/l2-configuration/prometheus_values.yaml \
    --set prometheus.prometheusSpec.nodeSelector.node-pool=main\
    --set prometheus.prometheusSpec.additionalScrapeConfigs[0].relabel_configs[1].replacement="${PRODUCT_PREFIX}-${DEPLOY_ENV}-backend-service.nm.svc:8000"\
    --set grafana.adminPassword="${GRAFANA_PASSWORD}"

# # install fluent-bit
# helm repo add eks https://aws.github.io/eks-charts
# helm upgrade --install aws-for-fluent-bit --namespace logging eks/aws-for-fluent-bit\
#     --create-namespace\
#     --set cloudWatch.region=${AWS_REGION}\
#     --set firehose.enabled=false\
#     --set kinesis.enabled=false\
#     --set elasticsearch.enabled=false\
#     --set nodeSelector.node-pool=main


# install aws load balancer controller
# If not using IAM Roles for service account
echo "[aws-load-balancer-controller] starting to install"
helm repo add eks https://aws.github.io/eks-charts
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller -n ${NAMESPACE}\
    --create-namespace\
    --version 1.2.0\
    --set clusterName=${EKS_NAME}\
    --set enableShield=false\
    --set enableWaf=false\
    --set enableWafv2=false\
    --set replicaCount=1\
    --set nodeSelector.node-pool=main


# install external DNS
# Get hostzone id and hostzone name
echo "[external-dns] starting to install"
HOSTZONE_ID=$(aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-eks-hostzone-id --query "Parameters[*].Value | [0]" | tr -d '"')
DOMAIN_NAME=$(aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-eks-domain-name --query "Parameters[*].Value | [0]" | tr -d '"')
echo $HOSTZONE_ID
echo $DOMAIN_NAME
helm repo add bitnami https://charts.bitnami.com/bitnami
helm upgrade --install external-dns bitnami/external-dns\
    --set provider=aws\
    --set aws.zoneType=public\
    --set aws.region="${AWS_REGION}"\
    --set txtOwnerId="${HOSTZONE_ID}"\
    --set domainFilters[0]="${DOMAIN_NAME}"\
    --set domainFilters[1]="api.${DOMAIN_NAME}"\
    --set domainFilters[2]="www.${DOMAIN_NAME}"\
    --set domainFilters[3]="doc.${DOMAIN_NAME}"\
    --set policy=sync\
    --set nodeSelector.node-pool=main


# install redis
REDIS_PASSWORD=$(aws secretsmanager get-secret-value --secret-id ${PRODUCT_PREFIX}-${DEPLOY_ENV}-redis-secret --region ${AWS_REGION} --query SecretString --output text)

if [ -z "${REDIS_PASSWORD}" ]; then
    echo "Init error: K8S_REDIS_PASSWORD is empty"
    exit 1
fi

echo "[redis] starting to install"
helm repo add bitnami https://charts.bitnami.com/bitnami
helm upgrade --install redis bitnami/redis -n ${NAMESPACE}\
    --create-namespace\
    --set replica.replicaCount=1\
    --set auth.password=${REDIS_PASSWORD}\
    --set master.nodeSelector.node-pool=main\
    --set replica.nodeSelector.node-pool=main


# -----------------------
# Disable the endpoint access for now. Unfortunately, the IP list of Github action is very long
# https://api.github.com/meta
# EKS only support 40 ips

# # setup endpoint access permission due to CDK bug
# # https://github.com/aws/aws-cdk/issues/16661
# # https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html
# WHITELIST_IPS=$(python helpers/output_eks_whitelist_ips.py ${DEPLOY_ENV})
# AWS_PAGER="" aws eks update-cluster-config \
#     --region ${AWS_REGION} \
#     --name ${EKS_NAME} \
#     --resources-vpc-config endpointPublicAccess=true,endpointPrivateAccess=true,publicAccessCidrs=${WHITELIST_IPS}

# # Waits 2 minutes until endpoint
# echo "Setup EKS endpoint access endpoint for whitelist IPs"
# echo $WHITELIST_IPS
# echo "wait for 2 minutes"
# sleep 2m

# install aws plugins
echo "[aws-plugins] starting to install"
EKS_CLUSTER_AUTO_SCALER_ROLE_ARN=`aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-eks-cluster-auto-scaler-role-arn --query "Parameters[0].Value" | tr -d '"'`
EKS_CLUSTER_NAME=`aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-eks-cluster-name --query "Parameters[0].Value" | tr -d '"'`

echo EKS_CLUSTER_NAME is ${EKS_CLUSTER_NAME}
echo EKS_CLUSTER_AUTO_SCALER_ROLE_ARN is ${EKS_CLUSTER_AUTO_SCALER_ROLE_ARN}

#helm upgrade --install ${PRODUCT_PREFIX}-${DEPLOY_ENV}-aws-plugins k8s/aws-plugins -f k8s/aws-plugins/values.yaml \
helm upgrade --install aws-plugins k8s/aws-plugins -f k8s/aws-plugins/values.yaml \
  --set global.aws_default_region=${AWS_REGION} \
  --set autoscaler.aws_role_arn=${EKS_CLUSTER_AUTO_SCALER_ROLE_ARN} \
  --set autoscaler.eks_cluster_name=${EKS_CLUSTER_NAME}
