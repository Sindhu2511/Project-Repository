import os

import psycopg
from dotenv import load_dotenv

load_dotenv()
conn = psycopg.connect(
    host=os.environ["DB_HOST"],
    port=os.environ["DB_PORT"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    dbname="postgres",          # built-in database that always exists
    sslmode="require",          # RDS requires encrypted connections
    connect_timeout=10,
    autocommit=True,
)
names = [r[0] for r in conn.execute(
    "SELECT datname FROM pg_database WHERE NOT datistemplate").fetchall()]
print("Connected. Databases:", names)

target = os.environ["DB_NAME"]
if target not in names:
    conn.execute(f'CREATE DATABASE "{target}"')
    print("Created database:", target)
conn.close()