FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

EXPOSE $PORT

CMD python web_main.py --host 0.0.0.0 --port $PORT
