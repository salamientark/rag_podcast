#!/bin/bash

# Load env file
source .env

PORT=5442

# Create data directory for PostgreSQL
initdb -D ./data/db_data/
mkdir ./data/db_data/sockets
sed -i "/^#unix_socket_directories.*/c\unix_socket_directories = \'$PWD/data/db_data/sockets\'" data/db_data/postgresql.conf

# Start PostgreSQL server
pg_ctl -D ./data/db_data/ -o "-p $PORT" -l ./data/db_data/logfile start

# Create user and tables
psql -h $PWD/data/db_data/sockets -p $PORT -d postgres -c "CREATE USER $BACKEND_USER_NAME WITH PASSWORD '$BACKEND_USER_PASSWORD';"
psql -h $PWD/data/db_data/sockets -p $PORT -d postgres -c "CREATE DATABASE $BACKEND_DB_NAME OWNER $BACKEND_USER_NAME;"

psql -h $PWD/data/db_data/sockets -p $PORT -d postgres -c "CREATE USER $FRONTEND_USER_NAME WITH PASSWORD '$FRONTEND_USER_PASSWORD';"
psql -h $PWD/data/db_data/sockets -p $PORT -d postgres -c "CREATE DATABASE $FRONTEND_DB_NAME OWNER $FRONTEND_USER_NAME;"
