#!/bin/bash
set -e

# Define a single root for all persistent data
PERSISTENT_DIR="/app/persistent"
mkdir -p "$PERSISTENT_DIR"

# Step 0: Generate self-signed certificates if not found
CERT_DIR="$PERSISTENT_DIR/certs"
if [ ! -f "$CERT_DIR/fullchain.pem" ] || [ ! -f "$CERT_DIR/privkey.pem" ]; then
  echo "--- Generating self-signed certificates... ---"
  mkdir -p "$CERT_DIR"
  openssl req -x509 -newkey rsa:4096 -nodes -out "$CERT_DIR/fullchain.pem" -keyout "$CERT_DIR/privkey.pem" -days 365 -subj "/CN=localhost"
  echo "--- Certificates generated. ---"
else
  echo "--- Certificates found. Skipping generation. ---"
fi

# Paths for data now live within the persistent directory
USDA_DB_PATH="$PERSISTENT_DIR/usda_data.db"
USDA_CSV_DIR="$PERSISTENT_DIR/usda_data"
MEASURE_UNIT_CSV_PATH="$USDA_CSV_DIR/measure_unit.csv"

# Step 1: Ensure USDA CSV directory exists and download if files are missing
mkdir -p "$USDA_CSV_DIR"
if [ ! -f "$MEASURE_UNIT_CSV_PATH" ]; then
    echo "--- USDA CSV files not found. Downloading and extracting... ---"
    
    URL="https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_csv_2025-04-24.zip"
    ZIP_FILE="$USDA_CSV_DIR/usda_data.zip"
    
    echo "--- Downloading USDA dataset... ---"
    wget -O "$ZIP_FILE" "$URL"
    
    echo "--- Unzipping dataset into $USDA_CSV_DIR... ---"
    unzip -o "$ZIP_FILE" -d "$USDA_CSV_DIR"
    
    SUBDIR=$(find "$USDA_CSV_DIR" -maxdepth 1 -type d -name "FoodData_Central_csv_*" -print | head -n 1)
    if [ -d "$SUBDIR" ]; then
        echo "--- Moving CSV files from $SUBDIR... ---"
        mv "$SUBDIR"/*.csv "$USDA_CSV_DIR/"
        rm -r "$SUBDIR"
    fi
    
    rm "$ZIP_FILE"
else
    echo "--- USDA CSV files found. Skipping download. ---"
fi

# Step 2: Build the USDA database from the CSVs only if it doesn't exist
if [ ! -f "$USDA_DB_PATH" ]; then
    echo "--- USDA database not found. Building from CSV files... ---"
    python import_usda_data.py --db_file "$USDA_DB_PATH" # Pass the correct path
    echo "--- USDA database build complete. ---"
else
    echo "--- USDA database found. Skipping build. ---"
fi

# Step 3: Always run user database migrations and seeding
echo "--- Applying database migrations... ---"
flask db upgrade

echo "--- Seeding USDA portions... ---"
flask seed-usda-portions

echo "--- Seeding default exercise activities... ---"
flask seed-exercise-activities

echo "--- Seeding development data (first time only)... ---"
flask seed-dev-data

# Step 4: Execute the main command
echo "--- Starting application... ---"
exec "$@"

