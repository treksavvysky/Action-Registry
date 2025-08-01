# 1. Base image
FROM python:3.12-slim as base

# 2. Setup environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 3. Install Poetry
RUN pip install "poetry==1.8.2"

# 4. Copy dependency definitions
COPY pyproject.toml poetry.lock* ./

# 5. Install dependencies
RUN poetry install --no-root --no-dev

# 6. Copy application code
COPY action_registry ./action_registry

# 7. Expose port and define command
EXPOSE 8000
CMD ["uvicorn", "action_registry.main:app", "--host", "0.0.0.0", "--port", "8000"]
