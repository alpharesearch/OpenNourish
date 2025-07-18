#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Starting USDA Data and Portions Seeding Process ---"

# Clean up previous database and migrations for a fresh start
echo "\n--- Cleaning up previous database and migrations ---"
rm -f persistent/user_data.db
rm -f .dev_data_seeded
rm -rf migrations/
rm -rf instance/

# Step 1: Import USDA data into usda_data.db
echo "\n--- Running import_usda_data.py to create usda_data.db ---"
python import_usda_data.py

# Step 2: Initialize Flask-Migrate if not already initialized
# Check if the migrations directory exists
if [ ! -d "migrations" ]; then
    echo "\n--- Initializing Flask-Migrate ---"
    flask db init
else
    echo "\n--- Flask-Migrate already initialized. Skipping 'flask db init'. ---"
fi

# Step 3: Generate a migration for the unified portions table
echo "\n--- Generating migration for UnifiedPortion table ---"
flask db migrate -m "Unified portions table"

# Step 4: Apply database migrations
echo "\n--- Applying database migrations ---"
flask db upgrade

# Step 5: Seed USDA portions into the user database
echo "\n--- Seeding USDA portions into user_data.db ---"
flask seed-usda-portions

# Step 6: Seed USDA categories into the user database
echo "\n--- Seeding USDA categories into user_data.db ---"
flask seed-usda-categories

echo "--- Seeding default exercise activities... ---"
flask seed-exercise-activities

echo "--- Seeding development data (first time only)... ---"
flask seed-dev-data
   
echo "\n--- USDA Data and Portions Seeding Process Complete! ---"