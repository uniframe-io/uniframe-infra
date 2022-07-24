PRODUCT_PREFIX=uniframe
NAME_SPACE=nm
APP=frontend

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
    -n | --namespace)
       shift
       NAME_SPACE=$1
      ;;
    -a | --app)
       shift
       APP=$1
      ;;

 esac
 shift
done

EKS_NAME=$(aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-eks-cluster-name --query "Parameters[0].Value" | tr -d '"')
aws eks update-kubeconfig --name ${EKS_NAME}

POD_NAME=`kubectl get pods --no-headers -o custom-columns=":metadata.name" -n ${NAME_SPACE} | grep ${APP} | head -n 1`
kubectl exec -it  -n ${NAME_SPACE} ${POD_NAME}  -- /bin/sh
