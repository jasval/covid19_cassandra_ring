#Script for initialisation

##Get minikube and necessary libraries

sudo apt-get install minikube


minikube start --memory 5120 --cpus=4

##Track all cassandra statefulset nodes from cassandra-service.yaml file:

kubectl apply -f ./cassandra-service.yaml

##Validate Cassandra service is running 
kubectl get svc cassandra

##Using a StatefulSet to create a Cassandra Ring

kubectl apply -f ./cassandra-statefulset.yaml

## Get the cassandra StatefulSet

kubectl get statefulset cassandra

kubectl get pods -l="app=cassandra"

kubectl exec -it cassandra-0 -- nodetool status


## Modifying the Cassandra StatefulSet

kubectl edit statefulset cassandra

## Change the number of replicas of your StatefulSet:

kubectl scale statefulsets <stateful-set-name> --replicas=<new-replicas>

kubectl apply -f <stateful-set-file-updated>

# Deleting a StatefulSet

kubectl delete -f <file.yaml>

kubectl delete statefulsets <statefulset-name>

## You may need to delete the associated headless service separately after the StatefulSet itself is deleted.

kubectl delete service <service-name>

## Deleting a StatefulSet through kubectl will scale it down to 0, thereby deleting all pods that are a part of it. If you want to delete just the StatefulSet and not the pods, use --cascade=false.

kubectl delete -f <file.yaml> --cascade=false

## By passing --cascade=false to kubectl delete, the Pods managed by the StatefulSet are left behind even after the StatefulSet object itself is deleted. If the pods have a label app=myapp, you can then delete them as follows:

kubectl delete pods -l app=myapp

# Persistent Volumes

grace=$(kubectl get pods <stateful-set-pod> --template '{{.spec.terminationGracePeriodSeconds}}')
kubectl delete statefulset -l app=myapp
sleep $grace
kubectl delete pvc -l app=myapp

# additional information to consider

cqlsh --version

kubectl exec -it cassandra-0 -- nodetool status
kubectl exec -it cassandra-0 cqlsh cassandra

# CQLSH commands to create data

CREATE KEYSPACE covidpapers WITH REPLICATION = {'class' : 'SimpleStrategy', 'replication_factor' : 3};
CONSISTENCY QUORUM;

CREATE KEYSPACE covidpapers WITH REPLICATION = {'class' : 'NetworkTopologyStrategy', 'DC1-CovidClstr' : 3};

use covidpapers;

Consistency level set to QUORUM.

