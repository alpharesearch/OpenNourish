# OpenNourish
OpenNourish is a free and open source food tracker.

## Installation

1. **Download the USDA FoodData Central dataset:**
   - Go to the [USDA FoodData Central download page](https://fdc.nal.usda.gov/download-datasets.html).
   - Download the latest "FoodData Central, April 2025: All data" dataset (or a newer version if available).
   - Unzip the downloaded FoodData_Central_csv_2025-04-24.zip file.

2. **Organize the data files:**
   - Create a folder named `usda_data` in the root of the OpenNourish project directory.
   - From the unzipped USDA dataset, copy the following CSV files into the `usda_data` folder:
     - `food.csv`
     - `nutrient.csv`
     - `food_nutrient.csv`
     - `food_portion.csv`
     - `measure_unit.csv`

3. **Set up the environment and install dependencies:**
   - It is recommended to use a Conda environment:
     ```bash
     conda create --name opennourish python=3.9
     conda activate opennourish
     ```
   - Install the required Python packages:
     ```bash
     pip install -r requirements.txt
     ```

4. **Create and populate the database:**
   - Run the import script to build the `opennourish.db` file from the USDA data. This may take a few minutes.
     ```bash
     python import_usda_data.py [--keep_newest_upc_only]
     ```
   - The `--keep_newest_upc_only` flag (optional) will ensure that if multiple food entries share the same UPC, only the one with the most recent `available_date` is imported. By default, all entries with duplicate UPCs will be imported.

5. **Run the Flask application:**
   - Start the web server:
     ```bash
     flask run
     ```
   - Open your web browser and navigate to `http://127.0.0.1:5000` to use the application.
