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

# Install font dependencies for Typst
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    fontconfig \
    fonts-liberation \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment from build stage
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY opennourish/ opennourish/
COPY models.py .
COPY config.py .
COPY app.py .
COPY serve.py .
COPY alembic.ini .
COPY migrations/ migrations/
COPY schema_usda.sql .
COPY import_usda_data.py .
COPY pytest.ini .
COPY templates/ templates/
COPY static/ static/

# Set the FLASK_APP environment variable
ENV FLASK_APP=app.py

# Copy Typst binary and associated files
COPY typst/ /usr/local/bin/typst/
ENV PATH="/usr/local/bin/typst:$PATH"

# Expose the port Flask will run on
EXPOSE 8081

# Copy and set up the entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]

# Command to run the application
CMD ["python", "-u", "serve.py"]
