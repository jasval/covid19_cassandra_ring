#!/bin/bash

echo "Creating the volume..."

kubectl apply -f ./cassandra/cassandra-service.yaml
kubectl apply -f ./cassandra/cassandra-statefulset.yaml
kubectl apply -f ./cassandra/cassandra-nodeport.yaml

echo "Cassandra Cluster has began building..."
sleep 5
echo "Wait a few minutes while resources are allocated and all nodes are up and running..."
