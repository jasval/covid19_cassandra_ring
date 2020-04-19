import os
import re
from datetime import *

import requests
from cassandra.cluster import Cluster, NoHostAvailable
from cassandra.query import OperationTimedOut, BatchStatement, ConsistencyLevel
from flask import Flask, abort, request, jsonify, g, url_for
from flask_httpauth import HTTPBasicAuth
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import (TimedJSONWebSignatureSerializer as Serialiser, BadSignature, SignatureExpired)
from passlib.apps import custom_app_context as pwd_context

# Define the app context and configuring a basic database to store users and hand-out tokens for transactions
app = Flask(__name__)
app.config['SECRET_KEY'] = 'she call me mr boombastic'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True

# Define connection parameters to access a Cassandra Ring deployed in Kubernetes
cluster = Cluster(['192.168.64.4'], port=30007)
session = cluster.connect(wait_for_all_pools=True)

db = SQLAlchemy(app)
auth = HTTPBasicAuth()

# Dict used to locally store the name of the countries and their corresponding slugs for fast lookup.
country_dict = {}

# Prepared statements
cql_insert = 'INSERT INTO covid.cases (country, date, confirmed, deaths, recovered) VALUES (?, ?, ?, ?, ?)'
cql_get_country = """SELECT * FROM covid.cases WHERE country in ('{}');"""
cql_get_country_limit = """SELECT * FROM covid.cases WHERE country in ('{}') LIMIT 1"""
cql_delete = """DELETE FROM covid.cases WHERE country in ('{}') AND date IN ('{}');"""
cql_update = """UPDATE covid.cases SET confirmed = {}, deaths = {}, recovered = {} WHERE country
                                                                                IN ('{}') AND date IN ('{}')"""


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


#
# The following are a collection of helper functions to format strings:
#
# date_format_checker() --> will check that dates will follow the Date format supported by Apache Cassandra.
# clean_country()       --> will check for rogue apostrophes in country names that might break queries, and will
#                           escape then with a "\" character.
# reformat_date()       --> will slice the date string pulled from the external API.
#
def date_format_checker(x):
    r = re.compile("\d{4}-\d{2}-\d{2}")
    if r.match(x) is not None:
        return True
    return False


def clean_country(country):
    char_position = country.find('\'')
    escape_char = "\'"
    if char_position != -1:
        clean_result = str(country[: char_position]) + escape_char + str(country[char_position:])
        return str(clean_result)
    else:
        return country


def reformat_date(x_date):
    char_position = x_date.find('T')
    if char_position != -1:
        x_date = x_date[: char_position]
    return x_date


# Function that will check passwords or tokens against
# our sqlite user database to ensure they are valid.
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
def welcome():
    name = "Data Scientist or Curious User"
    return (
               '<h1>Hello, {}!</h1> </br> <p> This is an API offering the latest figures of COVID-19 '
               '                                    Contagion accross the globe</p>'.format(name)), 200


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
    return jsonify({'username': user.username}), 201, \
           {'Location': url_for('get_user', id=user.id, _external=True)}


@app.route('/users/<int:id>', methods=['GET'])
def get_user(id):
    user = User.query.get(id)
    if not user:
        abort(400)
    return jsonify({'username': user.username})


# A function that generates a perishable token associated
# with a user passed in a JSON Object
@app.route('/token', methods=['GET'])
@auth.login_required
def get_auth_token():
    token = g.user.generate_auth_token()
    return jsonify({'token': token.decode('ascii'), 'duration': 3600})


# A function that builds a dictionary of countries to use
# as a quick reference to validate slugs and country names.
@app.route('/index', methods=['GET'])
def init_index():
    template = 'https://api.covid19api.com/countries'
    if not country_dict:
        resp = requests.get(template)
        if resp.ok:
            resp = resp.json()
            for x in resp:
                country_dict[x['Slug']] = x['Country']
            return jsonify(sorted(country_dict)), 200
    return jsonify(sorted(country_dict)), 200


