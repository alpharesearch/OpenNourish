#!/bin/sh
set -e

# --- Configuration ---
# This is the static location where Nginx will ALWAYS look for certs.
CERT_DIR="/etc/nginx/certs"
CERT_FILE="${CERT_DIR}/fullchain.pem"
KEY_FILE="${CERT_DIR}/privkey.pem"

# Create the directory if it doesn't exist
mkdir -p "$CERT_DIR"

# --- Logic ---
# Check if the user has provided paths to real certificates via environment variables
# and if those files actually exist.
if [ -n "$REAL_CERT_PATH" ] && [ -n "$REAL_KEY_PATH" ] && [ -f "$REAL_CERT_PATH" ] && [ -f "$REAL_KEY_PATH" ]; then
  echo "--> Found real certificates at specified paths. Creating symbolic links."
  # Create symbolic links from the real certs to the location Nginx expects.
  # This avoids copying the files and keeps the setup clean.
  ln -sf "$REAL_CERT_PATH" "$CERT_FILE"
  ln -sf "$REAL_KEY_PATH" "$KEY_FILE"
  echo "--> Links created."

# If real certs aren't provided, fall back to self-signed certs.
else
  # Only generate self-signed certs if they don't already exist.
  if [ ! -f "$CERT_FILE" ]; then
    echo "--> Real certificates not found. Generating self-signed certificates."
    # Generate the self-signed certs directly into the location Nginx expects.
    openssl req -x509 -newkey rsa:4096 -nodes \
            -out "$CERT_FILE" \
            -keyout "$KEY_FILE" \
            -days 365 \
            -subj "/CN=opennourish-selfsigned"
    echo "--> Self-signed certs generated."
  else
    echo "--> Using existing self-signed certificates."
  fi
fi

# --- Start Nginx ---
# This is a critical step. `exec "$@"` passes control to the main command
# defined in the Docker image (i.e., it starts Nginx).
exec "$@"