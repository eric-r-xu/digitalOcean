import logging
import datetime
import os

import pandas as pd
import numpy as np
from flask import Flask, request, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mysqldb import MySQL
from flask_sqlalchemy import SQLAlchemy
from pytz import timezone
from validate_email import validate_email
from validate_email.updater import update_builtin_blacklist
from werkzeug.middleware.proxy_fix import ProxyFix

from initialize_mysql_rain import lat_lon_dict, location_names
from local_settings import MYSQL_AUTH, cityNameSet, city_name_to_id

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

app.config["MYSQL_HOST"] = MYSQL_AUTH["host"]
app.config["MYSQL_USER"] = MYSQL_AUTH["user"]
app.config["MYSQL_PASSWORD"] = MYSQL_AUTH["password"]
app.config["MYSQL_DB"] = "klaviyo"


mysql = MySQL(app)


def timetz(*args):
    return datetime.datetime.now(tz).timetuple()


# logging datetime in PST
tz = timezone("US/Pacific")
logging.Formatter.converter = timetz
log_file = os.environ.get("MYPROJECT_LOG_FILE", "logs/myproject.log")
log_dir = os.path.dirname(log_file)
if log_dir:
    os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    filename=log_file,
    format="%(asctime)s %(levelname)s: %(message)s",
    level=logging.INFO,
    datefmt=f"%Y-%m-%d %H:%M:%S ({tz})",
)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri=os.environ.get(
        "RATELIMIT_STORAGE_URI", "redis://127.0.0.1:6379/0"
    ),
    key_prefix="digitalocean",
    headers_enabled=True,
)

app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqldb://%s:%s@%s/%s" % (
    MYSQL_AUTH["user"],
    MYSQL_AUTH["password"],
    MYSQL_AUTH["host"],
    "rain",
)

db = SQLAlchemy(app)


@app.route("/")
def base():
    return render_template("index.html")


@app.route("/research")
def research():
    return render_template("research.html")


@app.route("/old")
def base2():
    return render_template("index_old.html")


@app.route("/rain")
def rain_app():
    return render_template("rain_service.html", location_names=location_names)


@app.route("/rain", methods=(["POST"]))
@limiter.limit("50 per hour; 500 per day")
def rain_gen_html_table():
    i_location_name = str(request.form["i_location_name"])
    if i_location_name not in lat_lon_dict:
        return "Please choose a location from the list"

    i_location_lat, i_location_lon = (
        lat_lon_dict[i_location_name]["lat"],
        lat_lon_dict[i_location_name]["lon"],
    )
    with db.engine.connect() as conn:
        df_pre = pd.read_sql_query(
            f"""
            SELECT  
                MIN(SUBSTR(CONVERT_TZ(FROM_UNIXTIME(dt),'UTC','US/Pacific'),1,13)) AS "First API Update Hour (PST)",
                MAX(SUBSTR(CONVERT_TZ(FROM_UNIXTIME(dt),'UTC','US/Pacific'),1,13)) AS "Last API Update Hour (PST)",
                MAX(CONVERT_TZ(FROM_UNIXTIME(requested_dt),'UTC','US/Pacific')) AS "Last API Request Time (PST)"
            FROM 
                rain.tblFactLatLon 
            WHERE 
                location_name = "{i_location_name}" 
                AND lat = {i_location_lat} 
                AND lon = {i_location_lon}
            """,
            conn,
        )
        df = pd.read_sql_query(
            f"""
        SELECT  
            location_name AS "Location Name",
            {i_location_lat} AS "Latitude",
            {i_location_lon} AS "Longitude",
            SUBSTR(CONVERT_TZ(FROM_UNIXTIME(dt),'UTC','US/Pacific'),1,13) AS "Weather Date Hour (PST)",
            MAX(rain_1h) AS "Rainfall (mm) Last 1 hour" 
        FROM 
            rain.tblFactLatLon 
        WHERE 
            location_name = "{i_location_name}" 
            AND lat = {i_location_lat} 
            AND lon = {i_location_lon} 
            AND (rain_1h > 0) 
        GROUP BY 
            1,2,3,4
        ORDER BY 
            4 DESC
        """,
            conn,
        )
    return render_template(
        "rain_service_result.html",
        tables=[df_pre.to_html(classes="data"), df.to_html(classes="data")],
        titles=np.concatenate([df_pre.columns.values, df.columns.values]),
    )


# update email blacklist
try:
    update_builtin_blacklist(force=True, background=True)
except Exception:
    logging.exception("Unable to update email validation blacklist")


@app.route("/klaviyo")
def klaviyo_weather_app_html():
    return render_template("subscribe.html", cityNameSet=cityNameSet)


@app.route("/klaviyo", methods=["POST"])
@limiter.limit("50 per hour; 500 per day")
def klaviyo_weather_app_post():
    i_email = str(request.form["i_email"]).lower()
    is_valid = validate_email(
        email_address=i_email, check_format=True, check_blacklist=True
    )

    if not is_valid:
        return str("Unable to validate email address: %s" % i_email)

    i_city_name = str(request.form["i_city"])
    if i_city_name not in cityNameSet:
        return "Please choose a city from the list"

    i_city_id = int(city_name_to_id[i_city_name])
    cur = mysql.connection.cursor()
    try:
        logging.info(
            cur.execute(
                "DELETE FROM tblDimEmailCity WHERE email=%s AND city_id=%s",
                (i_email, i_city_id),
            )
        )

        logging.info(
            cur.execute(
                "INSERT INTO tblDimEmailCity(email, city_id) VALUES (%s, %s)",
                (i_email, i_city_id),
            )
        )
        mysql.connection.commit()
    except Exception as error:
        error_message = str("Caught this error: " + repr(error))
        if error_message.count("Duplicate entry") > 0:
            return str(
                "Existing subscription found for %s and location %s"
                % (i_email, i_city_name)
            )
        else:
            return error_message
    finally:
        cur.close()
    return str(
        "SUCCESS! email: %s is now subscribed to weather powered emails for %s for 10 days"
        % (i_email, i_city_name)
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0")
