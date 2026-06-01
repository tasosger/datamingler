FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY datamingler/ datamingler/
COPY examples/ examples/

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -e ".[excel,neo4j]"

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint.sh"]
