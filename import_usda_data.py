import sqlite3
import csv
import os

DB_FILE = 'opennourish.db'
SCHEMA_FILE = 'schema.sql'
DATA_DIR = 'usda_data'

def import_data():
    """
    Main function to import USDA data into the SQLite database.
    """
    # 1. Delete the old database file if it exists
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"Removed old database '{DB_FILE}'.")

    # 2. Create a new database connection
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    print(f"Created new database '{DB_FILE}'.")

    # 3. Read and execute the schema to create tables
    try:
        with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        cur.executescript(schema_sql)
        print("Successfully created tables from 'schema.sql'.")
    except FileNotFoundError:
        print(f"Error: '{SCHEMA_FILE}' not found. Please ensure the schema file exists.")
        conn.close()
        return
    except sqlite3.Error as e:
        print(f"Database error during schema execution: {e}")
        conn.close()
        return

    # 4. Populate the tables from CSV files
    try:
        # Populate 'nutrients' table
        print("Populating nutrients...")
        with open(os.path.join(DATA_DIR, 'nutrient.csv'), 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            nutrients = [(row[0], row[1], row[2]) for row in reader]
        cur.executemany("INSERT INTO nutrients (id, name, unit_name) VALUES (?, ?, ?)", nutrients)
        print(f"Populated {len(nutrients)} nutrients.")

        # Populate 'foods' table
        print("Populating foods...")
        with open(os.path.join(DATA_DIR, 'food.csv'), 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            foods = [(row[0], row[2]) for row in reader]
        cur.executemany("INSERT INTO foods (fdc_id, description, upc) VALUES (?, ?, NULL)", foods)
        print(f"Populated {len(foods)} foods.")

        # Update foods with UPCs from branded_food.csv
        print("Updating foods with UPC barcodes...")
        upc_updates = []
        processed_upcs = set()
        with open(os.path.join(DATA_DIR, 'branded_food.csv'), 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                fdc_id = row[0]
                upc = row[4]
                if upc and upc not in processed_upcs: # Only update if UPC exists and is not a duplicate
                    upc_updates.append((upc, fdc_id))
                    processed_upcs.add(upc)
        
        cur.executemany("UPDATE foods SET upc = ? WHERE fdc_id = ?", upc_updates)
        print(f"Updated {len(upc_updates)} foods with unique UPCs.")

        # Update foods with ingredients from branded_food.csv
        print("Updating foods with ingredient lists...")
        ingredient_updates = []
        with open(os.path.join(DATA_DIR, 'branded_food.csv'), 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                fdc_id = row[0]
                ingredients = row[19] if len(row) > 19 else None # Assuming ingredients are at index 19
                if ingredients: # Only update if ingredients exist
                    ingredient_updates.append((ingredients, fdc_id))
        
        cur.executemany("UPDATE foods SET ingredients = ? WHERE fdc_id = ?", ingredient_updates)
        print(f"Updated {len(ingredient_updates)} foods with ingredient lists.")

        # Populate 'food_nutrients' table
        print("Populating food_nutrients...")
        food_nutrients = []
        processed_pairs = set()
        with open(os.path.join(DATA_DIR, 'food_nutrient.csv'), 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                if not row[3]:  # Skip rows with empty amount
                    continue
                fdc_id = row[1]
                nutrient_id = row[2]
                pair = (fdc_id, nutrient_id)
                if pair not in processed_pairs:
                    food_nutrients.append((fdc_id, nutrient_id, row[3]))
                    processed_pairs.add(pair)
        cur.executemany("INSERT INTO food_nutrients (fdc_id, nutrient_id, amount) VALUES (?, ?, ?)", food_nutrients)
        print(f"Populated {len(food_nutrients)} food nutrient records.")

        # Populate 'portions' table
        print("Populating portions...")
        # First, load measure_unit.csv into a dictionary
        measure_units = {}
        with open(os.path.join(DATA_DIR, 'measure_unit.csv'), 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                measure_units[row[0]] = row[1]  # map measure_unit_id to name

        # Combine with food_portion.csv
        portions = []
        processed_portions = set() # Use a set to track composite keys and avoid duplicates
        with open(os.path.join(DATA_DIR, 'food_portion.csv'), 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                fdc_id = row[1]
                gram_weight = row[7]

                # Skip rows without a gram weight, as they are not useful
                if not gram_weight:
                    continue

                # Use the pre-formatted description if available
                measure_description = row[5].strip()

                # If not, build a description from other columns
                if not measure_description:
                    amount = row[3]
                    measure_unit_id = row[4]
                    modifier = row[6].strip()
                    unit_name = measure_units.get(measure_unit_id, '').strip()

                    # Format amount (e.g., 1.0 -> 1)
                    try:
                        amount_float = float(amount)
                        amount_str = str(int(amount_float)) if amount_float.is_integer() else str(amount_float)
                    except ValueError:
                        amount_str = amount

                    # Combine the parts into a descriptive string
                    description_parts = [part for part in [amount_str, unit_name, modifier] if part]
                    measure_description = ' '.join(description_parts)

                # Ensure we have a description before adding
                if not measure_description:
                    continue

                # Avoid inserting duplicate fdc_id/description pairs, which violates the primary key
                portion_key = (fdc_id, measure_description)
                if portion_key not in processed_portions:
                    portions.append((fdc_id, measure_description, gram_weight))
                    processed_portions.add(portion_key)

        cur.executemany("INSERT INTO portions (fdc_id, measure_description, gram_weight) VALUES (?, ?, ?)", portions)
        print(f"Populated {len(portions)} portions.")

    except FileNotFoundError as e:
        print(f"Error: Data file not found - {e}. Make sure the 'usda_data/' directory is populated.")
    except Exception as e:
        print(f"An error occurred during data population: {e}")
    finally:
        # 5. Commit changes and close the connection
        conn.commit()
        conn.close()
        print("Finished. Database 'opennourish.db' is ready.")

if __name__ == '__main__':
    import_data()
