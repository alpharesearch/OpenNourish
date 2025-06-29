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
        db_file = 'opennourish.db'
    usda_data_dir = 'usda_data'
    schema_file = 'schema.sql'

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

            print("\nPopulating 'foods' table...")
            with open(os.path.join(usda_data_dir, 'food.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)
                data = [(row[0], row[2]) for row in reader]
                cursor.executemany("INSERT INTO foods (fdc_id, description) VALUES (?, ?)", data)
                print(f"-> Imported {len(data)} foods.")

            print("\nPopulating 'food_nutrients' table...")
            seen = set()
            to_insert = []
            skipped = 0
            with open(os.path.join(usda_data_dir, 'food_nutrient.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    key = (row[1], row[2])
                    if key not in seen:
                        seen.add(key)
                        to_insert.append((row[1], row[2], row[3]))
                    else:
                        skipped += 1
            cursor.executemany("INSERT INTO food_nutrients (fdc_id, nutrient_id, amount) VALUES (?, ?, ?)", to_insert)
            print(f"-> Imported {len(to_insert)} unique food nutrients.")
            print(f"-> Skipped {skipped} duplicate entries.")

            # --- FINAL FIX FOR 'portions' TABLE - PROVIDES ALL COLUMNS ---
            print("\nPopulating 'portions' table...")

            measure_units = {row[0]: row[1] for row in csv.reader(open(os.path.join(usda_data_dir, 'measure_unit.csv'), 'r', encoding='utf-8'))}

            portions_data = []
            with open(os.path.join(usda_data_dir, 'food_portion.csv'), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    fdc_id = row[1]
                    measure_unit_id = row[2]
                    gram_weight = row[7]
                    measure_description = measure_units.get(measure_unit_id, "N/A")
                    # Append all four values in the correct order for the INSERT statement
                    portions_data.append((fdc_id, measure_unit_id, measure_description, gram_weight))

            # The INSERT statement now provides values for all four required columns
            cursor.executemany("INSERT INTO portions (fdc_id, measure_unit_id, measure_description, gram_weight) VALUES (?, ?, ?, ?)", portions_data)
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