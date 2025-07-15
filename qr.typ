#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam
#import "@preview/codetastic:0.2.2": ean13
#let data = (
  servings: "1", // Assuming 1 serving for 100g
  serving_size: "100g",
  calories: "315",
  total_fat: (value: 20.4, unit: "g"),
  saturated_fat: (value: 13.0, unit: "g"),
  trans_fat: (value: 0.0, unit: "g"),
  cholesterol: (value: 9, unit: "mg"),
  sodium: (value: 93, unit: "mg"),
  carbohydrate: (value: 35.2, unit: "g"),
  fiber: (value: 1.9, unit: "g"),
  sugars: (value: 24.1, unit: "g"),
  added_sugars: (value: 16.7, unit: "g"),
  protein: (value: 1.9, unit: "g"),
  micronutrients: (
    (name: "Vitamin D", key: "vitamin_d", value: 0, unit: "mcg"),
    (name: "Calcium", key: "calcium", value: 74, unit: "mg"),
    (name: "Iron", key: "iron", value: 1.1, unit: "mg"),
    (name: "Potassium", key: "potassium", value: 93, unit: "mg"),
  ),
)

#set page(paper: "a4", header: align(right + horizon)[OpenNourish Food fact sheet], columns: 2)
#set text(font: "Liberation Sans")
#place(
  top + center,
  float: true,
  scope: "parent",
  clearance: 2em,
)[
= VANILLA WITH COATING FROZEN DAIRY DESSERT BARS, VANILLA
]
== UPC:
#ean13(scale:(1.8, .5), "072554110894")

== Ingredients: 
DAIRY PRODUCT SOLIDS, SKIM MILK, SUGAR, CORN SYRUP, COCONUT OIL, PALM OIL, CREAM, RICE FLOUR, COCOA, MALTODEXTRIN, REDUCED MINERALS WHEY, PROPYLENE GLYCOL MONOSTEARATE, SALT, CELLULOSE GEL, GUAR GUM, CALCIUM CARBONATE, MONOGLYCERIDES, MILK, CHOCOLATE, CAROB BEAN GUM, CELLULOSE GUM, NATURAL FLAVOR, SOY LECITHIN.

== Portion Sizes: 
 (1.0g)



#show: nutrition-label-nam(data)


