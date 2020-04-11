# Script for initialisation

$ sudo apt-get update
$ sudo apt-get upgrade
$ sudo apt-get install docker.io

$ sudo apt-get install python3
$ sudo apt-get install python3-pip

# (Optional) Install all the required packages for installing different Python versions from sources using following command in a Linux machine (Debian-Ubuntu)
	$ sudo apt install curl git-core gcc make zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libssl-dev
	## (Optional) step for managing Python versions easily for your project - by installing PyEnv
	$ git clone https://github.com/pyenv/pyenv.git $HOME/.pyenv
	## Edit your bash file to set path to .pyenv
	vim .bashrc
	## pyenv configs
		export PYENV_ROOT="$HOME/.pyenv"
		export PATH="$PYENV_ROOT/bin:$PATH"

		if command -v pyenv 1>/dev/null 2>&1; then
	 	   eval "$(pyenv init -)"
		fi
	# Then restart the shell
	$ exec "$SHELL"
	# Install the python versions that you would like to use 
	$ pyenv install 3.x.x
	# For further information on how to use pyenv check out this Github https://github.com/pyenv/pyenv
	
## Get minikube and necessary libraries
## Mac OSX - needs minikube to spin a VM in host machine
sudo apt-get install minikube 
minikube start --memory 5120 --cpus=4


## Linux -> doesnt need a VM
sudo snap install microk8s --channel=1.18 --classic

## Check microk8s status
sudo microk8s status
## Alias microk8s.kubectl to kubectl to simplify calling the tool
sudo snap alias microk8s.kubectl kubectl

## Check nodes running on the cluster
sudo kubectl get nodes

## Navigate to the dir where this git directory has been cloned and continue the setup

##Track all cassandra statefulset nodes from cassandra-service.yaml file:
kubectl apply -f ./cassandra-service.yaml

##Validate Cassandra service is running 
kubectl get svc cassandra

## Label the node in which your app is going to run
kubectl get nodes --show-labels

kubectl label nodes <name_of_node> app=cassandra

kubectl get nodes --show-labels



microk8s enable ---> Fill with data from tabs

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

