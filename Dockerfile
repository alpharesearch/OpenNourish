# Stage 1: Build Stage
FROM python:3.9 AS build

WORKDIR /app

# Create a virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final Stage
FROM python:3.9-slim

WORKDIR /app

# Copy virtual environment from build stage
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY opennourish/ opennourish/
COPY models.py .
COPY config.py .
COPY serve.py .
COPY alembic.ini .
COPY migrations/ migrations/
COPY schema_usda.sql .
COPY schema_user.sql .
COPY import_usda_data.py .
COPY pytest.ini .
COPY templates/ templates/
COPY static/ static/

# Expose the port Flask will run on
EXPOSE 8081

# Command to run the application
CMD ["python", "-u", "serve.py"]
