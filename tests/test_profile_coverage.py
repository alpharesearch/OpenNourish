"""Coverage tests for ``opennourish/profile/routes.py``.

Complements ``tests/test_profile.py``: the own-visit render path, the read-only
friend diary with real diary rows, every ``time_range`` branch, the
friendship-state transitions that gate cross-user reads, and every flash branch
of ``copy_log_from_friend``.

Authorisation contract under test (root ``AGENTS.md``): an *accepted*
``Friendship`` is the only read gate for another user's data. ``is_private``
only hides an account from the friend search in ``friends/routes.py``, and
``is_verified`` only gates *sending* friend requests.

Test-client note: test clients on one app instance share the session cookie, so
each test drives exactly one principal (the fixture's); the counterparty side of
an authorisation rule is exercised by seeding the row from that side and
asserting the effect on the fixture user's read.
"""

import re
from datetime import timedelta

from models import (
    CheckIn,
    DailyLog,
    ExerciseActivity,
    ExerciseLog,
    Friendship,
    MyFood,
    Recipe,
    UnifiedPortion,
    User,
    UserGoal,
    db,
)
from opennourish.time_utils import get_user_today

TODAY = get_user_today("UTC")  # every fixture user has the default UTC timezone


def make_user(username, **kwargs):
    """Create a minimal user; ``email`` is NOT NULL so it is derived here."""
    user = User(username=username, email=f"{username}@example.com", **kwargs)
    user.set_password("password")
    db.session.add(user)
    db.session.commit()
    return user


def make_friendship(requester, receiver, status="accepted"):
    friendship = Friendship(
        requester_id=requester.id, receiver_id=receiver.id, status=status
    )
    db.session.add(friendship)
    db.session.commit()
    return friendship


def collapsed_text(response):
    """Rendered page with markup whitespace collapsed to single spaces."""
    return re.sub(r"\s+", " ", response.data.decode("utf-8"))


def flashes(client):
    with client.session_transaction() as sess:
        return list(sess.get("_flashes", []))


# ----------------------------------------------------------- own-visit paths


def test_own_dashboard_visit_needs_no_friendship(auth_client):
    """The own-username visit returns before the friendship query."""
    response = auth_client.get("/user/testuser/dashboard")

    assert response.status_code == 200
    assert "Nutritional Summary" in response.data.decode("utf-8")
    assert b'<form action="/goals/update"' not in response.data
    # No UserGoal row -> the temporary 2000 kcal default goal is used.
    assert "Goal: 2000.0 kcal" in response.data.decode("utf-8")


def test_own_diary_visit_needs_no_friendship(auth_client):
    response = auth_client.get("/user/testuser/diary")

    assert response.status_code == 200
    assert "Food Diary" in response.data.decode("utf-8")
    assert "No items logged for this meal." in response.data.decode("utf-8")
    assert b"diary/update_entry" not in response.data
    assert b"diary/delete_log" not in response.data


