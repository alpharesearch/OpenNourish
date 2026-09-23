# Stage 1: Build Stage
FROM python:3.12 AS build

WORKDIR /app

# Create a virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final Stage
# Must stay on the same Python minor as the build stage: /opt/venv is copied between them and is
# not portable across interpreter versions.
FROM python:3.12-slim

# Provenance. Nothing else in this image records which checkout it came from, and the tags carried
# to TrueNAS are not identity (`deploy_truenas.sh` applies a constant V1.0.0 plus :latest), so the
# git SHA and build date are stamped at build time into three places: these labels, /app/BUILD_INFO
# below, and the banner entrypoint.sh prints. `docker compose build` supplies them through the args
# in docker-compose.yml; a bare build leaves them "unknown". No release version is claimed here —
# `.version` is deliberately absent rather than mirroring the V1.0.0 tag, which is a constant.
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="OpenNourish" \
      org.opencontainers.image.description="Self-hosted multi-user food and nutrition tracker built on USDA FoodData Central" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/alpharesearch/OpenNourish" \
      org.opencontainers.image.url="https://github.com/alpharesearch/OpenNourish" \
      org.opencontainers.image.licenses="MIT"

# Install font dependencies and Typst
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    fontconfig \
    fonts-liberation \
    xz-utils \
    dos2unix \
    openssl \
    --no-install-recommends && \
    wget https://github.com/typst/typst/releases/download/v0.15.1/typst-x86_64-unknown-linux-musl.tar.xz && \
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

# Bake the same provenance into the filesystem, because `docker inspect` is unavailable from inside
# a TrueNAS custom app or a shell exec, while `cat /app/BUILD_INFO` always works. The requirements
# hash pins which lock is actually inside the image, and the live versions are re-checked at boot by
# entrypoint.sh.
RUN { \
      echo "revision=${VCS_REF}"; \
      echo "built=${BUILD_DATE}"; \
      echo "source=https://github.com/alpharesearch/OpenNourish"; \
      echo "python=$(python -V 2>&1)"; \
      echo "typst=$(typst --version | head -n1)"; \
      echo "requirements_sha256=$(sha256sum requirements.txt | cut -d' ' -f1)"; \
      echo "packages=$(pip freeze | wc -l)"; \
    } > /app/BUILD_INFO

# Expose the port Flask will run on
EXPOSE 8081

# Copy and set up the entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN dos2unix /app/entrypoint.sh /app/safe_upgrade.sh && chmod +x /app/entrypoint.sh /app/safe_upgrade.sh
ENTRYPOINT ["/app/entrypoint.sh"]

# Command to run the application
CMD ["python", "-u", "serve.py"]
