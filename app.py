import os
import bisect
import re
from datetime import *

import requests
from cassandra.cluster import Cluster, NoHostAvailable
from cassandra.query import OperationTimedOut
from flask import Flask, abort, request, jsonify, g, url_for
from passlib.apps import custom_app_context as pwd_context
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from itsdangerous import (TimedJSONWebSignatureSerializer as Serialiser, BadSignature, SignatureExpired)

# Define the app context and configuring a basic database to store users and hand-out tokens for transactions
app = Flask(__name__)
app.config['SECRET_KEY'] = 'she call me mr boombastic'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# Define connection parameters to access a Cassandra Ring deployed in Kubernetes
cluster = Cluster(['192.168.64.4'], port=30007)
session = cluster.connect(wait_for_all_pools=True)

db = SQLAlchemy(app)
auth = HTTPBasicAuth()

# A list used to locally store the name of the countries available to lookup.
country_list = []


# Definition of a User model class to store in in our sqlite database.
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), index=True)
    password_hash = db.Column(db.String(256))

    def hash_password(self, password):
        self.password_hash = pwd_context.encrypt(password)

    def verify_password(self, password):
        return pwd_context.verify(password, self.password_hash)

    # Method to generate a token from our SECRET_KEY, with a TTL of 60 minutes
    def generate_auth_token(self, expiration=3600):
        s = Serialiser(app.config['SECRET_KEY'], expires_in=expiration)
        return s.dumps({'id': self.id})

    # Verify if the token provided by the user in a HTTP call is valid
    @staticmethod
    def verify_auth_token(token):
        s = Serialiser(app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except SignatureExpired:
            return None
        except BadSignature:
            return None
        user = User.query.get(data['id'])
        return user


# A method to verify if the date specified by the user meets our database requirement
def date_format_checker(x):
    r = re.compile('\d{4}-\d-\d')
    if r.match(x) is not None:
        return True
    return False


# ------------- THIS METHOD CAN BE DELETED LATER AFTER REFACTORING! --------------------

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


@auth.verify_password
def verify_password(user_name_token, password):
    # Verification by token given priority
    user = User.verify_auth_token(user_name_token)
    if not user:
        # Verification by stored password
        user = User.query.filter_by(username=user_name_token).first()
        if not user or not user.verify_password(password):
            return False
    g.user = user
    return True


@app.route('/', methods=['GET'])
def index():
    name = "Data Scientist or Curious User"
    return (
               '<h1>Hello, {}!</h1> </br> <p> This is an API offering the latest figures of COVID-19 Contagion accross the globe</p>'.format(
                   name)), 200


@app.route('/register', methods=['POST'])
def new_user():
    username = request.json.get('username')
    password = request.json.get('password')
    if username is None or password is None:
        return jsonify('Missing arguments'), 400
    if User.query.filter_by(username=username).first() is not None:
        return jsonify('There is already a username under that name'), 400
    user = User(username=username)
    user.hash_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({'username': user.username}), 201, {'Location': url_for('get_user', id=user.id, _external=True)}


@app.route('/users/<int:id>')
def get_user(id):
    user = User.query.get(id)
    if not user:
        abort(400)
    return jsonify({'username': user.username})


@app.route('/token')
@auth.login_required
def get_auth_token():
    token = g.user.generate_auth_token()
    return jsonify({'token': token.decode('ascii'), 'duration': 3600})


@app.route('/index', methods=['GET'])
def get_latest():
    template = 'https://api.covid19api.com/countries'
    if not country_list:
        resp = requests.get(template)
        if resp.ok:
            resp = resp.json()
            for x in resp:
                bisect.insort(country_list, x['Country'])
            return jsonify(country_list), 200
        else:
            return jsonify('Server side error'), 500
    else:
        return jsonify(country_list), 200


@app.route('/latest', methods=['GET'])
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
@app.route('/countries', methods=['GET'])
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


@app.route('/<country>', methods=['GET'])
def query_country(country):
    if country_exist(country) is False:
        return jsonify('That country doesn\'t exist'), 404
    else:
        try:
            __query = """SELECT * FROM covid.cases WHERE country_region in ('{}');""".format(country)
            entry = session.execute(__query, timeout=500).one()
            return jsonify({"Country": entry.country_region, "Date": str(entry.date), "confirmed": entry.confirmed,
                            "deaths": entry.deaths,
                            "recovered": entry.recovered}), 200
        except NoHostAvailable:
            jsonify({'The host is not available'}), 408
        except OperationTimedOut:
            jsonify({'The communication with host timed out'}), 408
        except Exception as ex:
            jsonify({ex.args}), 418


@app.route('/<country>/s', methods=['GET'])
def query_country_voice(country):
    if country_exist(country) is False:
        return jsonify('That country doesn\'t exist'), 404
    else:
        try:
            __query = """SELECT * FROM covid.cases WHERE country_region in ('{}');""".format(country)
            entry = session.execute(__query, timeout=500).one()
            return jsonify({"Country": entry.country_region, "Date": str(entry.date), "confirmed": entry.confirmed,
                            "deaths": entry.deaths,
                            "recovered": entry.recovered}), 200
        except NoHostAvailable:
            jsonify({'The host is not available'}), 408
        except OperationTimedOut:
            jsonify({'The communication with host timed out'}), 408
        except Exception as ex:
            jsonify({ex.args}), 418


@app.route('/hist/<country>', methods=['GET'])
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
@auth.login_required
def post_data(country, new_confirmed, new_deaths, new_recovered):
    if country_exist(country) is False:
        return jsonify('That country doesn\'t exist'), 404
    else:
        latest_entry = session.execute(
            """SELECT * FROM covid.cases WHERE country_region in ('{}') LIMIT 1;""".format(
                country)).one()
        date = datetime.now().strftime("%Y-%m-%d")
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


@app.route('/delete/<country>/<date_entry>', methods=['GET', 'DELETE'])
@auth.login_required
def delete_date_entry(country, date_entry):
    if country_exist(country) is True:
        if date_format_checker(date_entry) is True:
            try:
                __query = session.execute(
                    """DELETE FROM covid.cases WHERE country_region in ('{}') AND date IN ('{}');""".format(country,
                                                                                                            date_entry))
                return jsonify("Entry deleted"), 200
            except Exception:
                return jsonify("There was a problem deleting the entry."), 500
        else:
            return jsonify('Date badly formated... please format date correctly YYYY-MM-DD'), 400
    else:
        return jsonify("Country not found."), 404


@app.route('/delete/<country>/today', methods=['GET', 'DELETE'])
@auth.login_required
def delete_today_entry(country):
    if country_exist(country) is True:
        try:
            date_entry = datetime.now().strftime("%Y-%m-%d")
            __query = session.execute(
                """DELETE FROM covid.cases WHERE country_region in ('{}') AND date IN ('{}');""".format(country,
                                                                                                        date_entry))
            return jsonify("Entry deleted"), 200
        except Exception:
            return jsonify("There was a problem deleting the entry."), 400
    else:
        return jsonify("Country not found."), 404


@app.route('/delete/<country>', methods=['GET', 'DELETE'])
@auth.login_required
def delete_recent_entry(country):
    if country_exist(country) is True:
        try:
            __query = session.execute(
                """SELECT * FROM covid.cases WHERE country_region in ('{}') LIMIT 1""".format(country)).one()
            session.execute(
                """DELETE FROM covid.cases WHERE country_region in ('{}') AND date IN ('{}');""".format(country,
                                                                                                        __query.date))
            return jsonify("Entry deleted"), 200
        except Exception:
            return jsonify("There was a problem deleting the entry."), 400
    else:
        return jsonify("Country not found."), 404


@app.route('/edit/<country>/<date_entry>', methods=['PUT'])
@auth.login_required
def update_entry(country, date_entry):
    if country_exist(country) is False:
        return jsonify("Country not found"), 404
    confirmed = request.json.get('confirmed')
    deaths = request.json.get('deaths')
    recovered = request.json.get('recovered')
    if date_entry is None:
        now = datetime.now()
        date_entry = now.strftime("%Y-%m-%d")
        session.execute(
            """UPDATE covid.cases SET confirmed = '{}', deaths = '{}', recovered = '{}' WHERE country_region IN ('{}') AND date IN ('{}')""".format(
                confirmed, deaths, recovered, country, date_entry))
        return jsonify('Entry was modified'), 202
    else:
        if date_format_checker(date_entry) is True:
            try:
                session.execute(
                    """UPDATE covid.cases SET confirmed = '{}', deaths = '{}', recovered = '{}' WHERE country_region IN ('{}') AND date IN ('{}')""".format(
                        confirmed, deaths, recovered, country, date_entry))
                return jsonify('Entry was modified'), 202
            except Exception:
                return jsonify('Date not found'), 404
        else:
            return jsonify('Date badly formated... please format date correctly YYYY-MM-DD'), 400


if __name__ == '__main__':
    # Uncomment the next line if you want to run the app in http.
    if not os.path.exists('db.sqlite'):
        db.create_all()
    app.run(debug=True)
    # The following line calls for pyopenssl to allow the app to run in https.
    # app.run(ssl_context='adhoc')