def test_own_copy_log_copies_into_own_diary(auth_client):
    """A self visit resolves the same user, so copying one's own row is allowed."""
    user = User.query.filter_by(username="testuser").first()
    own_log = DailyLog(
        user_id=user.id,
        log_date=TODAY,
        meal_name="Breakfast",
        amount_grams=120,
        fdc_id=12345,
    )
    db.session.add(own_log)
    db.session.commit()

    target_date = TODAY + timedelta(days=1)
    response = auth_client.post(
        "/user/testuser/copy_log",
        data={
            "log_id": own_log.id,
            "target_date": target_date.isoformat(),
            "target_meal_name": "Lunch",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert f"/diary/{target_date.isoformat()}" in response.headers["Location"]
    assert response.headers["Location"].endswith("#meal-lunch")
    assert flashes(auth_client) == [
        ("success", "Successfully copied item from testuser's diary.")
    ]

    copied = DailyLog.query.filter_by(
        user_id=user.id, log_date=target_date, meal_name="Lunch"
    ).one()
    assert copied.amount_grams == 120
    assert copied.fdc_id == 12345


# ------------------------------------------- goal lookup regression (user_id)


def test_friend_goal_is_resolved_by_user_id_not_primary_key(
    auth_client_with_friendship,
):
    """Regression for the wrong-PK ``UserGoal`` lookup.

    ``UserGoal.id`` is a surrogate key; ``user_id`` is the owner. The decoy goal
    deliberately occupies the primary key equal to ``friend_user.id``, so the
    old ``db.session.get(UserGoal, friend_user.id)`` returns another account's
    goal row.
    """
    client, _test_user, friend_user = auth_client_with_friendship

    decoy_user = make_user("decoy_goal_owner")
    decoy_goal = UserGoal(
        id=friend_user.id,
        user_id=decoy_user.id,
        calories=9999,
        protein=333,
        carbs=444,
        fat=111,
    )
    friend_goal = UserGoal(
        user_id=friend_user.id, calories=1234, protein=99, carbs=150, fat=44
    )
    db.session.add_all([decoy_goal, friend_goal])
    db.session.commit()

    # Precondition that makes the lookup meaningful: the surrogate keys are
    # skewed, so the friend's own row is NOT keyed by the friend's user id.
    assert decoy_goal.id == friend_user.id
    assert friend_goal.id != friend_user.id

    dashboard = client.get(f"/user/{friend_user.username}/dashboard")
    assert dashboard.status_code == 200
    assert "Goal: 1234.0 kcal" in dashboard.data.decode("utf-8")
    assert b"Goal: 9999.0 kcal" not in dashboard.data

    diary = client.get(f"/user/{friend_user.username}/diary")
    assert diary.status_code == 200
    assert "Goal: 1234.0 kcal" in diary.data.decode("utf-8")
    assert b"Goal: 9999.0 kcal" not in diary.data


def test_friend_without_goal_falls_back_to_default_goal(auth_client_with_friendship):
    client, _test_user, friend_user = auth_client_with_friendship

    response = client.get(f"/user/{friend_user.username}/dashboard")

    assert response.status_code == 200
    assert "Goal: 2000.0 kcal" in response.data.decode("utf-8")


# ------------------------------------------------- friendship as the read gate


def test_pending_request_does_not_grant_read(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users
    make_friendship(user_one, user_two, status="pending")

    for path in (
        f"/user/{user_two.username}/dashboard",
        f"/user/{user_two.username}/diary",
    ):
        response = client.get(path, follow_redirects=True)

        assert response.status_code == 200
        assert b"You are not friends with user_two." in response.data
        assert "/friends" in response.request.path
        assert b"Nutritional Summary" not in response.data


def test_incoming_request_declined_keeps_profile_hidden(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users
    incoming = make_friendship(user_two, user_one, status="pending")

    declined = client.post(
        f"/friends/request/{incoming.id}/decline", follow_redirects=True
    )
    assert b"Friend request declined." in declined.data
    assert db.session.get(Friendship, incoming.id) is None

    response = client.get(f"/user/{user_two.username}/dashboard", follow_redirects=True)
    assert b"You are not friends with user_two." in response.data


def test_incoming_request_accepted_grants_profile_read(auth_client_two_users):
    """pending -> accepted is the transition that opens the read gate."""
    client, user_one, user_two = auth_client_two_users
    incoming = make_friendship(user_two, user_one, status="pending")

    denied = client.get(f"/user/{user_two.username}/diary", follow_redirects=True)
    assert b"You are not friends with user_two." in denied.data

    accepted = client.post(
        f"/friends/request/{incoming.id}/accept", follow_redirects=True
    )
    assert b"Friend request accepted." in accepted.data
    assert db.session.get(Friendship, incoming.id).status == "accepted"

    allowed = client.get(f"/user/{user_two.username}/diary")
    assert allowed.status_code == 200
    assert "Food Diary" in allowed.data.decode("utf-8")


def test_reverse_direction_accepted_friendship_grants_read(auth_client_two_users):
    """The friendship check is symmetric: requester-side rows count too."""
    client, user_one, user_two = auth_client_two_users
    make_friendship(user_two, user_one, status="accepted")

    response = client.get(f"/user/{user_two.username}/diary")

    assert response.status_code == 200
    assert "Food Diary" in response.data.decode("utf-8")


def test_private_flag_hides_from_search_but_not_from_profile_read(
    auth_client_two_users,
):
    """``is_private`` is NOT a read gate; it only hides the friend search."""
    client, user_one, user_two = auth_client_two_users
    user_two.is_private = True
    db.session.commit()
    make_friendship(user_one, user_two, status="accepted")

    response = client.get(f"/user/{user_two.username}/dashboard")
    assert response.status_code == 200
    assert "Nutritional Summary" in response.data.decode("utf-8")

    response = client.post(
        "/friends/add", data={"username": "user_two"}, follow_redirects=True
    )
    assert b"User not found." in response.data
    assert Friendship.query.filter_by(requester_id=user_one.id).count() == 1


def test_unknown_username_returns_404(auth_client):
    for path in (
        "/user/nosuchuser/dashboard",
        "/user/nosuchuser/diary",
        "/user/nosuchuser/diary/2024-01-01",
    ):
        assert auth_client.get(path).status_code == 404

    assert auth_client.post("/user/nosuchuser/copy_log", data={}).status_code == 404


# ---------------------------------------------- dashboard data and time ranges


def test_dashboard_time_range_filters_check_ins(auth_client_with_friendship):
    client, _test_user, friend_user = auth_client_with_friendship
    db.session.add_all(
        [
            CheckIn(
                user_id=friend_user.id,
                checkin_date=TODAY - timedelta(days=3),
                weight_kg=81.5,
                body_fat_percentage=22.0,
                waist_cm=91.0,
            ),
            CheckIn(
                user_id=friend_user.id,
                checkin_date=TODAY - timedelta(days=200),
                weight_kg=61.25,
            ),
        ]
    )
    db.session.commit()
    base = f"/user/{friend_user.username}/dashboard"

    one_month = client.get(f"{base}?time_range=1_month")
    assert one_month.status_code == 200
    assert b"81.5" in one_month.data
    assert b"61.25" not in one_month.data

    for time_range in ("3_month", "6_month", "1_year"):
        response = client.get(f"{base}?time_range={time_range}")
        assert response.status_code == 200
        assert b"81.5" in response.data

    all_time = client.get(f"{base}?time_range=all_time")
    assert all_time.status_code == 200
    assert b"81.5" in all_time.data
    assert b"61.25" in all_time.data


def test_dashboard_shows_friend_logged_food_names(
    auth_client_with_friendship, sample_usda_food
):
    client, _test_user, friend_user = auth_client_with_friendship
    activity = ExerciseActivity(name="Cycling", met_value=7.5)
    my_food = MyFood(
        user_id=friend_user.id,
        description="Friend Custom Food",
        calories_per_100g=250.0,
        protein_per_100g=10.0,
    )
    db.session.add_all([activity, my_food])
    db.session.commit()

    db.session.add_all(
        [
            DailyLog(
                user_id=friend_user.id,
                log_date=TODAY,
                meal_name="Breakfast",
                fdc_id=sample_usda_food.fdc_id,
                amount_grams=100,
            ),
            DailyLog(
                user_id=friend_user.id,
                log_date=TODAY,
                meal_name="Lunch",
                my_food_id=my_food.id,
                amount_grams=200,
            ),
            # A dangling fdc_id resolves to no food, so it contributes no name.
            DailyLog(
                user_id=friend_user.id,
                log_date=TODAY,
                meal_name="Dinner",
                fdc_id=999999,
                amount_grams=50,
            ),
            ExerciseLog(
                user_id=friend_user.id,
                log_date=TODAY,
                activity_id=activity.id,
                duration_minutes=30,
                calories_burned=250,
            ),
        ]
    )
    db.session.commit()

    response = client.get(f"/user/{friend_user.username}/dashboard/{TODAY.isoformat()}")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert sample_usda_food.description in body
    assert "Friend Custom Food" in body
    assert "Cycling" in body


def test_dashboard_other_date_is_not_today(auth_client_with_friendship):
    client, _test_user, friend_user = auth_client_with_friendship
    db.session.add(
        DailyLog(
            user_id=friend_user.id,
            log_date=TODAY,
            meal_name="Breakfast",
            fdc_id=12345,
            amount_grams=100,
        )
    )
    db.session.commit()

    yesterday = TODAY - timedelta(days=1)
    response = client.get(
        f"/user/{friend_user.username}/dashboard/{yesterday.isoformat()}"
    )

    assert response.status_code == 200
    # The "next day" arrow is derived from the viewed date, which proves the
    # page renders `yesterday` and not the default today.
    assert f"/user/{friend_user.username}/dashboard/{TODAY.isoformat()}".encode() in (
        response.data
    )


# ------------------------------------------------- read-only diary rendering


def test_friend_diary_renders_every_item_kind_read_only(
    auth_client_with_friendship, sample_usda_food
):
    client, _test_user, friend_user = auth_client_with_friendship

    portion = UnifiedPortion(
        fdc_id=sample_usda_food.fdc_id,
        seq_num=1,
        amount=1.0,
        measure_unit_description="cup",
        portion_description="sliced",
        gram_weight=100.0,
    )
    my_food = MyFood(
        user_id=friend_user.id,
        description="Friend Custom Food",
        calories_per_100g=250.0,
        protein_per_100g=10.0,
    )
    recipe = Recipe(user_id=friend_user.id, name="Friend Recipe", servings=2.0)
    db.session.add_all([portion, my_food, recipe])
    db.session.commit()

    db.session.add_all(
        [
            DailyLog(
                user_id=friend_user.id,
                log_date=TODAY,
                meal_name="Breakfast",
                fdc_id=sample_usda_food.fdc_id,
                amount_grams=200,
                portion_id_fk=portion.id,
            ),
            DailyLog(
                user_id=friend_user.id,
                log_date=TODAY,
                meal_name="Lunch",
                my_food_id=my_food.id,
                amount_grams=100,
            ),
            # Recipes expose ``name``, not ``description``.
            DailyLog(
                user_id=friend_user.id,
                log_date=TODAY,
                meal_name="Dinner",
                recipe_id=recipe.id,
                amount_grams=150,
            ),
            # A meal name that is not pre-seeded in the route's meals dict.
            DailyLog(
                user_id=friend_user.id,
                log_date=TODAY,
                meal_name="Water",
                my_food_id=my_food.id,
                amount_grams=300,
            ),
            # No meal name at all -> the "Unspecified" bucket.
            DailyLog(
                user_id=friend_user.id,
                log_date=TODAY,
                meal_name=None,
                fdc_id=sample_usda_food.fdc_id,
                amount_grams=50,
            ),
            # Item whose food row cannot be resolved.
            DailyLog(
                user_id=friend_user.id,
                log_date=TODAY,
                meal_name="Snack (morning)",
                fdc_id=999999,
                amount_grams=25,
            ),
            ExerciseLog(
                user_id=friend_user.id,
                log_date=TODAY,
                manual_description="Walking",
                duration_minutes=20,
                calories_burned=100,
            ),
        ]
    )
    db.session.commit()

    response = client.get(f"/user/{friend_user.username}/diary/{TODAY.isoformat()}")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Food Diary" in body
    assert sample_usda_food.description in body
    assert "Friend Custom Food" in body
    assert "Friend Recipe" in body
    assert "Unknown Food" in body
    assert "Unspecified" in body
    text = collapsed_text(response)
    # 200 g logged against a 100 g portion -> 2.0 portions, 200 g total.
    assert "2.0 cup sliced" in text
    assert "(200g)" in text
    # Read-only: no editing controls, but the friend copy affordances are there.
    assert b"diary/update_entry" not in response.data
    assert b"diary/delete_log" not in response.data
    assert b'<form action="/diary/save_meal"' not in response.data
    assert "Direct Copy" in body


def test_friend_diary_empty_other_date(auth_client_with_friendship):
    client, _test_user, friend_user = auth_client_with_friendship

    response = client.get(
        f"/user/{friend_user.username}/diary/{(TODAY - timedelta(days=5)).isoformat()}"
    )

    assert response.status_code == 200
    assert b"No items logged for this meal." in response.data


# --------------------------------------------------------- copy_log flashes


def test_copy_log_rejects_unknown_entry(auth_client_with_friendship):
    client, _test_user, friend_user = auth_client_with_friendship

    response = client.post(
        f"/user/{friend_user.username}/copy_log",
        data={
            "log_id": 424242,
            "target_date": TODAY.isoformat(),
            "target_meal_name": "Lunch",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"Diary entry not found or it does not belong to the specified user."
        in response.data
    )
    assert f"/user/{friend_user.username}/diary" in response.request.path
    assert DailyLog.query.count() == 0


def test_copy_log_rejects_entry_of_another_user(auth_client_with_friendship):
    client, _test_user, friend_user = auth_client_with_friendship
    outsider = make_user("outsider_log_owner")
    outsider_log = DailyLog(
        user_id=outsider.id,
        log_date=TODAY,
        meal_name="Breakfast",
        amount_grams=100,
        fdc_id=12345,
    )
    db.session.add(outsider_log)
    db.session.commit()

    response = client.post(
        f"/user/{friend_user.username}/copy_log",
        data={
            "log_id": outsider_log.id,
            "target_date": TODAY.isoformat(),
            "target_meal_name": "Lunch",
        },
        follow_redirects=True,
    )

    assert (
        b"Diary entry not found or it does not belong to the specified user."
        in response.data
    )
    assert DailyLog.query.count() == 1


def test_copy_log_rolls_back_on_unparsable_target_date(auth_client_with_friendship):
    client, test_user, friend_user = auth_client_with_friendship
    friend_log = DailyLog(
        user_id=friend_user.id,
        log_date=TODAY,
        meal_name="Breakfast",
        amount_grams=100,
        fdc_id=12345,
    )
    db.session.add(friend_log)
    db.session.commit()

    response = client.post(
        f"/user/{friend_user.username}/copy_log",
        data={
            "log_id": friend_log.id,
            "target_date": "not-a-date",
            "target_meal_name": "Lunch",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"An error occurred while copying the entry:" in response.data
    assert f"/user/{friend_user.username}/diary" in response.request.path
    assert DailyLog.query.filter_by(user_id=test_user.id).count() == 0


def test_copy_log_by_non_friend_is_rejected_without_creating_rows(
    auth_client_two_users,
):
    client, user_one, user_two = auth_client_two_users
    stranger_log = DailyLog(
        user_id=user_two.id,
        log_date=TODAY,
        meal_name="Breakfast",
        amount_grams=100,
        fdc_id=12345,
    )
    db.session.add(stranger_log)
    db.session.commit()

    response = client.post(
        f"/user/{user_two.username}/copy_log",
        data={
            "log_id": stranger_log.id,
            "target_date": TODAY.isoformat(),
            "target_meal_name": "Lunch",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"You are not friends with user_two." in response.data
    assert b"Friend not found or you do not have permission" in response.data
    assert DailyLog.query.filter_by(user_id=user_one.id).count() == 0


# ------------------------------------- friend-request lifecycle around profile


def test_verified_gate_blocks_sending_only(app_with_db, auth_client_two_users):
    """``is_verified`` gates sending a request, never reading a profile."""
    client, user_one, user_two = auth_client_two_users
    app_with_db.config["ENABLE_EMAIL_VERIFICATION"] = True

    blocked = client.post(
        "/friends/add", data={"username": "user_two"}, follow_redirects=True
    )
    assert b"Please verify your email address to send friend requests." in blocked.data
    assert Friendship.query.count() == 0

    user_one.is_verified = True
    db.session.commit()
    sent = client.post(
        "/friends/add", data={"username": "user_two"}, follow_redirects=True
    )
    assert b"Friend request sent to user_two." in sent.data
    assert Friendship.query.filter_by(status="pending").count() == 1


def test_cannot_add_self_or_double_request(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    no_username = client.post("/friends/add", data={}, follow_redirects=True)
    assert b"Username is required." in no_username.data

    unknown = client.post(
        "/friends/add", data={"username": "ghost"}, follow_redirects=True
    )
    assert b"User not found." in unknown.data

    self_add = client.post(
        "/friends/add", data={"username": "user_one"}, follow_redirects=True
    )
    assert b"You cannot add yourself as a friend." in self_add.data

    sent = client.post(
        "/friends/add", data={"username": "user_two"}, follow_redirects=True
    )
    assert b"Friend request sent to user_two." in sent.data

    duplicate = client.post(
        "/friends/add", data={"username": "user_two"}, follow_redirects=True
    )
    assert b"Friendship already exists or is pending." in duplicate.data
    assert Friendship.query.count() == 1
    assert Friendship.query.filter_by(status="pending").count() == 1


def test_cancel_outgoing_request_then_resend(auth_client_two_users):
    """Declining one's own outgoing request is the cancel transition."""
    client, user_one, user_two = auth_client_two_users
    outgoing = make_friendship(user_one, user_two, status="pending")

    cancelled = client.post(
        f"/friends/request/{outgoing.id}/decline", follow_redirects=True
    )
    assert b"Friend request declined." in cancelled.data
    assert Friendship.query.count() == 0

    resent = client.post(
        "/friends/add", data={"username": "user_two"}, follow_redirects=True
    )
    assert b"Friend request sent to user_two." in resent.data
    assert Friendship.query.filter_by(status="pending").count() == 1


def test_accept_and_decline_error_branches(auth_client_two_users):
    client, _user_one, _user_two = auth_client_two_users
    stranger = make_user("stranger_a")
    other = make_user("stranger_b")
    someone_elses = make_friendship(stranger, other, status="pending")

    missing_accept = client.post(
        "/friends/request/999999/accept", follow_redirects=True
    )
    assert b"Friend request not found." in missing_accept.data

    forbidden_accept = client.post(
        f"/friends/request/{someone_elses.id}/accept", follow_redirects=True
    )
    assert (
        b"You do not have permission to perform this action." in forbidden_accept.data
    )
    assert someone_elses.status == "pending"

    missing_decline = client.post(
        "/friends/request/999999/decline", follow_redirects=True
    )
    assert b"Friend request not found." in missing_decline.data

    forbidden_decline = client.post(
        f"/friends/request/{someone_elses.id}/decline", follow_redirects=True
    )
    assert (
        b"You do not have permission to perform this action." in forbidden_decline.data
    )
    assert Friendship.query.count() == 1


def test_remove_friend_revokes_profile_read(auth_client_with_friendship):
    client, test_user, friend_user = auth_client_with_friendship
    friendship = Friendship.query.filter_by(
        requester_id=test_user.id, receiver_id=friend_user.id
    ).first()

    removed = client.post(
        f"/friends/friendship/{friend_user.id}/remove", follow_redirects=True
    )
    assert b"Friend removed." in removed.data
    assert db.session.get(Friendship, friendship.id) is None

    denied = client.get(f"/user/{friend_user.username}/diary", follow_redirects=True)
    assert b"You are not friends with frienduser_friendship." in denied.data

    unknown = client.post("/friends/friendship/999999/remove")
    assert unknown.status_code == 404
