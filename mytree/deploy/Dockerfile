FROM python:3.12-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000 MYTREE_PROFILE=/data/profiles.json MYTREE_USAGE_LOG=/data/model-usage.jsonl MYTREE_REQUIRE_AUTH=1 MYTREE_AUTH_MODE=email MYTREE_AUTH_DB=/data/auth.sqlite3
WORKDIR /opt/mytree
COPY mytree/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r requirements.txt && useradd --uid 10001 --create-home appuser && mkdir -p /data && chown appuser /data
COPY mytree/app ./app
COPY mytree/web ./web
COPY docs/architecture/agent-contract.schema.json /opt/docs/architecture/agent-contract.schema.json
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=4s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/_ready',timeout=3)"
CMD ["python","-m","app.server"]
