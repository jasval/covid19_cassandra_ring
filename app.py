from datetime import *
from time import sleep
from cassandra.cluster import Cluster, NoHostAvailable
from cassandra.query import OperationTimedOut
from flask import *
import bisect
from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model

# We need to identify the IP of the container for the Cassandra deployment
# cluster = Cluster(contact_points=[''], port=9042)
# Or default to localhost

app = Flask(__name__)

cluster = Cluster(['192.168.64.4'], port=30007)
session = cluster.connect(wait_for_all_pools=True)


def country_exist(country):
    countries = []
    results = session.execute("""SELECT DISTINCT country_region FROM covid.cases;""")
    for entry in results:
        bisect.insort(countries, entry.country_region)
    if country not in countries:
        return False
    else:
        return True


def clean_country(country):
    char_position = country.find('\'')
    escape_char = "\'"
    if char_position != -1:
        clean_result = str(country[: char_position]) + escape_char + str(country[char_position:])
        return str(clean_result)
    else:
        return country


def reformat_date(x_date):
    date_object = datetime.strptime(x_date, '%Y-%m-%d')
    return date_object


@app.route('/', methods=['GET'])
def index():
    name = "Data Scientist or Curious User"
    return (
               '<h1>Hello, {}!</h1> </br> <p> This is an API offering the latest figures of COVID-19 Contagion accross the globe</p>'.format(
                   name)), 200


@app.route('/latest/', methods=['GET'])
def show_latest_entries():
    countries_str = ""
    results = session.execute("""SELECT DISTINCT country_region FROM covid.cases;""")
    for entry in results:
        clean = clean_country(entry.country_region)
        countries_str += clean + ", "
    __query = (
        """SELECT country_region, date, confirmed, deaths, recovered FROM covid.cases PER PARTITION LIMIT 1;""".format(
            countries_str))
    result_set = session.execute(__query, timeout=800)
    results = []
    for entry in result_set:
        results.append({"Country": entry.country_region, "Date": str(entry.date), "confirmed": entry.confirmed,
                        "deaths": entry.deaths,
                        "recovered": entry.recovered})
    results.sort()
    return jsonify(results), 200


# noinspection PyBroadException
@app.route('/countries/', methods=['GET'])
def show_all_countries():
    countries = []
    try:
        results = session.execute("""SELECT DISTINCT country_region FROM covid.cases;""")
        for entry in results:
            bisect.insort(countries, entry.country_region)
        return jsonify(countries), 200
    except NoHostAvailable:
        jsonify({'The host is not available'}), 408
    except OperationTimedOut:
        jsonify({'The communication with host timed out'}), 408
    except Exception as ex:
        jsonify({ex.args}), 418

    # data = pd.read_json('path/.json')
    # data.set_index(['Name'], inplace=True)
    # data.index.name = None
    # females = data.loc[data.Gender == 'f']
    # males = data.loc[data.Gender == 'm']
    # return render_template('view.html', tables=[females.to_html(classes='female'), males.to_html(classes='male')],
    #                      titles=['na', 'Female surfers', 'Male surfers'])


@app.route('/hist/<country>/', methods=['GET'])
def query(country):
    if country_exist(country) is False:
        return jsonify('That country doesn\'t exist'), 404
    else:
        try:
            __query = """SELECT * FROM covid.cases WHERE country_region in ('{}');""".format(country)
            json_data = session.execute(__query, timeout=500)
            results = []
            for entry in json_data:
                results.append(
                    {"Country": entry.country_region, "Date": str(entry.date), "confirmed": entry.confirmed,
                     "deaths": entry.deaths,
                     "recovered": entry.recovered})
            return jsonify(results), 200
        except NoHostAvailable:
            jsonify({'The host is not available'}), 408
        except OperationTimedOut:
            jsonify({'The communication with host timed out'}), 408
        except Exception as ex:
            jsonify({ex.args}), 418


@app.route('/post/<country>/<new_confirmed>/<new_deaths>/<new_recovered>', methods=['GET', 'POST'])
def post_data(country, new_confirmed, new_deaths, new_recovered):
    if country_exist(country) is False:
        return jsonify('That country doesn\'t exist'), 404
    else:
        latest_entry = session.execute(
            """SELECT * FROM covid.cases WHERE country_region in ('{}') LIMIT 1;""".format(
                country)).one()
        now = datetime.now()
        date = now.strftime("%Y-%m-%d")
        if str(latest_entry.date) == str(date):
            return jsonify('There is already an entry for today!'), 409
        else:
            confirmed = float(latest_entry.confirmed) + float(new_confirmed)
            deaths = float(latest_entry.deaths) + float(new_deaths)
            recovered = float(latest_entry.recovered) + float(new_recovered)
            lat = float(latest_entry.lat)
            long = float(latest_entry.long)
            try:
                session.execute(
                    """INSERT INTO covid.cases(country_region, date, confirmed, deaths, lat, long, recovered) VALUES('{}','{}',{},{},{},{},{})""".format(
                        str(country), date, float(confirmed), float(deaths), float(lat), float(long), float(recovered)))
                return jsonify(
                    'Ok, updated {} and the current metrics are... Confirmed cases: {} Deaths: {} Recovered cases: {}'.format(
                        country, confirmed, deaths, recovered)), 201
            except Exception:
                return jsonify('There was a problem submitting your query!'), 500


@app.route('/delete/<date_entry>/<country>', methods=['GET', 'DELETE'])
def delete_entry(date_entry, country):
    if country_exist(country) is True:
        try:
            __query = session.execute(
                """DELETE FROM covid.cases WHERE country_region in ('{}') AND date IN ('{}');""".format(country,
                                                                                                        date_entry))
            return jsonify("Entry deleted"), 200
        except Exception as ex:
            return jsonify("ex.args"), 400
    else:
        return jsonify("Country not found"), 404


@app.route('/delete/<country>', methods=['GET', 'DELETE'])
def delete_recent(country):
    if country_exist(country) is True:
        try:
            now = datetime.now()
            date_entry = now.strftime("%Y-%m-%d")
            __query = session.execute(
                """DELETE FROM covid.cases WHERE country_region in ('{}') AND date IN ('{}');""".format(country,
                                                                                                        date_entry))
            return jsonify("Entry deleted"), 200
        except Exception as ex:
            return jsonify("ex.args"), 400
    else:
        return jsonify("Country not found"), 404


if __name__ == '__main__':
    # Uncomment the next line if you want to run the app in http.
    app.run(debug=True)
    # The following line calls for pyopenssl to allow the app to run in https.
    # app.run(ssl_context='adhoc')
