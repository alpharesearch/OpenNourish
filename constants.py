DIET_PRESETS = {
    "SAD": {"protein": 0.15, "carbs": 0.50, "fat": 0.35},
    "Balanced": {"protein": 0.20, "carbs": 0.50, "fat": 0.30},
    "Low Carb": {"protein": 0.40, "carbs": 0.25, "fat": 0.35},
    "Low Fat": {"protein": 0.20, "carbs": 0.60, "fat": 0.20},
    "High Protein": {"protein": 0.40, "carbs": 0.40, "fat": 0.20},
    "Keto": {"protein": 0.20, "carbs": 0.05, "fat": 0.75},
    "Zone": {"protein": 0.30, "carbs": 0.40, "fat": 0.30},
    "Paleo": {"protein": 0.30, "carbs": 0.30, "fat": 0.40},
    "Mediterranean": {"protein": 0.20, "carbs": 0.40, "fat": 0.40},
}

CORE_NUTRIENT_IDS = {
    "calories": 1008,
    "protein": 1003,
    "carbs": 1005,
    "fat": 1004,
    "saturated_fat": 1258,
    "trans_fat": 1257,
    "cholesterol": 1253,
    "sodium": 1093,
    "fiber": 1079,
    "sugars": 2000,
    #'added_sugars': 1235,
    "vitamin_d": 1110,
    "calcium": 1087,
    "iron": 1089,
    "potassium": 1092,
}

WATER = "Water"
BREAKFAST = "Breakfast"
SNACK_MORNING = "Snack (morning)"
LUNCH = "Lunch"
SNACK_AFTERNOON = "Snack (afternoon)"
DINNER = "Dinner"
SNACK_EVENING = "Snack (evening)"
UNSPECIFIED = "Unspecified"

MEAL_CONFIG = {
    3: [BREAKFAST, LUNCH, DINNER],
    4: [WATER, BREAKFAST, LUNCH, DINNER],
    6: [
        BREAKFAST,
        SNACK_MORNING,
        LUNCH,
        SNACK_AFTERNOON,
        DINNER,
        SNACK_EVENING,
    ],
    7: [
        WATER,
        BREAKFAST,
        SNACK_MORNING,
        LUNCH,
        SNACK_AFTERNOON,
        DINNER,
        SNACK_EVENING,
    ],
}
DEFAULT_MEAL_NAMES = MEAL_CONFIG[6]

ALL_MEAL_TYPES = [
    WATER,
    BREAKFAST,
    SNACK_MORNING,
    LUNCH,
    SNACK_AFTERNOON,
    DINNER,
    SNACK_EVENING,
    UNSPECIFIED,
]

# Constant for friends page endpoint
FRIENDS_PAGE_ENDPOINT = "friends.friends_page"

# Constant for food detail endpoint
MAIN_FOOD_DETAIL_ENDPOINT = "main.food_detail"

# Constant for portions table anchor
PORTIONS_TABLE_ANCHOR = "#portions-table"

# Constant for tracking progress endpoint
TRACKING_PROGRESS_ENDPOINT = "tracking.progress"

USERS_ID = "users.id"
