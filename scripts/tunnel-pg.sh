#!/bin/bash

PRODUCT_PREFIX=uniframe
AWS_REGION=eu-west-1
DEPLOY_ENV=dev

while [ "$1" != "" ]; do
  case $1 in
  --instance-id | --i)
    shift
    INSTANCE_ID=$1
    ;;
  --public-key-file | --pub)
    shift
    PUBLIC_KEY=$1
    ;;
  -private-key-file | --pri)
    shift
    PRIVATE_KEY=$1
    ;;
  --local-ssh-port)
    shift
    LOCAL_SSH_PORT=$1
    ;;
  --local-pg-port)
    shift
    LOCAL_PG_PORT=$1
    ;;
  --pg-host)
    shift
    PG_HOST=$1
    ;;
  --pg-port)
    shift
    PG_PORT=$1
    ;;
  -e | --deploy-env)
      shift
      DEPLOY_ENV=$1
    ;;    
  esac
  shift
done


INSTANCE_ID=$(aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-bastion-instance-id --query "Parameters[0].Value" | sed -e 's/^"//' -e 's/"$//')
LOCAL_SSH_PORT=9999
LOCAL_PG_PORT=54321
PG_HOST=$(aws ssm get-parameters --names ${PRODUCT_PREFIX}-${DEPLOY_ENV}-ssm-api-db-dns --query "Parameters[0].Value" | sed -e 's/^"//' -e 's/"$//')
PG_PORT=5432

aws ec2-instance-connect send-ssh-public-key --instance-id ${INSTANCE_ID} --availability-zone eu-west-1a --instance-os-user ec2-user --ssh-public-key file://${PUBLIC_KEY}

aws ssm start-session --target ${INSTANCE_ID} --document-name AWS-StartPortForwardingSession --parameters "portNumber"=["22"],"localPortNumber"=[${LOCAL_SSH_PORT}] & \
sleep 3 && ssh -o StrictHostKeyChecking=no ec2-user@localhost -i ${PRIVATE_KEY}  -p ${LOCAL_SSH_PORT} -N -L ${LOCAL_PG_PORT}:${PG_HOST}:${PG_PORT} & \
wait
