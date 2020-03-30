from cassandra.query import OperationTimedOut
from flask import *
import pandas as pd
from cassandra.cluster import Cluster, NoHostAvailable

# We need to identify the IP of the container for the Cassandra deployment
# cluster = Cluster(contact_points=[''], port=9042)
# Or default to localhost

app = Flask(__name__)

cluster = Cluster()
session = cluster.connect('cassandra', wait_for_all_pools=True)


def data_getter(q):
    try:
        if q is not None:
            rows = session.execute(q, timeout=None)
            if len(rows) == 0:
                return jsonify({'error': 'There are no results matching your query'}), 404
            else:
                table = pd.DataFrame(rows)
            return table
        else:
            raise Exception('DataIsNull')
    except Exception as ex:
        print(ex.args)


def check_browser():
    browser = request.user_agent.browser
    if browser == '*chrome*' or browser == '*firefox*' or browser == "safari":
        return True
    else:
        return False


def data_to_json(formatted_query):
    json_data = pd.DataFrame()


@app.route('/', methods=['GET'])
def index():
    name = "New User"
    return (
               '<h1>Hello, {}!</h1>'.format(name),
               '<p>This is a RESTful API offering COVID-19 metrics.</p>'
           ), 200


# noinspection PyBroadException
@app.route('/entries/', methods=['GET'])
def show_all_entries():
    try:
        session.execute('USE covidpapers')
        if check_browser() is True:
            __query = 'SELECT * FROM cases ORDER BY country_region DESC;'
            table = data_getter(__query)
            return render_template('results.html', tables=[table.to_html(classes='data', header="true")]), 200
        else:
            __query = 'SELECT JSON * FROM cases;'
            json_data = session.execute(__query, timeout=None)
            return json_data, 200
    except NoHostAvailable:
        print("The host is not available"), 408
    except OperationTimedOut:
        print("The communication with host timed out."), 408
    except Exception as ex:
        print(ex.args)

    # data = pd.read_json('path/.json')
    # data.set_index(['Name'], inplace=True)
    # data.index.name = None
    # females = data.loc[data.Gender == 'f']
    # males = data.loc[data.Gender == 'm']
    # return render_template('view.html', tables=[females.to_html(classes='female'), males.to_html(classes='male')],
    #                      titles=['na', 'Female surfers', 'Male surfers'])


@app.route('/<country>/', methods=['GET'])
def query(country):
    entries = session.execute("""SELECT * FROM covid.database WHERE country_region in ('{}') """.format(country))

    for entry in entries:
        return '<h1> ... </h1>', 200

    # Better if we save the information in a table and then output it in the webpage

    return '<h1>That author does not exist!</h1>'


if __name__ == '__main__':
    # Uncomment the next line if you want to run the app in http.
    app.run(debug=True, host='0.0.0.0', port=80)
    # The following line calls for pyopenssl to allow the app to run in https.
    # app.run(ssl_context='adhoc')
