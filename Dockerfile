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

# Install font dependencies and Typst
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    fontconfig \
    fonts-liberation \
    xz-utils \
    dos2unix \
    openssl \
    tesseract-ocr \
    --no-install-recommends && \
    wget https://github.com/typst/typst/releases/download/v0.13.1/typst-x86_64-unknown-linux-musl.tar.xz && \
    tar -xf typst-x86_64-unknown-linux-musl.tar.xz && \
    mkdir -p /usr/local/bin/typst && \
    mv typst-x86_64-unknown-linux-musl/* /usr/local/bin/typst/ && \
    rm typst-x86_64-unknown-linux-musl.tar.xz && \
    rmdir typst-x86_64-unknown-linux-musl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment from build stage
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the entire application context, respecting .dockerignore
COPY . .

# Set the FLASK_APP environment variable
ENV FLASK_APP=app.py

# Add Typst to the PATH
ENV PATH="/usr/local/bin/typst:$PATH"

# Expose the port Flask will run on
EXPOSE 8081

# Copy and set up the entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN dos2unix /app/entrypoint.sh /app/safe_upgrade.sh && chmod +x /app/entrypoint.sh /app/safe_upgrade.sh
ENTRYPOINT ["/app/entrypoint.sh"]

# Command to run the application
CMD ["python", "-u", "serve.py"]
