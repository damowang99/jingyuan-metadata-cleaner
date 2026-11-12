FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 PORT=8787 DATABASE=/data/cleaner.sqlite3
WORKDIR /app
RUN groupadd --gid 10001 cleaner && useradd --uid 10001 --gid 10001 --no-create-home cleaner \
    && mkdir -p /data /backups && chown cleaner:cleaner /data /backups
COPY --chown=10001:10001 server.py device_auth.py fleet.py file_records.py scan_inventory.py manage.py healthcheck.py release_api.py ./
COPY --chown=10001:10001 web/ ./web/
USER 10001:10001
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["python", "healthcheck.py"]
CMD ["python", "server.py"]
