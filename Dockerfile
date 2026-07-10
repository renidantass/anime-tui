FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir --user -e .

FROM python:3.11-slim
RUN useradd --create-home --shell /bin/bash app
WORKDIR /app
COPY --from=builder /root/.local /home/app/.local
COPY . .
RUN chown -R app:app /home/app /app
USER app
ENV PATH="/home/app/.local/bin:${PATH}"
ENV PORT=8765
EXPOSE $PORT
CMD python web_main.py --host 0.0.0.0 --port $PORT