# A function that populates the database for the first time,
# it divides queries in batches per country to lessen the stress in the Cassandra Cluster.
@app.route('/initialise', methods=['POST'])
@auth.login_required
def init():
    init_index()
    ans = session.execute('SELECT * FROM covid.cases LIMIT 1').one()
    if ans is None:
        insert_entry = session.prepare(cql_insert)
        template = 'https://api.covid19api.com/total/dayone/country/{name}'
        amount = 0
        for slug in country_dict:
            resp = requests.get(template.format(name=slug))
            if resp.ok:
                data = resp.json()
                # Sets consistency level to quorum to consider a request as successful if
                # at least two replicas return a success.
                batch = BatchStatement(consistency_level=ConsistencyLevel.QUORUM)
                for entry in data:
                    amount += 1
                    formatted_date = reformat_date(entry['Date'])
                    try:
                        batch.add(insert_entry, (
                            entry['Country'], formatted_date, entry['Confirmed'], entry['Deaths'],
                            entry['Recovered']))
                    except Exception as e:
                        print('Cassandra error: {}'.format(e))
                try:
                    print(str(len(data)) + "  " + country_dict[slug])
                    session.execute(batch)
                except Exception as e:
                    print('Cassandra error: {}'.format(e))
        print(amount)
        return jsonify('The database has been populated with the '
                       'latest up to date COVID cases worldwide'), 201
    else:
        return jsonify('Table has already been initialised'), 208


@app.route('/latest', methods=['GET'])
def show_latest_entries():
    # PER PARTITION LIMIT 1 limits results to one result based on our partition key which is Date.
    result_set = session.execute("""SELECT * FROM covid.cases PER PARTITION LIMIT 1;""", timeout=800).all()
    results = []
    for entry in result_set:
        results.append({".Country": entry.country, ".Date": str(entry.date), "Confirmed": entry.confirmed,
                        "Deaths": entry.deaths,
                        "Recovered": entry.recovered})
    # Sort our results using a lambda function applied to our PRIMARY KEY
    sorted_results = sorted(results, key=lambda x: x['.Country'])
    return jsonify(sorted_results), 200


@app.route('/country/<slug>', methods=['GET'])
def query_country(slug):
    init_index()
    if slug in country_dict:
        try:
            entry = session.execute(cql_get_country.format(country_dict[slug]), timeout=500).one()
            return jsonify({".Country": entry.country, ".Date": str(entry.date), "Confirmed": entry.confirmed,
                            "Deaths": entry.deaths,
                            "Recovered": entry.recovered}), 200
        except NoHostAvailable:
            return jsonify('The host is not available'), 408
        except OperationTimedOut:
            return jsonify('The communication with host timed out'), 408
        except Exception as ex:
            return jsonify('Something else went wrong!  ' + str(ex.args)), 418
    else:
        return jsonify('That country doesn\'t exist'), 404


@app.route('/hist/country/<slug>', methods=['GET'])
def query(slug):
    init_index()
    if slug in country_dict:
        try:
            entries = session.execute(cql_get_country.format(country_dict[slug]), timeout=500).all()
            results = []
            for entry in entries:
                results.append(
                    {".Country": entry.country, ".Date": str(entry.date), "Confirmed": entry.confirmed,
                     "Deaths": entry.deaths,
                     "Recovered": entry.recovered})
            return jsonify(results), 200
        except NoHostAvailable:
            return jsonify('The host is not available'), 408
        except OperationTimedOut:
            return jsonify('The communication with host timed out'), 408
        except Exception as ex:
            return jsonify('Something else went wrong!  ' + str(ex.args)), 418
    else:
        return jsonify('That country doesn\'t exist'), 404


@app.route('/update/<slug>', methods=['POST'])
@auth.login_required
def update_data(slug):
    init_index()
    if slug in country_dict:
        template = 'https://api.covid19api.com/total/country/{name}'
        resp = requests.get(template.format(name=slug))
        if resp.ok:
            last_entry = session.execute(cql_get_country_limit.format(country_dict[slug])).one()
            data = resp.json()
            for entry in data:
                entry['Date'] = reformat_date(entry['Date'])
            # Filter results into a new list only considering entries whose dates start after the last entry on the db.
            output_dict = [x for x in data if x['Date'] > str(last_entry.date)]
            batch = BatchStatement(consistency_level=ConsistencyLevel.QUORUM)
            for entry in output_dict:
                batch.add(session.prepare(cql_insert),
                          (entry['Country'], entry['Date'], entry['Confirmed'],
                           entry['Deaths'], entry['Recovered']))
            session.execute(batch)
            return jsonify('Entries from {} are now up to date'.format(country_dict[slug])), 200
        else:
            return jsonify('There has been a problem with the external API'), 500
    else:
        return jsonify('That country doesn\'t exist'), 404


