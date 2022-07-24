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

DNS_INGRESS_SECURITY_GROUP=`aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-elb-sg-id --query "Parameters[0].Value" | tr -d '"'`
DNS_INGRESS_ACM_ARN=`aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-eks-certificate-manager-arn --query "Parameters[0].Value" | tr -d '"'`
DNS_HOSTNAME=`aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-eks-domain-name --query "Parameters[0].Value" | tr -d '"'`


echo DNS_INGRESS_SECURITY_GROUP is ${DNS_INGRESS_SECURITY_GROUP}
# extra \ for escape comma
echo DNS_INGRESS_ACM_ARN is "${DNS_INGRESS_ACM_ARN/,/\,}"
echo DNS_HOSTNAME is ${DNS_HOSTNAME}

# setup kubectl context
EKS_NAME=$(aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-eks-cluster-name --query "Parameters[0].Value" | tr -d '"')
aws eks update-kubeconfig --name ${EKS_NAME}

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text) 


# helm install --dry-run --debug ${PRODUCT_PREFIX}-${DEPLOY_ENV} k8s/uniframe  --namespace ${NAMESPACE}  \
helm upgrade --install  ${PRODUCT_PREFIX}-${DEPLOY_ENV} k8s/uniframe  --namespace ${NAMESPACE}  \
  --create-namespace\
  --set global.ingress.sg=${DNS_INGRESS_SECURITY_GROUP} \
  --set global.ingress.acm_arn="${DNS_INGRESS_ACM_ARN/,/\,}" \
  --set global.ingress.hostname=${DNS_HOSTNAME}\
  --set global.aws_account=${ACCOUNT_ID}\
  --set global.namespace=${NAMESPACE}\
  --set global.aws_default_region=${AWS_REGION}\
  --set global.app_name=${PRODUCT_PREFIX}\
  --set global.deploy_dev=${DEPLOY_ENV}
