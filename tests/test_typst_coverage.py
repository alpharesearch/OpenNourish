"""Coverage-focused unit tests for ``opennourish/typst_utils.py``.

Covers all three label sources — USDA ``Food``, ``MyFood`` and ``Recipe`` —
across the label-only / details / svg variants, portion scaling, UPC
normalisation and the typst failure paths.

These tests call the typst helpers directly (no route/URL assertions);
route-level integration for the label endpoints lives in the feature test
files. Real ``typst`` subprocess calls are used for the success paths so the
generated artefacts are verified by their magic bytes. Failure paths fake
``subprocess.run`` so no compiler is involved.
"""

import subprocess

import pytest

from models import (
    db,
    Food,
    FoodNutrient,
    MyFood,
    Nutrient,
    Recipe,
    RecipeIngredient,
    UnifiedPortion,
    User,
)
from opennourish import typst_utils

USDA_FDC_ID = 167588

NUTRIENTS = [
    (1008, "Energy", "kcal", 100.0),
    (1003, "Protein", "g", 8.0),
    (1005, "Carbohydrate, by difference", "g", 15.0),
    (1004, "Total lipid (fat)", "g", 5.0),
    (1258, "Fatty acids, total saturated", "g", 2.0),
    (1257, "Fatty acids, total trans", "g", 0.1),
    (1253, "Cholesterol", "mg", 10.0),
    (1093, "Sodium, Na", "mg", 200.0),
    (1079, "Fiber, total dietary", "g", 3.0),
    (2000, "Total Sugars", "g", 10.0),
    (1235, "Sugars, added", "g", 5.0),
    (1110, "Vitamin D (D2 + D3)", "mcg", 2.0),
    (1087, "Calcium, Ca", "mg", 260.0),
    (1089, "Iron, Fe", "mg", 8.0),
    (1092, "Potassium, K", "mg", 240.0),
]


@pytest.fixture
def ctx(app_with_db):
    """App + request context so ``send_file`` works outside a view."""
    with app_with_db.test_request_context("/"):
        yield app_with_db


@pytest.fixture
def label_user(ctx):
    user = User(username="typst_user", email="typst_user@example.com")
    user.set_password("password")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def usda_food(ctx):
    """USDA food carrying every nutrient the label template needs."""
    food = Food(
        fdc_id=USDA_FDC_ID,
        description="Test *Food*",
        ingredients="Water, Salt",
        upc=None,
    )
    db.session.add(food)
    for nutrient_id, name, unit, amount in NUTRIENTS:
        db.session.add(Nutrient(id=nutrient_id, name=name, unit_name=unit))
        db.session.add(
            FoodNutrient(
                fdc_id=food.fdc_id,
                nutrient_id=nutrient_id,
                amount=amount,
            )
        )
    db.session.commit()
    return food


def make_portion(
    *,
    fdc_id=None,
    my_food_id=None,
    recipe_id=None,
    seq_num=1,
    amount=1.0,
    measure_unit_description="g",
    portion_description=None,
    gram_weight=100.0,
):
    portion = UnifiedPortion(
        fdc_id=fdc_id,
        my_food_id=my_food_id,
        recipe_id=recipe_id,
        seq_num=seq_num,
        amount=amount,
        measure_unit_description=measure_unit_description,
        portion_description=portion_description,
        gram_weight=gram_weight,
    )
    db.session.add(portion)
    db.session.commit()
    return portion


def make_my_food(user_id, **kwargs):
    kwargs.setdefault("description", "Test MyFood")
    kwargs.setdefault("calories_per_100g", 150.0)
    kwargs.setdefault("protein_per_100g", 10.0)
    kwargs.setdefault("carbs_per_100g", 20.0)
    kwargs.setdefault("fat_per_100g", 5.0)
    my_food = MyFood(user_id=user_id, **kwargs)
    db.session.add(my_food)
    db.session.commit()
    return my_food


def make_recipe(user_id, name="Test Recipe", **kwargs):
    kwargs.setdefault("calories_per_100g", 120.0)
    kwargs.setdefault("protein_per_100g", 6.0)
    kwargs.setdefault("carbs_per_100g", 18.0)
    kwargs.setdefault("fat_per_100g", 3.0)
    kwargs.setdefault("fiber_per_100g", 2.0)
    recipe = Recipe(user_id=user_id, name=name, **kwargs)
    db.session.add(recipe)
    db.session.commit()
    return recipe


