# Running a Cassandra Cluster and API to store COVID-19 data

## Want to learn how this project was built?
-- Blog post will be available from 21:00 on April 17, 2020 ---

## Want to use and deploy the project?
### Kubernetes
#### Installation Mac OS (Minikube)
The installation and steps described in this section were done using **homewbrew** for Mac OS https://brew.sh/ and Z shell instead of bash. 
*(I don't think the steps would differ too much in alternative setups, but beware.)*

Install and run [Minikube](https://kubernetes.io/docs/setup/minikube/):
```
brew update
brew upgrade
brew install minikube
```
Start minikube cluster:
```
minikube start -- memory 5120 --cpus=4
minikube dashboard
```
#### Installation Linux (Snaps)
Install Python 3 and Pip 3 if you are still using Python 2:
```
sudo apt-get install python3
sudo apt-get install python3-pip
```
Install kubernetes using [Snapcraft](https://snapcraft.io/):
```
sudo snap install microk8s --channel=1.18 --classic
```
(Recommended) Steps to avoid using sudo constantly when using kubernetes:
```
sudo usermod -a -G microk8s ubuntu
sudo chown -f -R ubuntu ~/.kube
```
Enabling kubernetes addons:
```
microk8s enable fluentd dns storage
```
##### (Optional) Using PyEnv:
Installing all the required packages in order to use [pyenv](https://github.com/pyenv/pyenv) in your project:
```
sudo apt install curl git-core make zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libssl-dev
git clone https://github.com/pyenv/pyenv.git $HOME/.pyenv
```
Edit your bash file `sudo vim ~/.bashrc` to properly configure path to binaries:
```
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

if command -v pyenv 1>/dev/null 2>&1; then
  eval "$(pyenv init -)"
fi
```
Restart the shell `exec "$SHELL"` and start using pyenv in your system `pyenv install 3.x.x` and `pyenv local 3.x.x` in the local dir of your choosing for example. 
*For further information on how to use pyenv, I recommend the following comprehensive post written by Logan Jones https://realpython.com/intro-to-pyenv/*
#### Using kubernetes
Label the node in which the app is going to run:
```
kubectl get nodes --show-labels

kubectl label nodes your_node app=cassandra

kubectl get nodes --show-labels
```

From the git root dir execute the **deploy-cluster.sh** script.

Check the state of the deployment by using any of the following commands:
```
kubectl describe statefulset cassandra
kubectl get pods -l="app=cassandra"
kubectl exec -it cassandra-0 -- nodetool status
```
Once all three pods are up we are ready to continue configuring our cassandra cluster.
##### (Worth knowing) Useful commands for troubleshooting your kubernetes deployment
Modifying the Cassandra StatefulSet:
```
kubectl edit statefulset cassandra
```
Change the number of replicas in your statefulset deployment:
```
kubectl scale statefulsets cassandra --replicas= x
```
Deleting a StatefulSet:
```
kubectl delete -f cassandra-statefulset.yaml
kubectl delete statefulset cassandra
```
Delete the associated services:
```
kubectl delete service cassandra
kubectl delete service cassandra-nodeport
kubectl delete service flask
```
Deleting a StatefulSet through kubectl will scale it down to 0, thereby deleting all pods that are a part of it. If you want to delete just the StatefulSet and not the pods, use --cascade=false:
```
kubectl delete -f <file.yaml> --cascade=false
```
By passing --cascade=false to kubectl delete, the Pods managed by the StatefulSet are left behind even after the StatefulSet object itself is deleted. If the pods have a label app=myapp, you can then delete them as follows:
```
kubectl delete pods -l app=myapp
```
Persistent Volumes:
```
grace=$(kubectl get pods <stateful-set-pod> --template '{{.spec.terminationGracePeriodSeconds}}')
kubectl delete statefulset -l app=myapp
sleep $grace
kubectl delete pvc -l app=myapp
```
### Cassandra
#### Configuring your cassandra deployment
Check the status of the cassandra environment:
```
kubectl exec -it cassandra-0 -- nodetool status
```
Enter the environment:
```
kubectl exec -it cassandra-o -- cqlsh
```
Execute the following commands:
```
CREATE KEYSPACE covid WITH REPLICATION = {'class': 'NetworkTopologyStrategy', 'DC1-CovidClstr' : 3};
CONSISTENCY QUORUM;
PAGING OFF;

CREATE TABLE covid.cases (Country text, Date date, Confirmed int, Deaths int, Recovered int, PRIMARY KEY (Country, Date)) WITH CLUSTERING ORDER BY (Date DESC);
```
### Flask
#### Installing requirements for running your python app
```
pip install -U -r requirements.txt
```
**(Optional) If you want to deploy the app as a docker container alongside your Cassandra Cluster I also included a Dockerfile for you to build your own**

#### Configuring the app to connect with your kubernetes cluster
Open app.py in your editor or IDE of choice and edit `cluster = Cluster(['...'], port=30007)` replacing the ellipsis with the ip of the kubernetes node that is running your cassandra cluster. If you don't know the IP you can see it by running the following command:
```
kubectl get nodes -o wide
```
Everything set. Cross your fingers and run the app!
```
python app.py
```
