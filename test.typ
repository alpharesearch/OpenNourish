#import "nutrition-lable-nam.typ": nutrition-label-nam

#let data = (
  servings: "1", // Assuming 1 serving for 100g
  serving_size: "100g",
  calories: "541",
  total_fat: (value: 32.4, unit: "g"),
  saturated_fat: (value: 10.8, unit: "g"),
  trans_fat: (value: 0.0, unit: "g"),
  cholesterol: (value: 14, unit: "mg"),
  sodium: (value: 0, unit: "mg"),
  carbohydrate: (value: 62.2, unit: "g"),
  fiber: (value: 2.7, unit: "g"),
  sugars: (value: 0.0, unit: "g"),
  added_sugars: (value: 0, unit: "g"), // Assuming no added sugars data for now
  protein: (value: 5.4, unit: "g"),
  micronutrients: (
    (name: "Vitamin D (D2 + D3)", key: "vitamin_d", value: 0.0, unit: "mcg"),
    (name: "Calcium", key: "calcium", value: 0.0, unit: "mg"),
    (name: "Iron", key: "iron", value: 0.0, unit: "mg"),
    (name: "Potassium", key: "potassium", value: 0.0, unit: "mg"),
    (name: "Vitamin A, RAE", key: "vitamin_a", value: 0.0, unit: "mcg"),
    (name: "Vitamin C, total ascorbic acid", key: "vitamin_c", value: 0.0, unit: "mg")
  ),
)

#show: nutrition-label-nam(data)

#align(center, text(20pt, "Nutrition Facts for FERRERO, NUTELLA, HAZELNUT SPREAD WITH COCOA"))
