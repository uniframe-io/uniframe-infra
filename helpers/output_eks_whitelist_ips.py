# This is an auxiliary program to output the whitelist ip for EKS endpoint access
# Reason:
# - CDK has bug to support, so we use AWS CLI in helm-install-l2.sh
# - bash seems not have a good yaml parser

import sys
from helpers.prop_loader import EnvDepProperties

if __name__ == '__main__':
    if len(sys.argv) <= 1:
        exit("Must input deployment environment")
    
    deploy_env = sys.argv[1]
    if deploy_env not in ['dev', 'prod']:
        exit("Deployment environment must be dev or prod")
    
    env_props = EnvDepProperties.load(f"./conf/env_props.{deploy_env}.yaml")

    ip_list = [e.ip for e in env_props.eks_cluster_cfg.whitelist_ips]
    print(",".join(ip_list))
