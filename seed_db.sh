#!/bin/bash

# This script automates the process of updating migrations and seeding the user database.
# It applies any pending migrations and then populates it with development data,
# preserving existing database structure and non-user data.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Starting user_data.db reset procedure (preserving migrations) ---"

# 1. Delete existing user_data.db
if [ -f user_data.db ]; then
    echo "Deleting existing user_data.db..."
    rm user_data.db
else
    echo "user_data.db not found, skipping deletion."
fi

echo "--- user_data.db reset complete! ---"

# 1. Apply any pending migrations
echo "Applying any pending database migrations..."
flask db upgrade


echo "Seeding usda portion data..."
flask seed-usda-portions

echo "--- Seeding default exercise activities... ---"
flask seed-exercise-activities

echo "--- Seeding development data ---"
flask seed-dev-data

echo "--- Database update and seeding complete! ---"