@app.route('/update', methods=['POST'])
@auth.login_required
def update_all_data():
    init_index()
    insert_entry = session.prepare(cql_insert)
    template = 'https://api.covid19api.com/total/country/{name}'
    for slug in country_dict:
        resp = requests.get(template.format(name=slug))
        if resp.ok:
            batch = BatchStatement(consistency_level=ConsistencyLevel.QUORUM)
            country_name = clean_country(country_dict[slug])
            last_entry = session.execute(cql_get_country_limit.format(country_name)).one()
            data = resp.json()
            for entry in data:
                entry['Date'] = reformat_date(entry['Date'])
            output_dict = [x for x in data if x['Date'] > str(last_entry.date)]
            for entry in output_dict:
                country_name = clean_country(entry['Country'])
                batch.add(insert_entry,
                          (country_name, entry['Date'], entry['Confirmed'],
                           entry['Deaths'], entry['Recovered']))
            session.execute(batch)
        else:
            return jsonify('There has been a problem with the external API'), 500
    return jsonify('Entries from all countries are now up to date'), 200


@app.route('/delete/today/<slug>', methods=['DELETE'])
@auth.login_required
def delete_today_entry(slug):
    init_index()
    if slug in country_dict:
        try:
            date_entry = datetime.now().strftime("%Y-%m-%d")
            __query = session.execute(cql_delete.format(country_dict[slug], date_entry))
            return jsonify("Entry deleted"), 200
        except Exception as ex:
            return jsonify('There was a problem deleting the entry ' + str(ex.args)), 400
    else:
        return jsonify("Country not found."), 404


@app.route('/delete/recent', methods=['DELETE'])
@auth.login_required
def delete_recent():
    init_index()
    try:
        for slug in country_dict:
            __query = session.execute(cql_get_country_limit.format(country_dict[slug])).one()
            session.execute(cql_delete.format(country_dict[slug], __query.date))
        return jsonify('Entries deleted'), 200
    except Exception as ex:
        return jsonify('There was a problem deleting the entries ' + str(ex.args)), 500


@app.route('/delete/recent/<slug>', methods=['DELETE'])
@auth.login_required
def delete_recent_entry(slug):
    init_index()
    if slug in country_dict:
        try:
            __query = session.execute(cql_get_country_limit.format(country_dict[slug])).one()
            session.execute(cql_delete.format(country_dict[slug], __query.date))
            return jsonify('Entry deleted'), 200
        except Exception as ex:
            return jsonify('There was a problem deleting the entry ' + str(ex.args)), 500
    else:
        return jsonify('Country not found'), 404


@app.route('/delete/<entry_date>', methods=['DELETE'])
@auth.login_required
def delete_date(entry_date):
    init_index()
    if date_format_checker(entry_date) is True:
        try:
            for slug in country_dict:
                session.execute(cql_delete.format(country_dict[slug], entry_date))
            return jsonify('Entries deleted'), 200
        except Exception as ex:
            return jsonify('There was a problem deleting the entries ' + str(ex.args)), 500
    else:
        return jsonify('Date format should be YYYY-MM-DD'), 400


@app.route('/delete/<entry_date>/<slug>', methods=['DELETE'])
@auth.login_required
def delete_date_entry(entry_date, slug):
    init_index()
    if slug in country_dict and date_format_checker(entry_date) is True:
        try:
            session.execute(cql_delete.format(country_dict[slug], entry_date))
            return jsonify('Entry deleted'), 200
        except Exception as ex:
            return jsonify('There was a problem deleting the entry ' + str(ex.args)), 500
    else:
        return jsonify('Some parameters are not ok, '
                       'check country slug and date format YYYY-MM-DD'), 400


@app.route('/edit/<date_entry>/<slug>', methods=['PUT'])
@auth.login_required
def update_entry(date_entry, slug):
    init_index()
    if slug in country_dict and date_format_checker(date_entry) is True:
        confirmed = request.json.get('confirmed')
        deaths = request.json.get('deaths')
        recovered = request.json.get('recovered')
        print(confirmed)
        print(deaths)
        print(recovered)
        try:
            session.execute(cql_update.format(confirmed, deaths, recovered, country_dict[slug], date_entry))
            return jsonify('Entry was modified'), 202
        except Exception as ex:
            return jsonify('There was a problem editing the entry ' + str(ex.args)), 500
    else:
        return jsonify('Some parameters are not ok, '
                       'check country slug and date format YYYY-MM-DD'), 400


if __name__ == '__main__':
    if not os.path.exists('db.sqlite'):
        db.create_all()
    app.run(host='0.0.0.0', port=80, debug=True)
