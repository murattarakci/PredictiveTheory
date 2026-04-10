FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker/entrypoint.sh \
    && mkdir -p data db

ENV PYTHONUNBUFFERED=1

EXPOSE 8500

ENTRYPOINT ["./docker/entrypoint.sh"]
