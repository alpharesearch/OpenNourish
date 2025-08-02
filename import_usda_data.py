# import_usda_data.py (Final Version - Aligned with the Full Schema)

import sqlite3
import csv
import os
import sys
import time
import string
import re

def intelligent_capwords(s):
    if not s:
        return s
    # Capitalize words, respecting parentheses.
    return re.sub(r"[A-Za-z]+('[A-Za-z]+)?", lambda mo: mo.group(0).capitalize(), s)

def import_usda_data(db_file=None, keep_newest_upc_only=False):
    """
    Creates and populates the SQLite database from USDA CSV files.
    This script is idempotent: it deletes the old database on every run.
    This version is optimized to reduce memory usage.
    """
    if db_file is None:
        db_file = 'persistent/usda_data.db'
    usda_data_dir = 'persistent/usda_data'
    schema_file = 'schema_usda.sql'
    CHUNK_SIZE = 50000

    if os.path.exists(db_file):
        print(f"Removing existing database: {db_file}")
        retries = 5
        delay = 0.5
        for i in range(retries):
            try:
                os.remove(db_file)
                break
            except PermissionError:
                if i < retries - 1:
                    print(f"PermissionError: Could not remove DB. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    raise # Re-raise if all retries fail

    try:
        with sqlite3.connect(db_file) as conn:
            print(f"Creating new database: {db_file}")
            cursor = conn.cursor()

            with open(schema_file, 'r') as f:
                cursor.executescript(f.read())
            print("Schema created successfully.")

            print("Creating index for faster inserts...")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_food_nutrients_unique ON food_nutrients (fdc_id, nutrient_id)")
            print("Index created.")

            # --- DATA POPULATION ---

            print("\nPopulating 'nutrients' table...")
            with open(os.path.join(usda_data_dir, 'nutrient.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader) # Skip header
                chunk = []
                count = 0
                for row in reader:
                    chunk.append((row[0], row[1], row[2]))
                    if len(chunk) >= CHUNK_SIZE:
                        cursor.executemany("INSERT INTO nutrients (id, name, unit_name) VALUES (?, ?, ?)", chunk)
                        count += len(chunk)
                        chunk = []
                if chunk:
                    cursor.executemany("INSERT INTO nutrients (id, name, unit_name) VALUES (?, ?, ?)", chunk)
                    count += len(chunk)
                print(f"-> Imported {count} nutrients.")

            print("\nPreparing 'foods' data (this may take a while)...")
            foods_with_energy = set()
            energy_nutrient_ids = {'1008', '2047'} # Energy (KCAL) and Energy (Atwater General Factors) (KCAL)

            # First pass: Identify foods with non-zero energy values
            print("-> Identifying foods with energy values...")
            with open(os.path.join(usda_data_dir, 'food_nutrient.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader) # Skip header
                for row in reader:
                    fdc_id = row[1]
                    nutrient_id = row[2]
                    amount = float(row[3])
                    if nutrient_id in energy_nutrient_ids and amount > 0:
                        foods_with_energy.add(fdc_id)
            print(f"-> Found {len(foods_with_energy)} foods with energy.")

            # --- Load data from specific food type CSVs into dictionaries ---
            print("-> Processing branded foods data...")
            branded_foods_data = {}
            if keep_newest_upc_only:
                upc_to_best_fdc_info = {} # Stores gtin_upc -> (fdc_id, ingredients, available_date)
                duplicate_upcs = 0
                with open(os.path.join(usda_data_dir, 'branded_food.csv'), 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader)
                    for row in reader:
                        fdc_id, gtin_upc, ingredients, available_date = row[0], row[4] or None, row[5] or None, row[14] or '1900-01-01'
                        if gtin_upc:
                            if gtin_upc in upc_to_best_fdc_info:
                                duplicate_upcs += 1
                                if available_date > upc_to_best_fdc_info[gtin_upc][2]:
                                    upc_to_best_fdc_info[gtin_upc] = (fdc_id, ingredients, available_date)
                            else:
                                upc_to_best_fdc_info[gtin_upc] = (fdc_id, ingredients, available_date)
                        else:
                            branded_foods_data[fdc_id] = (gtin_upc, ingredients)
                
                for gtin_upc, (fdc_id, ingredients, date) in upc_to_best_fdc_info.items():
                    branded_foods_data[fdc_id] = (gtin_upc, ingredients)
                print(f"-> Found {duplicate_upcs} duplicate UPCs. Keeping the most recent for each.")
            else:
                with open(os.path.join(usda_data_dir, 'branded_food.csv'), 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader)
                    for row in reader:
                        fdc_id, gtin_upc, ingredients = row[0], row[4] or None, row[5] or None
                        branded_foods_data[fdc_id] = (gtin_upc, ingredients)
                print("-> Including all branded foods.")

            print("-> Processing sr_legacy_food data...")
            sr_legacy_foods_data = {}
            with open(os.path.join(usda_data_dir, 'sr_legacy_food.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    fdc_id = row[0]
                    sr_legacy_foods_data[fdc_id] = () # No extra columns for now

            print("-> Processing survey_fndds_food data...")
            survey_foods_data = {}
            with open(os.path.join(usda_data_dir, 'survey_fndds_food.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    fdc_id = row[0]
                    survey_foods_data[fdc_id] = () # No extra columns for now

            print("\nPopulating 'foods' table...")
            foods_to_insert_chunk = []
            count = 0
            with open(os.path.join(usda_data_dir, 'food.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader) # Skip header
                for row in reader:
                    fdc_id, data_type, description, food_category_id = row[0], row[1], row[2], row[3] or None
                    
                    if fdc_id in foods_with_energy:
                        upc, ingredients = None, None
                        
                        if data_type == 'branded_food':
                            upc, ingredients = branded_foods_data.get(fdc_id, (None, None))
                        elif data_type == 'sr_legacy_food':
                            # No extra data to pull for sr_legacy_food yet
                            pass
                        elif data_type == 'survey_fndds_food':
                            # No extra data to pull for survey_fndds_food yet
                            pass

                        # Capitalize the description here
                        formatted_description = intelligent_capwords(description)
                        # Capitalize ingredients if they exist
                        formatted_ingredients = intelligent_capwords(ingredients) if ingredients else None

                        foods_to_insert_chunk.append((fdc_id, formatted_description, data_type, food_category_id, upc, formatted_ingredients))
                        
                        if len(foods_to_insert_chunk) >= CHUNK_SIZE:
                            cursor.executemany(
                                "INSERT INTO foods (fdc_id, description, data_type, food_category_id, upc, ingredients) VALUES (?, ?, ?, ?, ?, ?)",
                                foods_to_insert_chunk
                            )
                            count += len(foods_to_insert_chunk)
                            foods_to_insert_chunk = []

            if foods_to_insert_chunk:
                cursor.executemany(
                    "INSERT INTO foods (fdc_id, description, data_type, food_category_id, upc, ingredients) VALUES (?, ?, ?, ?, ?, ?)",
                    foods_to_insert_chunk
                )
                count += len(foods_to_insert_chunk)
            print(f"-> Imported {count} foods.")

            print("\nPopulating 'food_nutrients' table...")
            to_insert_chunk = []
            processed_count = 0
            cursor.execute("SELECT COUNT(*) FROM food_nutrients")
            initial_count = cursor.fetchone()[0]

            with open(os.path.join(usda_data_dir, 'food_nutrient.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    fdc_id = row[1]
                    nutrient_id = row[2]
                    amount = float(row[3])

                    if fdc_id in foods_with_energy and amount > 0:
                        processed_count += 1
                        to_insert_chunk.append((fdc_id, nutrient_id, amount))
                        if len(to_insert_chunk) >= CHUNK_SIZE:
                            cursor.executemany("INSERT OR IGNORE INTO food_nutrients (fdc_id, nutrient_id, amount) VALUES (?, ?, ?)", to_insert_chunk)
                            to_insert_chunk = []
            if to_insert_chunk:
                cursor.executemany("INSERT OR IGNORE INTO food_nutrients (fdc_id, nutrient_id, amount) VALUES (?, ?, ?)", to_insert_chunk)

            cursor.execute("SELECT COUNT(*) FROM food_nutrients")
            final_count = cursor.fetchone()[0]
            inserted_count = final_count - initial_count
            skipped_count = processed_count - inserted_count

            print(f"-> Imported {inserted_count} unique food nutrients.")
            print(f"-> Skipped {skipped_count} duplicate entries.")

            

        print("\n--- Import successful. Database is ready. ---")
        conn.close()

    except (sqlite3.Error, IOError, csv.Error) as e:
        print(f"\n--- An error occurred during database import: {e} ---", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Import USDA FoodData Central data into an SQLite database.")
    parser.add_argument(
        '--db_file', 
        type=str, 
        default='persistent/usda_data.db', 
        help='Path to the SQLite database file.'
    )
    parser.add_argument(
        '--keep_newest_upc_only', 
        action='store_true', 
        help='If set, only the newest food entry for a given UPC will be kept.'
    )

    args = parser.parse_args()

    import_usda_data(db_file=args.db_file, keep_newest_upc_only=args.keep_newest_upc_only)