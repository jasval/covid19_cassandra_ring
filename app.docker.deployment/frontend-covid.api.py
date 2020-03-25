from flask import Flask, request
from cassandra.cluster import Cluster

# we need to identify the IP of the container for the Cassandra deployment

cluster = Cluster(contact_points=[''], port=9042)
session = cluster.connect()
app = Flask(__name__)

@app.route('/')
def login():
    name = request.args.get("name","World")
    return('<h1>Hello, {}!</h1>'.format(name))
    
@app.route('/query/<search_terms>')
def query(search_terms):
    entries = session.execute("""Select * From covid.database where author = '{}' """.format(search_terms))
    
    for entry in entries:
        return('<h1> {} wrote {}</h1>'.format(name,entry.title))
        
    # Better if we save the information in a table and then output it in the webpage
    
    return('<h1>That author does not exist!</h1>')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
