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
#    - TRUENAS_REAL_CERT_PATH (OPTIONAL: for Nginx SSL, e.g., /etc/certificates/LEProduction.crt)
#    - TRUENAS_REAL_KEY_PATH (OPTIONAL: for Nginx SSL, e.g., /etc/certificates/LEProduction.key)

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

if [ -z "$ENCRYPTION_KEY" ]; then
    echo "Error: ENCRYPTION_KEY is not set in your .env file or environment."
    echo "Please add ENCRYPTION_KEY=\"your_encryption_secret_key\" to your .env file."
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

# Use provided cert paths or default to empty strings if not set, in this case private certificates will be generated.
REAL_CERT_PATH_VAR=${TRUENAS_REAL_CERT_PATH:-}
REAL_KEY_PATH_VAR=${TRUENAS_REAL_KEY_PATH:-}

# Use provided SEED_DEV_DATA or default to false if not set
SEED_DEV_DATA_VAR=${SEED_DEV_DATA:-false}

REGISTRY_URL="$TRUENAS_REGISTRY_URL"

echo -e "\n--- Building Docker images using standard docker-compose.yml ---"

# Stamp provenance before the build so it lands in the image labels, /app/BUILD_INFO and the boot
# banner. This script otherwise tags every build in history as the same constant V1.0.0 and hands
# TrueNAS a mutable :latest, which is why a deployed container could not be identified afterwards.
GIT_SHA=$(git rev-parse --short=12 HEAD 2>/dev/null || echo "unknown")
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    GIT_SHA="${GIT_SHA}-dirty"
fi
export OPENNOURISH_VCS_REF="$GIT_SHA"
export OPENNOURISH_BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Stamping build ${OPENNOURISH_VCS_REF} at ${OPENNOURISH_BUILD_DATE}"

docker compose build

if [ $? -ne 0 ]; then
    echo "Docker image build failed. Exiting."
    exit 1
fi

IMAGE_VERSION="V1.0.0"
echo -e "\n--- Tagging ${IMAGE_VERSION} images for private registry: ${REGISTRY_URL} ---"
docker tag opennourish-opennourish-app:latest ${REGISTRY_URL}/opennourish-app:latest
docker tag opennourish-opennourish-app:latest opennourish-opennourish-app:${IMAGE_VERSION}
docker tag opennourish-opennourish-app:${IMAGE_VERSION} ${REGISTRY_URL}/opennourish-app:${IMAGE_VERSION}
docker tag opennourish-nginx:latest ${REGISTRY_URL}/opennourish-nginx:latest
docker tag opennourish-nginx:latest opennourish-nginx:${IMAGE_VERSION}
docker tag opennourish-nginx:${IMAGE_VERSION} ${REGISTRY_URL}/opennourish-nginx:${IMAGE_VERSION}

echo -e "\n--- Pushing images to private registry: ${REGISTRY_URL} ---"
PUSH_FAILED=0
for IMAGE in opennourish-app opennourish-nginx; do
    for TAG in latest "${IMAGE_VERSION}"; do
        if ! docker push "${REGISTRY_URL}/${IMAGE}:${TAG}"; then
            echo "Error: push of ${REGISTRY_URL}/${IMAGE}:${TAG} failed." >&2
            PUSH_FAILED=1
        fi
    done
done

docker logout ${REGISTRY_URL} || true

# This check used to sit after `docker logout` and therefore read logout's exit code, so a failed
# push still printed "successfully built, tagged, and pushed" and emitted the TrueNAS YAML.
if [ "$PUSH_FAILED" -ne 0 ]; then
    echo -e "\nDocker image push failed. Ensure your registry URL is correct and your Docker daemon trusts the registry." >&2
    echo "The registry may still be serving the previous build, so do not redeploy from the YAML below." >&2
    exit 1
fi

# Construct the Nginx environment block conditionally
NGINX_ENV_BLOCK=""
if [ -n "$REAL_CERT_PATH_VAR" ] || [ -n "$REAL_KEY_PATH_VAR" ]; then
  NGINX_ENV_BLOCK="    environment:
      REAL_CERT_PATH: ${REAL_CERT_PATH_VAR}
      REAL_KEY_PATH: ${REAL_KEY_PATH_VAR}"
fi

APP_ENV_BLOCK=""

# Helper function to add an environment variable if it exists
add_env_var() {
  local key=$1
  local value=$2
  if [ -n "$value" ]; then
    APP_ENV_BLOCK+=$"      - ${key}=${value}"
    APP_ENV_BLOCK+=$'\n'
  fi
}

add_env_var "SECRET_KEY" "$SECRET_KEY"
add_env_var "ENCRYPTION_KEY" "$ENCRYPTION_KEY"
add_env_var "FLASK_DEBUG" "$FLASK_DEBUG"
add_env_var "SEED_DEV_DATA" "$SEED_DEV_DATA_VAR"
add_env_var "ENABLE_PASSWORD_RESET" "$ENABLE_PASSWORD_RESET"
add_env_var "ENABLE_EMAIL_VERIFICATION" "$ENABLE_EMAIL_VERIFICATION"
add_env_var "MAIL_CONFIG_SOURCE" "$MAIL_CONFIG_SOURCE"
add_env_var "MAIL_SERVER" "$MAIL_SERVER"
add_env_var "MAIL_PORT" "$MAIL_PORT"
add_env_var "MAIL_USE_TLS" "$MAIL_USE_TLS"
add_env_var "MAIL_USE_SSL" "$MAIL_USE_SSL"
add_env_var "MAIL_USERNAME" "$MAIL_USERNAME"
add_env_var "MAIL_PASSWORD" "$MAIL_PASSWORD"
add_env_var "MAIL_FROM" "$MAIL_FROM"
add_env_var "MAIL_SUPPRESS_SEND" "$MAIL_SUPPRESS_SEND"


echo -e "\n--- Images successfully built, tagged, and pushed to ${REGISTRY_URL} ---"
echo -e "\n--- TrueNAS Custom App YAML Configuration (Copy and Paste into TrueNAS UI) ---"
cat <<EOF
services:
  opennourish-app:
    image: ${REGISTRY_URL}/opennourish-app:latest
    restart: unless-stopped
    environment:
${APP_ENV_BLOCK}    volumes:
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
