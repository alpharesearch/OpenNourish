-- This table stores the basic information about each food item.
CREATE TABLE foods (
    -- The unique identifier for the food from the USDA FoodData Central database.
    fdc_id INTEGER PRIMARY KEY,
    -- A description of the food item.
    description TEXT NOT NULL,
    -- The Global Trade Item Number (GTIN) or UPC barcode for the food.
    upc TEXT,
    -- A list of ingredients for the food item.
    ingredients TEXT
);

-- This table stores information about each nutrient.
CREATE TABLE nutrients (
    -- The unique identifier for the nutrient.
    id INTEGER PRIMARY KEY,
    -- The name of the nutrient (e.g., "Protein", "Total lipid (fat)").
    name TEXT NOT NULL,
    -- The unit of measurement for the nutrient (e.g., "g", "mg").
    unit_name TEXT NOT NULL
);

-- This table links foods to their respective nutrients and specifies the amount of each nutrient in 100g of the food.
CREATE TABLE food_nutrients (
    -- The foreign key referencing the food item.
    fdc_id INTEGER NOT NULL,
    -- The foreign key referencing the nutrient.
    nutrient_id INTEGER NOT NULL,
    -- The amount of the nutrient in the food, per 100g of the food.
    amount REAL NOT NULL,
    PRIMARY KEY (fdc_id, nutrient_id),
    FOREIGN KEY (fdc_id) REFERENCES foods (fdc_id),
    FOREIGN KEY (nutrient_id) REFERENCES nutrients (id)
);

-- This table stores information about measure units.
CREATE TABLE measure_units (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

-- This table provides user-friendly portion sizes for foods.
CREATE TABLE portions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fdc_id INTEGER NOT NULL,
    seq_num INTEGER NOT NULL,
    amount REAL,
    measure_unit_id INTEGER NOT NULL,
    portion_description TEXT NOT NULL,
    modifier TEXT,
    gram_weight REAL NOT NULL,
    FOREIGN KEY (fdc_id) REFERENCES foods (fdc_id),
    FOREIGN KEY (measure_unit_id) REFERENCES measure_units (id)
);

