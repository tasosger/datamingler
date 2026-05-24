#!/bin/sh
set -e

NEO4J_URI="${NEO4J_URI:-bolt://neo4j:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-12345678}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

echo "Waiting for Neo4j at $NEO4J_URI ..."
until datamingler load-neo4j examples/sample.dvm.xml \
      --uri "$NEO4J_URI" --user "$NEO4J_USER" --password "$NEO4J_PASSWORD" \
      --reset 2>/dev/null; do
  sleep 4
done
echo "Neo4j ready — starting server"

exec datamingler serve examples/datasources.xml \
  --neo4j-uri      "$NEO4J_URI" \
  --neo4j-user     "$NEO4J_USER" \
  --neo4j-password "$NEO4J_PASSWORD" \
  --redis-host     "$REDIS_HOST" \
  --redis-port     "$REDIS_PORT" \
  --host 0.0.0.0 \
  --port 8080