class FakeCompletedRun:
    """Stand-in for ``subprocess.run`` results."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def raise_called_process_error(monkeypatch, stderr="typst exploded"):
    def _fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            1, args[0] if args else ["typst"], output="out", stderr=stderr
        )

    monkeypatch.setattr(typst_utils.subprocess, "run", _fake_run)


def raise_file_not_found(monkeypatch):
    def _fake_run(*args, **kwargs):
        raise FileNotFoundError("typst: command not found")

    monkeypatch.setattr(typst_utils.subprocess, "run", _fake_run)


def returncode_one(monkeypatch, stderr="bad typst flag"):
    monkeypatch.setattr(
        typst_utils.subprocess,
        "run",
        lambda *a, **k: FakeCompletedRun(1, "", stderr),
    )


def body_of(response):
    if response.direct_passthrough:
        return b"".join(response.response)
    return response.get_data()


# Every Typst markup hazard in one string, measured on typst 0.15.1: "$" opens
# math ("unclosed delimiter"), "#" enters code ("unknown variable"), "<x>" and
# "@tag" are a label and a reference, "`" opens raw text, "]" closes a content
# block, "%" comments out the rest of the line, and "*" / "_" restyle the text.
# A backslash is in here because a bare one silently swallows the next character.
# Straight quotes and "--" are deliberately absent: markup text is supposed to go
# through Typst's smart typography, so escaping those would change what renders.
MARKUP_HAZARDS = "Hazard $5 <x> @tag 100% _it_ `raw`] #link \\ tail"

# The same text for a Typst *string literal*, where only '"' and '\' are
# significant — escaping "*" inside a string shows the backslash instead.
STRING_CONTEXT_HAZARDS = 'Cup "o" *stuff* $5 \\ tail'


# ---------------------------------------------------------------------------
# The escapers themselves — opennourish/AGENTS.md owns this contract
# ---------------------------------------------------------------------------


def test_escapers_are_context_specific_in_both_directions():
    markup = typst_utils._escape_typst_markup
    string = typst_utils._escape_typst_string

    # "*" is markup, so only the markup escaper touches it. Escaping it inside a
    # string is what made labels print a stray backslash.
    assert markup("a*b") == "a\\*b"
    assert string("a*b") == "a*b"
    # A quote is a delimiter only inside a string literal.
    assert markup('say "hi"') == 'say "hi"'
    assert string('say "hi"') == 'say \\"hi\\"'
    # The backslash is escaped first, so it cannot arm the character after it.
    assert markup("a\\$b") == "a\\\\\\$b"
    assert string("a\\$b") == "a\\\\$b"
    # Both are no-ops on the non-string values the numeric fields still produce.
    assert markup(3.5) == 3.5
    assert string(None) is None


# ---------------------------------------------------------------------------
# _get_nutrition_label_data (USDA)
# ---------------------------------------------------------------------------


def test_usda_label_data_missing_food(ctx):
    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(999999)
    assert food is None
    assert nutrient_info is None
    assert nutrients is None


def test_usda_label_data_maps_preferred_and_alternate_names(ctx, usda_food):
    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(USDA_FDC_ID)

    assert food is usda_food
    assert nutrients["Energy"] == 100.0
    # "Sodium, Na" and "Total Sugars" are alternate names in the mapping.
    assert nutrients["Sodium"] == 200.0
    assert nutrients["Sugars, total including NLEA"] == 10.0
    assert nutrients["Vitamin D"] == 2.0
    assert nutrient_info["Energy"]["format"] == ".0f"


def test_usda_label_data_absent_nutrients_default_to_zero(ctx):
    db.session.add(Food(fdc_id=424242, description="Bare food"))
    db.session.commit()

    _, _, nutrients = typst_utils._get_nutrition_label_data(424242)
    assert set(nutrients) == {
        "Energy",
        "Total lipid (fat)",
        "Fatty acids, total saturated",
        "Fatty acids, total trans",
        "Cholesterol",
        "Sodium",
        "Carbohydrate, by difference",
        "Fiber, total dietary",
        "Sugars, total including NLEA",
        "Sugars, added",
        "Protein",
        "Vitamin D",
        "Calcium",
        "Iron",
        "Potassium",
    }
    assert all(value == 0.0 for value in nutrients.values())


# ---------------------------------------------------------------------------
# _generate_typst_content (USDA)
# ---------------------------------------------------------------------------


def test_usda_content_falls_back_to_100g_without_portions(ctx, usda_food):
    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(USDA_FDC_ID)
    content = typst_utils._generate_typst_content(food, nutrient_info, nutrients)

    assert 'serving_size: "100g"' in content
    assert 'calories: "100"' in content
    assert 'total_fat: (value: 5.0, unit: "g")' in content
    assert "Net Carbs" not in content  # label-only variant
    assert "#show: nutrition-label-nam(data)" in content
    assert "#import" in content


def test_usda_content_uses_gram_default_portion_and_scales(ctx, usda_food):
    make_portion(fdc_id=usda_food.fdc_id, gram_weight=250.0, amount=250.0)

    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(USDA_FDC_ID)
    content = typst_utils._generate_typst_content(
        food, nutrient_info, nutrients, include_extra_info=True
    )

    assert 'serving_size: "250 g"' in content or 'serving_size: "250g"' in content
    # scaling factor 2.5 -> 100 kcal/100g becomes 250 kcal per serving
    assert 'calories: "250"' in content
    assert "Net Carbs: 30.0g" in content
    assert "== Ingredients:" in content
    assert "Water, Salt" in content
    assert "Test \\*Food\\*" in content  # asterisks escaped for typst
    assert "= Test \\*Food\\*" in content


def test_usda_content_non_gram_portion_shows_grams(ctx, usda_food):
    make_portion(
        fdc_id=usda_food.fdc_id,
        measure_unit_description="cup",
        portion_description="chopped",
        gram_weight=137.5,
        amount=0.5,
    )

    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(USDA_FDC_ID)
    content = typst_utils._generate_typst_content(food, nutrient_info, nutrients)

    assert "0.50 cup chopped (138g)" in content
    assert 'calories: "138"' in content


def test_usda_content_lists_all_portions_or_na(ctx, usda_food):
    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(USDA_FDC_ID)

    without = typst_utils._generate_typst_content(
        food, nutrient_info, nutrients, include_extra_info=True
    )
    assert "== Portion Sizes: \nN/A" in without

    make_portion(fdc_id=usda_food.fdc_id, seq_num=1, gram_weight=100.0)
    make_portion(
        fdc_id=usda_food.fdc_id,
        seq_num=2,
        amount=2.0,
        measure_unit_description="cup",
        gram_weight=240.0,
    )

    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(USDA_FDC_ID)
    with_portions = typst_utils._generate_typst_content(
        food, nutrient_info, nutrients, include_extra_info=True
    )
    assert "1 g (100.0g)" in with_portions
    # Units render verbatim from the DB value; nothing pluralizes them.
    assert "2 cup (240.0g)" in with_portions
    assert "\\ " in with_portions


def test_usda_content_missing_ingredients_falls_back_to_na(ctx):
    db.session.add(Food(fdc_id=515151, description="No ingredients"))
    db.session.commit()
    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(515151)

    content = typst_utils._generate_typst_content(
        food, nutrient_info, nutrients, include_extra_info=True
    )
    assert "== Ingredients: \nN/A" in content


@pytest.mark.parametrize(
    "upc, expected",
    [
        (None, None),
        ("04400003029", "004400003029"),  # 11 digits -> padded
        ("044000030293", "004400003029"),  # EAN-13 -> first 12
        ("0440000302939", "044000030293"),  # 13 digits -> first 12
    ],
)
def test_usda_content_upc_normalisation(ctx, usda_food, upc, expected):
    usda_food.upc = upc
    db.session.commit()

    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(USDA_FDC_ID)
    content = typst_utils._generate_typst_content(
        food, nutrient_info, nutrients, include_extra_info=True
    )

    if expected is None:
        assert "ean13(" not in content
    else:
        assert f'"{expected}"' in content
        assert "#ean13(scale:(1.8, .5)" in content


# ---------------------------------------------------------------------------
# generate_nutrition_label_pdf / _svg
# ---------------------------------------------------------------------------


def test_generate_nutrition_label_pdf_real_typst(ctx, usda_food):
    response = typst_utils.generate_nutrition_label_pdf(USDA_FDC_ID)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.headers["Cache-Control"] == typst_utils.NO_CACHE_HEADERS
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"
    assert body_of(response)[:5] == b"%PDF-"


def test_generate_nutrition_label_svg_real_typst(ctx, usda_food):
    response = typst_utils.generate_nutrition_label_svg(USDA_FDC_ID)

    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    assert response.headers["Cache-Control"] == typst_utils.NO_CACHE_HEADERS
    assert b"<svg" in body_of(response)[:4096]


def test_generate_nutrition_label_pdf_unknown_food(ctx):
    assert typst_utils.generate_nutrition_label_pdf(999999) == ("Food not found", 404)


def test_generate_nutrition_label_svg_unknown_food(ctx):
    assert typst_utils.generate_nutrition_label_svg(999999) == ("Food not found", 404)


def test_generate_nutrition_label_pdf_compile_error(ctx, usda_food, monkeypatch):
    raise_called_process_error(monkeypatch, stderr="error: unexpected token")

    message, status = typst_utils.generate_nutrition_label_pdf(USDA_FDC_ID)
    assert status == 500
    assert "error: unexpected token" in message


def test_generate_nutrition_label_pdf_missing_binary(ctx, usda_food, monkeypatch):
    raise_file_not_found(monkeypatch)

    message, status = typst_utils.generate_nutrition_label_pdf(USDA_FDC_ID)
    assert status == 500
    assert message == typst_utils.TYPST_NOT_FOUND_ERROR


def test_generate_nutrition_label_svg_compile_error(ctx, usda_food, monkeypatch):
    raise_called_process_error(monkeypatch, stderr="svg boom")

    message, status = typst_utils.generate_nutrition_label_svg(USDA_FDC_ID)
    assert status == 500
    assert "svg boom" in message


def test_generate_nutrition_label_svg_missing_binary(ctx, usda_food, monkeypatch):
    raise_file_not_found(monkeypatch)

    message, status = typst_utils.generate_nutrition_label_svg(USDA_FDC_ID)
    assert status == 500
    assert message == typst_utils.TYPST_NOT_FOUND_ERROR


def escape_markup(text):
    """The escaping contract, restated here so the tests cannot silently agree
    with an implementation that stopped escaping."""
    escaped = text.replace("\\", "\\\\")
    for special in typst_utils.TYPST_MARKUP_SPECIALS:
        escaped = escaped.replace(special, "\\" + special)
    return escaped


def test_usda_content_escapes_typst_markup(ctx, usda_food):
    usda_food.description = MARKUP_HAZARDS
    usda_food.ingredients = MARKUP_HAZARDS
    db.session.commit()

    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(USDA_FDC_ID)
    content = typst_utils._generate_typst_content(
        food, nutrient_info, nutrients, include_extra_info=True
    )

    escaped = escape_markup(MARKUP_HAZARDS)
    # Heading and ingredients both carry it, and neither keeps raw markup.
    assert content.count(escaped) == 2
    assert f"= {MARKUP_HAZARDS}" not in content


def test_usda_content_escapes_portions_without_the_separator(ctx, usda_food):
    make_portion(
        fdc_id=usda_food.fdc_id,
        amount=1.0,
        measure_unit_description="cup",
        portion_description='A "b" *c* $',
        gram_weight=137.5,
    )
    make_portion(fdc_id=usda_food.fdc_id, seq_num=2, amount=2.0, gram_weight=50.0)

    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(USDA_FDC_ID)
    content = typst_utils._generate_typst_content(
        food, nutrient_info, nutrients, include_extra_info=True
    )

    # Markup context: the quote is Typst's business, "*" and "$" are ours.
    assert 'A "b" \\*c\\* \\$ (137.5g)' in content
    # Portions are joined with "\\ ", and escaping per item keeps it single.
    assert ")\\ 2 g (" in content
    assert ")\\\\ 2 g (" not in content


def test_usda_serving_size_escapes_only_string_delimiters(ctx, usda_food):
    make_portion(
        fdc_id=usda_food.fdc_id,
        amount=1.0,
        measure_unit_description="cup",
        portion_description=STRING_CONTEXT_HAZARDS,
        gram_weight=137.5,
    )

    food, nutrient_info, nutrients = typst_utils._get_nutrition_label_data(USDA_FDC_ID)
    content = typst_utils._generate_typst_content(food, nutrient_info, nutrients)

    assert 'serving_size: "1 cup Cup \\"o\\" *stuff* $5 \\\\ tail (138g)"' in content
    # "\*" inside a string literal would print the backslash.
    assert "\\*" not in content


def test_generate_nutrition_label_pdf_renders_markup_hazards(ctx, usda_food):
    """The bug this locks: a "$" in a food name made every label a 500."""
    usda_food.description = MARKUP_HAZARDS
    usda_food.ingredients = MARKUP_HAZARDS
    db.session.commit()

    response = typst_utils.generate_nutrition_label_pdf(USDA_FDC_ID)

    assert response.status_code == 200
    assert body_of(response)[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# MyFood labels
# ---------------------------------------------------------------------------


MYFOOD_NUTRIENTS = {
    "calories_per_100g": 111.0,
    "protein_per_100g": 11.0,
    "carbs_per_100g": 12.0,
    "fat_per_100g": 13.0,
    "saturated_fat_per_100g": 14.0,
    "trans_fat_per_100g": 15.0,
    "cholesterol_mg_per_100g": 16.0,
    "sodium_mg_per_100g": 17.0,
    "fiber_per_100g": 18.0,
    "sugars_per_100g": 19.0,
    "added_sugars_per_100g": 20.0,
    "vitamin_d_mcg_per_100g": 21.0,
    "calcium_mg_per_100g": 22.0,
    "iron_mg_per_100g": 23.0,
    "potassium_mg_per_100g": 24.0,
}


def label_nutrients(**overrides):
    """A complete per-100g nutrient mapping for the direct generator tests."""
    base = {
        "Energy": 100.0,
        typst_utils.TOTAL_LIPID_FAT: 10.0,
        typst_utils.FATTY_ACIDS_TOTAL_SATURATED: 1.0,
        typst_utils.FATTY_ACIDS_TOTAL_TRANS: 0.5,
        "Cholesterol": 5.0,
        "Sodium": 300.0,
        typst_utils.CARBOHYDRATE_BY_DIFFERENCE: 20.0,
        typst_utils.FIBER_TOTAL_DIETARY: 4.0,
        typst_utils.SUGARS_TOTAL_INCLUDING_NLEA: 6.0,
        typst_utils.SUGARS_ADDED: 3.0,
        "Protein": 9.0,
        typst_utils.VITAMIN_D: 1.0,
        "Calcium": 90.0,
        "Iron": 2.0,
        "Potassium": 200.0,
    }
    base.update(overrides)
    return base


ZEROED_NUTRIENTS = dict.fromkeys(label_nutrients(), 0.0)


def test_myfood_label_data_missing(ctx):
    assert typst_utils._get_nutrition_label_data_myfood(999999) == (None, None)


def test_myfood_label_data_maps_every_column(ctx, label_user):
    my_food = make_my_food(
        label_user.id, ingredients="Flour, Water", **MYFOOD_NUTRIENTS
    )

    food, nutrients = typst_utils._get_nutrition_label_data_myfood(my_food.id)

    assert food is my_food
    assert nutrients["Energy"] == 111.0
    assert nutrients[typst_utils.TOTAL_LIPID_FAT] == 13.0
    assert nutrients[typst_utils.SUGARS_ADDED] == 20.0
    assert nutrients[typst_utils.VITAMIN_D] == 21.0
    assert nutrients["Potassium"] == 24.0


def test_myfood_label_data_zero_columns(ctx, label_user):
    my_food = make_my_food(
        label_user.id,
        calories_per_100g=0.0,
        protein_per_100g=0.0,
        carbs_per_100g=0.0,
        fat_per_100g=0.0,
    )

    _, nutrients = typst_utils._get_nutrition_label_data_myfood(my_food.id)

    assert nutrients["Energy"] == 0
    assert all(value == 0 for value in nutrients.values())


def test_myfood_content_falls_back_to_100g(ctx, label_user):
    my_food = make_my_food(label_user.id, **MYFOOD_NUTRIENTS)

    content = typst_utils._generate_typst_content_myfood(
        my_food,
        dict(
            MYFOOD_NUTRIENTS
            and {
                "Energy": 100.0,
                typst_utils.TOTAL_LIPID_FAT: 10.0,
                typst_utils.FATTY_ACIDS_TOTAL_SATURATED: 1.0,
                typst_utils.FATTY_ACIDS_TOTAL_TRANS: 0.5,
                "Cholesterol": 5.0,
                "Sodium": 300.0,
                typst_utils.CARBOHYDRATE_BY_DIFFERENCE: 20.0,
                typst_utils.FIBER_TOTAL_DIETARY: 4.0,
                typst_utils.SUGARS_TOTAL_INCLUDING_NLEA: 6.0,
                typst_utils.SUGARS_ADDED: 3.0,
                "Protein": 9.0,
                typst_utils.VITAMIN_D: 1.0,
                "Calcium": 90.0,
                "Iron": 2.0,
                "Potassium": 200.0,
            }
        ),
    )

    assert 'serving_size: "100g"' in content
    assert 'calories: "100"' in content
    assert "Net Carbs: 16.0g" in content
    assert "== My Food:" in content
    assert "== Ingredients: \nN/A" in content
    assert "== Portion Sizes: \nN/A" in content
    assert "#nutrition-label-nam(data, scale-percent: 73%" in content
    assert "#ean13(" not in content


def test_myfood_content_gram_and_non_gram_portions(ctx, label_user):
    my_food = make_my_food(
        label_user.id, ingredients="Water, *Salt*", **MYFOOD_NUTRIENTS
    )
    make_portion(my_food_id=my_food.id, seq_num=1, gram_weight=80.0, amount=80.0)
    make_portion(
        my_food_id=my_food.id,
        seq_num=2,
        amount=0.5,
        measure_unit_description="cup",
        portion_description="sliced",
        gram_weight=120.0,
    )

    content = typst_utils._generate_typst_content_myfood(my_food, label_nutrients())

    # seq_num 1 portion is 80 g -> scaling factor 0.8
    assert 'serving_size: "80 g"' in content or 'serving_size: "80g"' in content
    assert 'calories: "80"' in content
    # Non-gram default is annotated with its gram weight: see the other test.
    assert "0.50 cup sliced (120.0g)" in content
    assert "Water, \\*Salt\\*" in content
    assert "Test MyFood" in content


def test_myfood_content_non_gram_default_portion_shows_grams(ctx, label_user):
    my_food = make_my_food(label_user.id, **MYFOOD_NUTRIENTS)
    make_portion(
        my_food_id=my_food.id,
        seq_num=1,
        amount=1.0,
        measure_unit_description="cup",
        gram_weight=137.5,
    )

    content = typst_utils._generate_typst_content_myfood(my_food, label_nutrients())

    assert "138g" in content
    assert 'calories: "138"' in content


def test_myfood_content_label_only(ctx, label_user):
    my_food = make_my_food(label_user.id, **MYFOOD_NUTRIENTS)

    nutrients = ZEROED_NUTRIENTS
    content = typst_utils._generate_typst_content_myfood(
        my_food, nutrients, label_only=True
    )

    assert "#set page(width: 2in, height: 1in)" in content
    assert "== My Food:" not in content
    assert "Test MyFood" in content
    assert "#ean13(" not in content


@pytest.mark.parametrize(
    "upc, expected",
    [
        ("2001234567890", "200123456789"),  # internal 13-digit
        ("044000030293", "004400003029"),  # UPC-A gets a leading zero
        ("5901234123457", "590123412345"),  # plain EAN-13
        ("12345", "000000012345"),  # short code: left-padded (value preserved)
    ],
)
def test_myfood_content_upc_normalisation(ctx, label_user, upc, expected):
    my_food = make_my_food(label_user.id, upc=upc, **MYFOOD_NUTRIENTS)
    nutrients = ZEROED_NUTRIENTS

    full = typst_utils._generate_typst_content_myfood(my_food, nutrients)
    assert f'#ean13(scale:(2.0, .5), "{expected}")' in full

    label = typst_utils._generate_typst_content_myfood(
        my_food, nutrients, label_only=True
    )
    assert f'#ean13(scale:(1.6, .5), "{expected}")' in label


def test_myfood_content_escapes_typst_markup(ctx, label_user):
    my_food = make_my_food(
        label_user.id,
        description='Weird "name" \\ *star*',
        ingredients='Soy "sauce" *plus* \\ stuff',
        **MYFOOD_NUTRIENTS,
    )
    nutrients = ZEROED_NUTRIENTS

    content = typst_utils._generate_typst_content_myfood(my_food, nutrients)

    # Quotes stay raw in markup: Typst renders them as smart quotes, which is what
    # the USDA path has always done. Backslash and "*" are the ones we escape.
    assert 'Weird "name" \\\\ \\*star\\*' in content
    assert 'Soy "sauce" \\*plus\\* \\\\ stuff' in content


def test_generate_myfood_label_pdf_renders_markup_hazards(ctx, label_user):
    my_food = make_my_food(
        label_user.id, description=MARKUP_HAZARDS, **MYFOOD_NUTRIENTS
    )

    response = typst_utils.generate_myfood_label_pdf(my_food.id)

    assert response.status_code == 200
    assert body_of(response)[:5] == b"%PDF-"


def test_generate_myfood_label_pdf_full_and_label_only(ctx, label_user):
    my_food = make_my_food(label_user.id, **MYFOOD_NUTRIENTS)

    for label_only in (False, True):
        response = typst_utils.generate_myfood_label_pdf(my_food.id, label_only)
        assert response.status_code == 200
        assert response.mimetype == "application/pdf"
        assert body_of(response)[:5] == b"%PDF-"
        suffix = "label_only" if label_only else "details"
        assert suffix in response.headers["Content-Disposition"]


def test_generate_myfood_label_pdf_sanitises_download_name(ctx, label_user):
    my_food = make_my_food(
        label_user.id, description="Spicy Sauce!!", **MYFOOD_NUTRIENTS
    )

    response = typst_utils.generate_myfood_label_pdf(my_food.id)

    assert "Spicy_Sauce" in response.headers["Content-Disposition"]


def test_generate_myfood_label_pdf_unknown_food(ctx):
    assert typst_utils.generate_myfood_label_pdf(999999) == ("Food not found", 404)


def test_generate_myfood_label_pdf_compile_error(ctx, label_user, monkeypatch):
    my_food = make_my_food(label_user.id, **MYFOOD_NUTRIENTS)
    raise_called_process_error(monkeypatch, stderr="myfood boom")

    message, status = typst_utils.generate_myfood_label_pdf(my_food.id)
    assert status == 500
    assert "myfood boom" in message


def test_generate_myfood_label_pdf_missing_binary(ctx, label_user, monkeypatch):
    my_food = make_my_food(label_user.id, **MYFOOD_NUTRIENTS)
    raise_file_not_found(monkeypatch)

    message, status = typst_utils.generate_myfood_label_pdf(my_food.id)
    assert status == 500
    assert message == typst_utils.TYPST_NOT_FOUND_ERROR


# ---------------------------------------------------------------------------
# Recipe labels
# ---------------------------------------------------------------------------


def make_recipe_ingredient(recipe_id, **kwargs):
    kwargs.setdefault("amount_grams", 100.0)
    ingredient = RecipeIngredient(recipe_id=recipe_id, **kwargs)
    db.session.add(ingredient)
    db.session.commit()
    return ingredient


def test_recipe_label_data_missing(ctx):
    assert typst_utils._get_nutrition_label_data_recipe(999999) == (None, None)


def test_recipe_label_data_maps_every_column(ctx, label_user):
    recipe = make_recipe(
        label_user.id,
        calories_per_100g=111.0,
        fat_per_100g=13.0,
        added_sugars_per_100g=20.0,
        vitamin_d_mcg_per_100g=21.0,
        potassium_mg_per_100g=24.0,
    )

    stored, nutrients = typst_utils._get_nutrition_label_data_recipe(recipe.id)

    assert stored is recipe
    assert nutrients["Energy"] == 111.0
    assert nutrients[typst_utils.TOTAL_LIPID_FAT] == 13.0
    assert nutrients[typst_utils.SUGARS_ADDED] == 20.0
    assert nutrients[typst_utils.VITAMIN_D] == 21.0
    assert nutrients["Potassium"] == 24.0


def test_recipe_label_data_zero_columns(ctx, label_user):
    recipe = make_recipe(
        label_user.id,
        calories_per_100g=0.0,
        protein_per_100g=0.0,
        carbs_per_100g=0.0,
        fat_per_100g=0.0,
        fiber_per_100g=0.0,
    )

    _, nutrients = typst_utils._get_nutrition_label_data_recipe(recipe.id)

    assert all(value == 0 for value in nutrients.values())


def test_recipe_content_without_ingredients_or_portions(ctx, label_user):
    recipe = make_recipe(label_user.id, servings=4, instructions="Mix well.")

    content = typst_utils._generate_typst_content_recipe(recipe, label_nutrients())

    assert 'servings: "4' in content
    assert 'serving_size: "100g"' in content
    assert 'calories: "100"' in content
    assert "== Recipe:" not in content  # details branch, not label-only
    assert "= Test Recipe" in content
    assert "== Ingredients: \nN/A" in content
    assert "== Instructions: \nMix well." in content
    assert "== Portion Sizes: \nN/A" in content
    assert "#nutrition-label-nam(data, scale-percent: 75%)" in content
    assert "Net Carbs: 16.0g" in content
    assert "#ean13(" not in content


def test_recipe_content_label_only(ctx, label_user):
    recipe = make_recipe(label_user.id, servings=2.5, instructions="Fold gently.")

    content = typst_utils._generate_typst_content_recipe(
        recipe, label_nutrients(), label_only=True
    )

    assert 'servings: "2.5"' in content
    assert "#set page(width: 6in, height: 4in, columns: 2)" in content
    assert "== Recipe:" in content
    assert "== Ingredients: \nN/A" in content
    assert "== Instructions" not in content  # label-only drops the instructions
    assert "#nutrition-label-nam(data, scale-percent: 73%" in content


def test_recipe_content_svg_only(ctx, label_user):
    recipe = make_recipe(label_user.id)

    content = typst_utils._generate_typst_content_recipe(
        recipe, label_nutrients(), svg_only=True
    )

    assert "#set page(width: 12cm, height: 18cm)" in content
    assert "#nutrition-label-nam(data)" in content
    assert "== Recipe:" not in content


def test_recipe_content_gram_default_portion_scales(ctx, label_user):
    recipe = make_recipe(label_user.id)
    make_portion(recipe_id=recipe.id, seq_num=1, gram_weight=250.0, amount=250.0)

    content = typst_utils._generate_typst_content_recipe(recipe, label_nutrients())

    assert 'serving_size: "250 g"' in content or 'serving_size: "250g"' in content
    assert 'calories: "250"' in content
    assert "Net Carbs: 40.0g" in content


def test_recipe_content_non_gram_default_portion_shows_grams(ctx, label_user):
    recipe = make_recipe(label_user.id)
    make_portion(
        recipe_id=recipe.id,
        seq_num=1,
        amount=1.0,
        measure_unit_description="cup",
        portion_description="packed",
        gram_weight=137.5,
    )

    content = typst_utils._generate_typst_content_recipe(recipe, label_nutrients())

    assert "1 cup packed (138g)" in content
    assert 'calories: "138"' in content


def test_recipe_content_lists_portions_with_two_decimals(ctx, label_user):
    recipe = make_recipe(label_user.id)
    make_portion(recipe_id=recipe.id, seq_num=1, gram_weight=100.0, amount=100.0)
    make_portion(
        recipe_id=recipe.id,
        seq_num=2,
        amount=2.0,
        measure_unit_description="cup",
        gram_weight=240.0,
    )

    content = typst_utils._generate_typst_content_recipe(
        recipe, label_nutrients(), label_only=True
    )

    assert "100.00g" in content
    assert "2 cup (240.00g)" in content
    assert "\\ " in content


def test_recipe_content_renders_all_ingredient_kinds(ctx, label_user):
    recipe = make_recipe(label_user.id, servings=1, instructions="Combine.")
    egg = Food(fdc_id=USDA_FDC_ID, description="Whole Egg", ingredients="Egg")
    db.session.add(egg)
    db.session.commit()

    my_food = make_my_food(
        label_user.id, description="My *Yoghurt*", **MYFOOD_NUTRIENTS
    )
    child = make_recipe(label_user.id, name="Sauce Base")
    make_recipe_ingredient(child.id, my_food_id=my_food.id, amount_grams=50.0)

    egg_portion = make_portion(
        fdc_id=egg.fdc_id,
        seq_num=1,
        amount=2.0,
        measure_unit_description="cup",
        gram_weight=240.0,
    )

    make_recipe_ingredient(
        recipe.id,
        fdc_id=egg.fdc_id,
        amount_grams=120.0,
        portion_id_fk=egg_portion.id,
    )
    make_recipe_ingredient(recipe.id, my_food_id=my_food.id, amount_grams=60.0)
    make_recipe_ingredient(recipe.id, recipe_id_link=child.id, amount_grams=30.0)

    recipe = db.session.get(Recipe, recipe.id)
    content = typst_utils._generate_typst_content_recipe(recipe, label_nutrients())

    # USDA ingredient measured by its selected non-gram portion.
    assert "0.50 2 cup (120g) Whole Egg" in content
    # MyFood ingredient keeps plain gram units, no gram annotation.
    # No portion_id_fk means the raw gram amount is the quantity.
    assert "60.00 g My \\*Yoghurt\\*" in content
    # Nested recipe ingredient is labelled by its name.
    assert "30.00 g Sauce Base" in content


def test_recipe_content_escapes_typst_markup(ctx, label_user):
    recipe = make_recipe(
        label_user.id, name='Odd "name" \\ *star*', instructions='Say "hi" *now*'
    )

    content = typst_utils._generate_typst_content_recipe(recipe, label_nutrients())

    # As in the MyFood path, quotes belong to Typst's smart typography.
    assert 'Odd "name" \\\\ \\*star\\*' in content
    assert 'Say "hi" \\*now\\*' in content


def test_recipe_servings_is_numeric_and_needs_no_escaping(ctx, label_user):
    """`Recipe.servings` is a Float column, which is why it is interpolated raw."""
    recipe = make_recipe(label_user.id, name="Stew", servings=4.0)

    content = typst_utils._generate_typst_content_recipe(recipe, label_nutrients())

    assert 'servings: "4.0"' in content


def test_generate_recipe_label_pdf_renders_markup_hazards(ctx, label_user):
    recipe = make_recipe(
        label_user.id,
        name=MARKUP_HAZARDS,
        instructions=MARKUP_HAZARDS,
    )

    response = typst_utils.generate_recipe_label_pdf(recipe.id)

    assert response.status_code == 200
    assert body_of(response)[:5] == b"%PDF-"


@pytest.mark.parametrize(
    "upc, expected",
    [
        ("2011234567890", "201123456789"),  # internal 13-digit (201 prefix)
        ("044000030293", "004400003029"),  # UPC-A gets a leading zero
        ("5901234123457", "590123412345"),  # plain EAN-13
        ("12345", "000000012345"),  # short code: left-padded (value preserved)
    ],
)
def test_recipe_content_upc_normalisation(ctx, label_user, upc, expected):
    recipe = make_recipe(label_user.id, upc=upc)

    details = typst_utils._generate_typst_content_recipe(recipe, label_nutrients())
    assert f'#ean13(scale:(2.0, .5), "{expected}")' in details

    label = typst_utils._generate_typst_content_recipe(
        recipe, label_nutrients(), label_only=True
    )
    assert f'#ean13(scale:(1.6, .5), "{expected}")' in label


def test_generate_recipe_label_pdf_full_and_label_only(ctx, label_user):
    recipe = make_recipe(label_user.id, instructions="Boil.")

    for label_only in (False, True):
        response = typst_utils.generate_recipe_label_pdf(recipe.id, label_only)
        assert response.status_code == 200
        assert response.mimetype == "application/pdf"
        assert body_of(response)[:5] == b"%PDF-"
        suffix = "label_only" if label_only else "details"
        assert suffix in response.headers["Content-Disposition"]


def test_generate_recipe_label_pdf_sanitises_download_name(ctx, label_user):
    recipe = make_recipe(label_user.id, name="Chili con & Carne!!")

    response = typst_utils.generate_recipe_label_pdf(recipe.id)

    # Non-word characters are dropped, the surrounding spaces survive as underscores.
    assert "Chili_con__Carne" in response.headers["Content-Disposition"]


def test_generate_recipe_label_pdf_unknown_recipe(ctx):
    assert typst_utils.generate_recipe_label_pdf(999999) == ("Recipe not found", 404)


def test_generate_recipe_label_pdf_compile_error(ctx, label_user, monkeypatch):
    recipe = make_recipe(label_user.id)
    raise_called_process_error(monkeypatch, stderr="recipe pdf boom")

    message, status = typst_utils.generate_recipe_label_pdf(recipe.id)
    assert status == 500
    assert "recipe pdf boom" in message


def test_generate_recipe_label_pdf_missing_binary(ctx, label_user, monkeypatch):
    recipe = make_recipe(label_user.id)
    raise_file_not_found(monkeypatch)

    message, status = typst_utils.generate_recipe_label_pdf(recipe.id)
    assert status == 500
    assert message == typst_utils.TYPST_NOT_FOUND_ERROR


def test_generate_recipe_label_svg_unknown_recipe(ctx):
    assert typst_utils.generate_recipe_label_svg(999999) == ("Recipe not found", 404)


def test_generate_recipe_label_svg_compile_error(ctx, label_user, monkeypatch):
    recipe = make_recipe(label_user.id)
    raise_called_process_error(monkeypatch, stderr="recipe svg boom")

    message, status = typst_utils.generate_recipe_label_svg(recipe.id)
    assert status == 500
    assert "Error generating SVG: recipe svg boom" == message


def test_generate_recipe_label_svg_missing_binary(ctx, label_user, monkeypatch):
    recipe = make_recipe(label_user.id)
    raise_file_not_found(monkeypatch)

    message, status = typst_utils.generate_recipe_label_svg(recipe.id)
    assert status == 500
    assert message == typst_utils.TYPST_NOT_FOUND_ERROR
