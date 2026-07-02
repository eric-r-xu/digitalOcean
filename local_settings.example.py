import os

MYSQL_AUTH = {
    "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "user": os.environ.get("MYSQL_USER", "site_user"),
    "password": os.environ.get("MYSQL_PASSWORD", "change-me"),
}

# Keep these values in sync with the city dimension table used by /klaviyo.
city_name_to_id = {
    "San Francisco, CA": 5391959,
    "New York, NY": 5128581,
}
cityNameSet = set(city_name_to_id.keys())
