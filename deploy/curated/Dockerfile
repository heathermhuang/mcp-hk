FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock pyproject.toml README.md LICENSE ./
RUN pip install --no-cache-dir -r requirements.lock
COPY src ./src
RUN pip install --no-cache-dir --no-deps . && pip install --no-cache-dir 'psycopg[binary]==3.2.13'
USER 65532:65532
EXPOSE 8081
CMD ["mcp-hk-curated-backend"]
