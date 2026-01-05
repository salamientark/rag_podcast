 #!/bin/bash
set -euo pipefail
 
# Check if .env exists
if [ ! -f .env ]; then
  echo "Error: .env file not found"
  exit 1
fi

# Load env file
source .env

# Create data directory for PostgreSQL
if [ ! -d ./data/db_data ]; then
  initdb -D ./data/db_data/
fi
mkdir -p ./data/db_data/sockets
sed -i "/^#unix_socket_directories.*/c\\unix_socket_directories = '$PWD/data/db_data/sockets'" data/db_data/postgresql.conf
 
# Start PostgreSQL server
pg_ctl -D ./data/db_data/ -o "-p $POSTGRES_PORT" -l ./data/db_data/logfile start
pg_ctl -D ./data/db_data/ -o "-p ${POSTGRES_PORT}" -l ./data/db_data/logfile start
 
# Create user and tables
# Use PGPASSWORD to avoid exposing passwords in command line
psql -h "$PWD/data/db_data/sockets" -p "${POSTGRES_PORT}" -d postgres -c "CREATE USER \"${BACKEND_USER_NAME}\" WITH PASSWORD '${BACKEND_USER_PASSWORD}';" || echo "Backend user may already exist"
psql -h "$PWD/data/db_data/sockets" -p "${POSTGRES_PORT}" -d postgres -c "CREATE DATABASE \"${BACKEND_DB_NAME}\" OWNER \"${BACKEND_USER_NAME}\";" || echo "Backend database may already exist"
 
psql -h "$PWD/data/db_data/sockets" -p "${POSTGRES_PORT}" -d postgres -c "CREATE USER \"${FRONTEND_USER_NAME}\" WITH PASSWORD '${FRONTEND_USER_PASSWORD}';" || echo "Frontend user may already exist"
psql -h "$PWD/data/db_data/sockets" -p "${POSTGRES_PORT}" -d postgres -c "CREATE DATABASE \"${FRONTEND_DB_NAME}\" OWNER \"${FRONTEND_USER_NAME}\";" || echo "Frontend database may already exist"
