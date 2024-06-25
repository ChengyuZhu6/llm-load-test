#!/bin/bash

# Prefix of the pods to be killed
pod_prefix=${pod_prefix:-"llama2inferenceserving-predictor-00001-deployment-"}
# Get the list of pods with the specified prefix
pods=$(kubectl get pods | grep $pod_prefix | awk '{print $1}')

# Loop through each pod and kill the python process
for pod in $pods
do
    # Get the PID of the python process inside the pod
    pid=$(kubectl exec -it $pod -- sh -c "ps aux | grep '__main__.py' | grep -v grep | awk '{print \$2}'")

    # Kill the python process
    kubectl exec -it $pod -- sh -c "kill -9 $pid"

    # Delete the pod
    kubectl delete pod $pod
done

echo "All specified pods and python processes have been killed."

