# This script uninstall L2 components, including
# - prometheus
# - Redis
# - fluent-bit
PRODUCT_PREFIX=uniframe
REGION=eu-west-1
NAMESPACE=nm

if [ $# -eq 0 ]; then
    echo "You must at least input -e or --deploy_env prod|dev"
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

# uninstall redis
helm uninstall redis -n ${NAMESPACE}

# uninstall external DNS
helm uninstall external-dns

# uninstall aws load balancer controller
helm uninstall aws-load-balancer-controller -n ${NAMESPACE}\

# uninstall prometheus
helm uninstall prometheus -n default

# uninstall aws-plugins
helm uninstall aws-plugins

# uninstall fluent-bit
# helm uninstall aws-for-fluent-bit --namespace kube-system

kubectl delete namespace nm
