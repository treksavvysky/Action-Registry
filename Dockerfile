FROM python:3.12-slim as base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install --no-cache-dir "poetry==1.8.2"

COPY pyproject.toml poetry.lock* ./

# Install into system site-packages (not /app/.venv)
RUN poetry config virtualenvs.create false \
 && poetry install --no-root --only main

COPY app ./app

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]