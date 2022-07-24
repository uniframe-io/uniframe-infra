# This script uninstall UniFrame

PRODUCT_PREFIX=uniframe
REGION=eu-west-1
NAMESPACE=nm

if [ $# -eq 0 ]; then
    echo "You must at least input --deploy_env=prod|dev"
    exit 1
fi

while [ "$1" != "" ]; do
 case $1 in
    -p | --product_prefix)
       shift
       PRODUCT_PREFIX=$1
      ;;
    -e | --deploy_env)
       shift
       DEPLOY_ENV=$1
      ;;
 esac
 shift
done


# setup kubectl context
EKS_NAME=$(aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-eks-cluster-name --query "Parameters[0].Value" | tr -d '"')
aws eks update-kubeconfig --name ${EKS_NAME}

# uninstall uniframe
helm uninstall ${PRODUCT_PREFIX}-${DEPLOY_ENV} --namespace ${NAMESPACE} 
