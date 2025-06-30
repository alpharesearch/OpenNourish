# import_usda_data.py (Final Version - Aligned with the Full Schema)

import sqlite3
import csv
import os
import sys
import time

def import_usda_data(db_file=None):
    """
    Creates and populates the SQLite database from USDA CSV files.
    This script is idempotent: it deletes the old database on every run.
    """
    if db_file is None:
        db_file = 'usda_data.db'
    usda_data_dir = 'usda_data'
    schema_file = 'schema_usda.sql'

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

            # --- DATA POPULATION ---

            print("\nPopulating 'nutrients' table...")
            with open(os.path.join(usda_data_dir, 'nutrient.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)
                data = [(row[0], row[1], row[2]) for row in reader]
                cursor.executemany("INSERT INTO nutrients (id, name, unit_name) VALUES (?, ?, ?)", data)
                print(f"-> Imported {len(data)} nutrients.")

            print("\nPopulating 'measure_units' table...")
            with open(os.path.join(usda_data_dir, 'measure_unit.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)
                data = [(row[0], row[1]) for row in reader]
                cursor.executemany("INSERT INTO measure_units (id, name) VALUES (?, ?)", data)
                print(f"-> Imported {len(data)} measure units.")

            print("\nPopulating 'foods' table...")
            foods_with_energy = set()
            energy_nutrient_ids = {'1008', '2047'} # Energy (KCAL) and Energy (Atwater General Factors) (KCAL)

            # First pass: Identify foods with non-zero energy values
            with open(os.path.join(usda_data_dir, 'food_nutrient.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader) # Skip header
                for row in reader:
                    fdc_id = row[1]
                    nutrient_id = row[2]
                    amount = float(row[3])
                    if nutrient_id in energy_nutrient_ids and amount > 0:
                        foods_with_energy.add(fdc_id)

            food_descriptions = {}
            with open(os.path.join(usda_data_dir, 'food.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader) # Skip header
                for row in reader:
                    food_descriptions[row[0]] = row[2] # fdc_id, description

            branded_foods_data = {}
            upc_dates = {}
            duplicate_upcs = 0
            with open(os.path.join(usda_data_dir, 'branded_food.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                for row in reader:
                    fdc_id = row[0]
                    gtin_upc = row[4] if row[4] else None
                    ingredients = row[5] if row[5] else None
                    available_date = row[14] if row[14] else '1900-01-01'

                    if gtin_upc:
                        if gtin_upc in upc_dates:
                            if available_date > upc_dates[gtin_upc]:
                                # This one is newer, so replace the old one
                                upc_dates[gtin_upc] = available_date
                                branded_foods_data[fdc_id] = (gtin_upc, ingredients)
                            duplicate_upcs += 1
                        else:
                            # First time seeing this UPC
                            upc_dates[gtin_upc] = available_date
                            branded_foods_data[fdc_id] = (gtin_upc, ingredients)
                    else:
                        branded_foods_data[fdc_id] = (gtin_upc, ingredients)
            
            print(f"-> Found {duplicate_upcs} duplicate UPCs, keeping the most recent.")

            foods_to_insert = []
            for fdc_id, description in food_descriptions.items():
                if fdc_id in foods_with_energy: # Only import foods with energy values
                    upc, ingredients = branded_foods_data.get(fdc_id, (None, None))
                    foods_to_insert.append((fdc_id, description, upc, ingredients))

            cursor.executemany("INSERT INTO foods (fdc_id, description, upc, ingredients) VALUES (?, ?, ?, ?)", foods_to_insert)
            print(f"-> Imported {len(foods_to_insert)} foods.")

            print("\nPopulating 'food_nutrients' table...")
            seen = set()
            to_insert = []
            skipped = 0
            with open(os.path.join(usda_data_dir, 'food_nutrient.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    fdc_id = row[1]
                    nutrient_id = row[2]
                    amount = float(row[3])

                    # Only insert if food has energy and amount is greater than 0
                    if fdc_id in foods_with_energy and amount > 0:
                        key = (fdc_id, nutrient_id)
                        if key not in seen:
                            seen.add(key)
                            to_insert.append((fdc_id, nutrient_id, amount))
                        else:
                            skipped += 1
            cursor.executemany("INSERT INTO food_nutrients (fdc_id, nutrient_id, amount) VALUES (?, ?, ?)", to_insert)
            print(f"-> Imported {len(to_insert)} unique food nutrients.")
            print(f"-> Skipped {skipped} duplicate entries.")

            # --- FINAL FIX FOR 'portions' TABLE - PROVIDES ALL COLUMNS ---
            print("\nPopulating 'portions' table...")

            portions_data = []
            with open(os.path.join(usda_data_dir, 'food_portion.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    # id is auto-incremented, so we don't need to provide it
                    fdc_id = row[1]
                    seq_num = row[2]
                    amount = row[3]
                    measure_unit_id = row[4]
                    portion_description = row[5]
                    modifier = row[6]
                    gram_weight = row[7]
                    portions_data.append((fdc_id, seq_num, amount, measure_unit_id, portion_description, modifier, gram_weight))

            cursor.executemany("INSERT INTO portions (fdc_id, seq_num, amount, measure_unit_id, portion_description, modifier, gram_weight) VALUES (?, ?, ?, ?, ?, ?, ?)", portions_data)
            print(f"-> Imported {len(portions_data)} food portions.")

        print("\n--- Import successful. Database is ready. ---")
        conn.close()

    except (sqlite3.Error, IOError, csv.Error) as e:
        print(f"\n--- An error occurred during database import: {e} ---", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        import_usda_data(sys.argv[1])
    else:
        import_usda_data()