from datetime import *
from time import sleep
import pandas as pd
from cassandra.cluster import Cluster, NoHostAvailable
from cassandra.query import OperationTimedOut
from flask import *

# We need to identify the IP of the container for the Cassandra deployment
# cluster = Cluster(contact_points=[''], port=9042)
# Or default to localhost

app = Flask(__name__)

cluster = Cluster(contact_points=['10.96.0.1'], port=9042)
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


def country_exist(country):
    __query = session.execute("""SELECT * FROM covid.database WHERE ('{}')""".format(country))
    if __query is not None:
        return True
    else:
        return False


def reformat_date(x_date):
    date_object = datetime.strptime(x_date, '%Y-%m-%d')
    return date_object.strftime('%Y-%m-%d')


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
        jsonify("The host is not available"), 408
    except OperationTimedOut:
        jsonify("The communication with host timed out."), 408
    except Exception as ex:
        jsonify(ex.args)

    # data = pd.read_json('path/.json')
    # data.set_index(['Name'], inplace=True)
    # data.index.name = None
    # females = data.loc[data.Gender == 'f']
    # males = data.loc[data.Gender == 'm']
    # return render_template('view.html', tables=[females.to_html(classes='female'), males.to_html(classes='male')],
    #                      titles=['na', 'Female surfers', 'Male surfers'])


@app.route('/hist/<country>/', methods=['GET'])
def query(country):
    try:
        if check_browser() is True:
            __query = session.execute(
                """SELECT * FROM covid.database WHERE country_region in ('{}') """.format(country))
            table = data_getter(__query)
            return render_template('result.html', tables=[table.to_html(classes='data', header="true")]), 200
        else:
            __query = """SELECT JSON * FROM covid.database WHERE country_region in ('{}');""".format(country)
            json_data = session.execute(__query, timeout=None)
            return json_data, 200
    except NoHostAvailable:
        jsonify("The host is not available"), 408
    except OperationTimedOut:
        jsonify("The communication with host time out."), 408
    except Exception as ex:
        jsonify(ex.args), 418


@app.route('/post/<country>/<new_confirmed>-<new_deaths>-<new_recovered>', methods=['GET', 'POST'])
def post_data(country, new_confirmed, new_deaths, new_recovered):
    try:
        if country_exist(country) is False:
            print("That country doesn't exist"), 404
        if check_browser() is True:
            latest_entry = session.execute(
                """SELECT * FROM covid.database WHERE country_region in ('{}') ORDER BY date DESC LIMIT 1""".format(
                    country))
            confirmed = latest_entry.confirmed + new_confirmed
            deaths = latest_entry.deaths + new_deaths
            recovered = latest_entry.recovered + new_recovered
            today = date.today().strftime("%Y-%m-%d")
            try:
                session.execute("""INSERT INTO covid.database (country_region, date, confirmed, deaths, lat, long, recovered)
                            VALUES ('{}', '{}', '{}', '{}', '{}');""".format(country, today, confirmed, deaths,
                                                                             recovered))
                sleep(1)
                latest_entry = session.execute(
                    """SELECT * FROM covid.database WHERE country_region in ('{}') ORDER BY date DESC LIMIT 1""".format(
                        country))
                return latest_entry, 201
            except Exception as ex:
                jsonify(ex.args), 406
    except Exception as ex:
        jsonify(ex.args), 418


@app.route('/delete/<date_entry>/<country>', methods=['DELETE'])
def delete_entry(date_entry, country):
    date_entry = reformat_date(date_entry)
    if country_exist(country) is True:
        try:
            __query = session.execute(
                """DELETE * FROM covid.database WHERE country_region in ('{}') AND date == ('{}');""".format(country, date_entry))
            return jsonify("Entry deleted"), 200
        except Exception as ex:
            jsonify(ex.args), 400
    else:
        return jsonify("Entry not found"), 404


if __name__ == '__main__':
    # Uncomment the next line if you want to run the app in http.
    app.run(debug=True)
    # The following line calls for pyopenssl to allow the app to run in https.
    # app.run(ssl_context='adhoc')
