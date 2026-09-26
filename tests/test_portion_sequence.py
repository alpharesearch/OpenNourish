"""Portion ordering and the repair command — PLAN.md M6.2's remaining half.

`seq_num` is display order and nothing else, but until 2026-09-26 it was kept up to date by
`ensure_portion_sequence`, which five *read* handlers called. Opening a food page could
therefore renumber an item's entire portion list — including the order a key user had built
with the USDA move routes — and commit it from a GET. It was replaced by two things: a total
ordering on the read side (`seq_num NULLS LAST, gram_weight ASC`), and an operator-run CLI.
Each test here keeps one of those halves honest.
"""

import pathlib

import pytest
from flask import url_for

from models import MyFood, Recipe, UnifiedPortion, User, db
from opennourish.utils import ensure_portion_sequence

SOURCE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "opennourish"


def _my_food(user_id, weights, sequenced=None):
    food = MyFood(description="Ordered food", user_id=user_id)
    db.session.add(food)
    db.session.commit()
    for i, weight in enumerate(weights):
        db.session.add(
            UnifiedPortion(
                my_food_id=food.id,
                gram_weight=weight,
                seq_num=(sequenced or {}).get(i),
            )
        )
    db.session.commit()
    return food


@pytest.fixture
def onboarded_user_id(app_with_db, auth_client_onboarded):
    """The id of the user `auth_client_onboarded` logs in as. Depending on that fixture is
    what makes the user exist — the login fixture creates it when it runs."""
    with app_with_db.app_context():
        return User.query.filter_by(username="onboardeduser").one().id


def test_unsequenced_portions_display_in_weight_order(app_with_db, onboarded_user_id):
    """No write is needed to order a list that has no numbers at all.

    This is the same order the old backfill used to write, which is what made dropping it
    safe: the display does not change, only the fact that somebody has to ask for it.
    """
    with app_with_db.app_context():
        food = _my_food(onboarded_user_id, [30.0, 10.0, 20.0])
        assert [p.gram_weight for p in food.portions] == [10.0, 20.0, 30.0]
        recipe = Recipe(name="Ordered recipe", user_id=onboarded_user_id)
        db.session.add(recipe)
        db.session.commit()
        db.session.add_all(
            [
                UnifiedPortion(recipe_id=recipe.id, gram_weight=30.0),
                UnifiedPortion(recipe_id=recipe.id, gram_weight=10.0),
            ]
        )
        db.session.commit()
        assert [p.gram_weight for p in recipe.portions] == [10.0, 30.0]
        # And nothing was written while ordering them.
        assert (
            UnifiedPortion.query.filter(UnifiedPortion.seq_num.is_not(None)).count()
            == 0
        )


def test_sequenced_portions_keep_their_curated_place(app_with_db, onboarded_user_id):
    """A portion somebody placed by hand outranks a weight-ordered one, whatever its weight."""
    with app_with_db.app_context():
        food = _my_food(onboarded_user_id, [30.0, 10.0, 20.0], sequenced={0: 1})
        assert [p.gram_weight for p in food.portions] == [30.0, 10.0, 20.0]


def test_repair_leaves_curated_numbers_alone(app_with_db, onboarded_user_id):
    """The old backfill renumbered *every* portion of an item as soon as one was NULL, which
    is how it destroyed curated order. Now only the NULL ones move, after the highest number
    already in use, and the return value says how many."""
    with app_with_db.app_context():
        food = _my_food(onboarded_user_id, [30.0, 10.0, 20.0], sequenced={0: 1})
        before = [p.gram_weight for p in food.portions]

        assert ensure_portion_sequence([food]) == 2

        by_weight = {p.gram_weight: p.seq_num for p in food.portions}
        assert by_weight == {30.0: 1, 10.0: 2, 20.0: 3}
        assert [p.gram_weight for p in food.portions] == before


def test_repair_is_a_no_op_when_everything_is_numbered(app_with_db, onboarded_user_id):
    with app_with_db.app_context():
        food = _my_food(onboarded_user_id, [10.0, 20.0], sequenced={0: 1, 1: 2})
        assert ensure_portion_sequence([food]) == 0


