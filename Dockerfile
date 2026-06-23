FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml setup.py ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY config ./config
COPY knowledge ./knowledge
COPY docs ./docs
COPY README.md MAINTENANCE.md ./

RUN mkdir -p data/reports data/hotspots data/generated_images

CMD ["python", "-m", "xhs_agent", "run"]
