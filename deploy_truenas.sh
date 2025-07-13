#!/bin/bash

# This script automates the process of building, tagging, and pushing
# OpenNourish Docker images to a private TrueNAS SCALE Docker registry.
# It also generates the TrueNAS Custom App YAML configuration.

# IMPORTANT: Before running this script:
# 1. Ensure you have Docker and Docker Compose installed on your development machine.
# 2. Configure your Docker daemon to trust your TrueNAS registry (see DEV-README.md for details).
# 3. Set the following variables in your .env file:
#    - TRUENAS_REGISTRY_URL (REQUIRED: e.g., your-truenas-ip:5000)
#    - SECRET_KEY (REQUIRED: your Flask application secret key)
#    - TRUENAS_APP_PATH (REQUIRED: The base path on your TrueNAS server for app data, e.g., /mnt/data-pool/opennourish)
#    - SEED_DEV_DATA (OPTIONAL: true/false, defaults to false if not set)
#    - REAL_CERT_PATH (OPTIONAL: for Nginx SSL, e.g., /etc/certificates/LEProduction.crt)
#    - REAL_KEY_PATH (OPTIONAL: for Nginx SSL, e.g., /etc/certificates/LEProduction.key)

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Validate required environment variables
if [ -z "$TRUENAS_REGISTRY_URL" ]; then
    echo "Error: TRUENAS_REGISTRY_URL is not set in your .env file or environment."
    echo "Please add TRUENAS_REGISTRY_URL=\"your-truenas-ip:port\" to your .env file."
    exit 1
fi

if [ -z "$SECRET_KEY" ]; then
    echo "Error: SECRET_KEY is not set in your .env file or environment."
    echo "Please add SECRET_KEY=\"your_flask_secret_key\" to your .env file."
    exit 1
fi

# Use provided TRUENAS_APP_PATH or default to /mnt/data-pool/opennourish if not set
TRUENAS_APP_PATH_VAR=${TRUENAS_APP_PATH:-/mnt/data-pool/opennourish}

# Validate TRUENAS_APP_PATH after defaulting
if [ -z "$TRUENAS_APP_PATH_VAR" ]; then
    echo "Error: TRUENAS_APP_PATH is not set and no default could be applied."
    echo "Please add TRUENAS_APP_PATH=\"your_truenas_app_path\" to your .env file."
    exit 1
fi

# Use provided cert paths or default to empty strings if not set
REAL_CERT_PATH_VAR=${REAL_CERT_PATH:-}
REAL_KEY_PATH_VAR=${REAL_KEY_PATH:-}

# Use provided SEED_DEV_DATA or default to false if not set
SEED_DEV_DATA_VAR=${SEED_DEV_DATA:-false}

REGISTRY_URL="$TRUENAS_REGISTRY_URL"

echo "--- Building Docker images using standard docker-compose.yml ---"
docker compose build

if [ $? -ne 0 ]; then
    echo "Docker image build failed. Exiting."
    exit 1
fi

echo "--- Tagging images for private registry: ${REGISTRY_URL} ---"
docker tag opennourish-app:latest ${REGISTRY_URL}/opennourish-app:latest
docker tag opennourish-nginx:latest ${REGISTRY_URL}/opennourish-nginx:latest

echo "--- Pushing images to private registry: ${REGISTRY_URL} ---"
docker push ${REGISTRY_URL}/opennourish-app:latest
docker push ${REGISTRY_URL}/opennourish-nginx:latest

if [ $? -ne 0 ]; then
    echo "Docker image push failed. Ensure your registry URL is correct and your Docker daemon trusts the registry."
    exit 1
fi

# Construct the Nginx environment block conditionally
NGINX_ENV_BLOCK=""
if [ -n "$REAL_CERT_PATH_VAR" ] || [ -n "$REAL_KEY_PATH_VAR" ]; then
  NGINX_ENV_BLOCK="    environment:
      REAL_CERT_PATH: ${REAL_CERT_PATH_VAR}
      REAL_KEY_PATH: ${REAL_KEY_PATH_VAR}"
fi

echo -e "\n--- Images successfully built, tagged, and pushed to ${REGISTRY_URL} ---"
echo -e "\n--- TrueNAS Custom App YAML Configuration (Copy and Paste into TrueNAS UI) ---"
cat <<EOF
services:
  opennourish-app:
    image: ${REGISTRY_URL}/opennourish-app:latest
    restart: unless-stopped
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - SEED_DEV_DATA=${SEED_DEV_DATA_VAR}
    volumes:
      - ${TRUENAS_APP_PATH_VAR}:/app/persistent

  nginx:
    image: ${REGISTRY_URL}/opennourish-nginx:latest
    restart: unless-stopped
    ports:
      - "18080:80"
      - "18443:443"
${NGINX_ENV_BLOCK}
    volumes:
      - /etc/certificates:/etc/certificates:ro
      - ${TRUENAS_APP_PATH_VAR}/nginx_certs:/etc/nginx/certs
    depends_on:
      - opennourish-app
EOF

echo -e "\n--- IMPORTANT: Remember to adjust volume paths in the YAML to match your TrueNAS storage. ---"