REFERENCERS_ALLOWED = {
    # The operator command the helper was moved behind.
    "opennourish/__init__.py",
    # Two POST-only reorder routes: their swap predicate is a seq_num comparison, and
    # `NULL < NULL` matches nothing, so an unsequenced portion has to be numbered in the
    # POST that asked to move it.
    "opennourish/my_foods/routes.py",
}


def test_only_the_command_and_post_reorder_routes_repair_portion_numbers():
    """The invariant, stated where it can rot. Adding a file here means putting a committing
    data repair behind whatever route imports it — which is exactly what five read handlers
    used to do (`test_these_gets_commit_nothing` is the behavioural half)."""
    referencers = {
        str(path.relative_to(SOURCE_ROOT.parent))
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
        if path.name != "utils.py" and "ensure_portion_sequence" in path.read_text()
    }
    assert referencers <= REFERENCERS_ALLOWED, referencers - REFERENCERS_ALLOWED


@pytest.mark.parametrize("direction", ["up", "down"])
def test_moving_an_unsequenced_portion_numbers_it_instead_of_noopping(
    app_with_db, auth_client_onboarded, onboarded_user_id, direction
):
    """Without the backfill, the reorder buttons would answer "already at the top" for a
    portion that merely has no number — a silent regression, so it gets its own test.

    Both directions, because each route carries its own copy of the guard."""
    with app_with_db.app_context():
        food = _my_food(onboarded_user_id, [10.0, 20.0])
        big = [p for p in food.portions if p.gram_weight == 20.0][0]
        portion_id = big.id

    response = auth_client_onboarded.post(
        url_for(f"my_foods.move_my_food_portion_{direction}", portion_id=portion_id)
    )

    assert response.status_code == 302
    with app_with_db.app_context():
        food = db.session.get(MyFood, food.id)
        assert sorted(p.seq_num for p in food.portions) == [1, 2]


@pytest.mark.parametrize(
    "target",
    [
        pytest.param("food_detail", id="main.food_detail"),
        pytest.param("edit_my_food", id="my_foods.edit_my_food"),
        pytest.param("edit_recipe", id="recipes.edit_recipe"),
        pytest.param("view_recipe", id="recipes.view_recipe"),
    ],
)
def test_these_gets_commit_nothing(
    app_with_db,
    auth_client_onboarded,
    onboarded_user_id,
    sample_usda_food,
    target,
    monkeypatch,
):
    """Four of the five call sites were removed from GET handlers; this is the lock.

    `search.search` is deliberately not here — it has its own, separate GET-time write
    (creating the 1 g portion) which is a different inherited defect and still open.

    Patched on the class: undoing an instance-level `db.session` patch leaves a bound
    method behind that shadows every later class patch (`tests/AGENTS.md`).
    """
    with app_with_db.app_context():
        food = _my_food(onboarded_user_id, [10.0])
        recipe = Recipe(name="Committed recipe", user_id=onboarded_user_id)
        db.session.add(recipe)
        db.session.commit()
        urls = {
            "food_detail": url_for("main.food_detail", fdc_id=sample_usda_food.fdc_id),
            "edit_my_food": url_for("my_foods.edit_my_food", food_id=food.id),
            "edit_recipe": url_for("recipes.edit_recipe", recipe_id=recipe.id),
            "view_recipe": url_for("recipes.view_recipe", recipe_id=recipe.id),
        }

    def no_commit(self, *args, **kwargs):
        raise AssertionError(f"a GET handler committed: {target}")

    monkeypatch.setattr("sqlalchemy.orm.scoping.scoped_session.commit", no_commit)

    response = auth_client_onboarded.get(urls[target])

    assert response.status_code == 200


def test_cli_command_numbers_legacy_rows(app_with_db, onboarded_user_id):
    """The repair still exists for whoever wants the numbers materialised — it is just not
    something a page load decides to do."""
    with app_with_db.app_context():
        food = _my_food(onboarded_user_id, [20.0, 10.0])
        food_id = food.id

    result = app_with_db.test_cli_runner().invoke(args=["repair-portion-sequence"])

    assert result.exit_code == 0, result.output
    assert "MyFood: sequenced the portions of 1 item" in result.output
    with app_with_db.app_context():
        # Re-queried: the CLI ran in its own session, so the object above is detached.
        reloaded = db.session.get(MyFood, food_id)
        assert sorted(p.seq_num for p in reloaded.portions) == [1, 2]
