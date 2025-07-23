#!/bin/bash

# Exit immediately if any command fails
set -e

# --- Configuration ---
DB_FILE="persistent/user_data.db"
BACKUP_DIR="persistent/backups"

# --- Main Logic ---
echo "--- Starting Safe Database Upgrade Check ---"

# 1. Get the current revision from the database and the latest revision from the code.
# The 'awk' command is used to extract just the revision hash.
# The '|| true' prevents the script from exiting if 'flask db current' fails on a new, empty database.
CURRENT_REV=$(flask db current | awk '{print $1}' || true)
LATEST_REV=$(flask db heads | awk '{print $1}')

# 2. Compare the revisions to see if an upgrade is needed.
# This will be true if the DB is new (CURRENT_REV is empty) or if the revisions don't match.
if [ -z "$CURRENT_REV" ] || [ "$CURRENT_REV" != "$LATEST_REV" ]; then
    
    echo "-> Database is not up-to-date. A migration is required."
    echo "   Current DB revision: ${CURRENT_REV:-'None (New Database)'}"
    echo "   Latest code revision: $LATEST_REV"

    # 3a. Create the backup directory if it doesn't exist
    mkdir -p "$BACKUP_DIR"

    # 3b. Check if the database file exists before trying to back it up
    if [ -f "$DB_FILE" ]; then
        TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
        BACKUP_FILE="$BACKUP_DIR/$(basename "$DB_FILE").bak-$TIMESTAMP"
        
        echo "-> Backing up '$DB_FILE' to '$BACKUP_FILE'..."
        cp "$DB_FILE" "$BACKUP_FILE"
        echo "-> Backup complete."
    else
        echo "-> Database file '$DB_FILE' not found, skipping backup (first run)."
    fi

    # 3c. Run the actual flask db upgrade command
    echo "-> Applying migrations..."
    flask db upgrade

else
    echo "-> Database is already up-to-date at revision $CURRENT_REV. No backup or migration needed."
fi

echo "--- Safe Database Upgrade Check Complete! ---"