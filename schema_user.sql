-- schema_user.sql

-- Stores user login information.
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

-- Stores user-created recipes.
CREATE TABLE recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    instructions TEXT,
    description TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- A table linking a recipe to its ingredients, which are foods from the USDA database.
CREATE TABLE recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL,
    -- This is just a number. It is a "logical" link to the foods table in the usda_data.db
    fdc_id INTEGER,
    -- This is a link to the user's custom food
    my_food_id INTEGER,
    -- The user-defined amount for this ingredient in the recipe
    amount REAL NOT NULL,
    -- The user-selected portion, e.g., "cup", "slice", "g"
    serving_type TEXT NOT NULL,
    FOREIGN KEY (recipe_id) REFERENCES recipes (id),
    FOREIGN KEY (my_food_id) REFERENCES my_foods (id)
);

-- The user's daily food journal.
CREATE TABLE daily_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    log_date DATE NOT NULL,
    -- The food item from the USDA database
    fdc_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    serving_type TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
