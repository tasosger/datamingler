#!/bin/sh
set -e

NEO4J_URI="${NEO4J_URI:-bolt://neo4j:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-12345678}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
PROJECTS_DIR="${DATAMINGLER_PROJECTS_DIR:-/app/projects}"
DEFAULT_PROJECT_ID="${DATAMINGLER_DEFAULT_PROJECT_ID:-default}"

echo "Waiting for Neo4j at $NEO4J_URI ..."
until datamingler save-neo4j --output /tmp/current.dvm.xml \
      --uri "$NEO4J_URI" --user "$NEO4J_USER" --password "$NEO4J_PASSWORD" \
      --project-id "$DEFAULT_PROJECT_ID" 2>/dev/null; do
  sleep 4
done

if grep -q "<edge>" /tmp/current.dvm.xml; then
  echo "Default project '$DEFAULT_PROJECT_ID' already has graph data"
else
  datamingler load-neo4j examples/sample.dvm.xml \
    --uri "$NEO4J_URI" --user "$NEO4J_USER" --password "$NEO4J_PASSWORD" \
    --project-id "$DEFAULT_PROJECT_ID" --reset
fi

echo "Neo4j ready - starting server"

exec datamingler serve examples/datasources.xml \
  --neo4j-uri "$NEO4J_URI" \
  --neo4j-user "$NEO4J_USER" \
  --neo4j-password "$NEO4J_PASSWORD" \
  --redis-host "$REDIS_HOST" \
  --redis-port "$REDIS_PORT" \
  --projects-dir "$PROJECTS_DIR" \
  --default-project-id "$DEFAULT_PROJECT_ID" \
  --host 0.0.0.0 \
  --port 8080
