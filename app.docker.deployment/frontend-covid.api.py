from flask import *
import pandas as pd
from cassandra.cluster import Cluster

# we need to identify the IP of the container for the Cassandra deployment

cluster = Cluster(contact_points=[''], port=9042)
session = cluster.connect()
app = Flask(__name__)

@app.route('/')
def login():
    name = request.args.get("name","World")
    return('<h1>Hello, {}!</h1>'.format(name))

@app.route("/table")
def show_entries():
    data = pd.read_json('path/.json')
    data.set_index(['Name'], inplace=True)
    data.index.name=None
    females = data.loc[data.Gender=='f']
    males = data.loc[data.Gender=='m']
    return render_template('view.html',tables=[females.to_html(classes='female'), males.to_html(classes='male')],
    titles = ['na', 'Female surfers', 'Male surfers'])

@app.route('/query/<search_terms>')
def query(search_terms):
    entries = session.execute("""Select * From covid.database where author = '{}' """.format(search_terms))
    
    for entry in entries:
        return('<h1> {} wrote {}</h1>'.format(name,entry.title))
        
    # Better if we save the information in a table and then output it in the webpage
    
    return('<h1>That author does not exist!</h1>')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
