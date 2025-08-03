import pytest
from opennourish.utils import (
    cm_to_ft_in,
    ft_in_to_cm,
    kg_to_lbs,
    lbs_to_kg,
    cm_to_in,
    in_to_cm,
    get_display_weight,
    get_display_waist,
    get_display_height,
)


# Test cm_to_ft_in
def test_cm_to_ft_in():
    assert cm_to_ft_in(180) == (5, pytest.approx(10.9, abs=0.1))
    assert cm_to_ft_in(0) == (0, 0)
    assert cm_to_ft_in(None) == (None, None)
    assert cm_to_ft_in(152.4) == (5, pytest.approx(0.0, abs=0.1))


# Test ft_in_to_cm
def test_ft_in_to_cm():
    assert ft_in_to_cm(5, 10.9) == pytest.approx(180.0, abs=0.1)
    assert ft_in_to_cm(None, 10) is None
    assert ft_in_to_cm(5, None) is None
    assert ft_in_to_cm(5, 0) == pytest.approx(152.4, abs=0.1)


# Test kg_to_lbs
def test_kg_to_lbs():
    assert kg_to_lbs(70) == pytest.approx(154.32, abs=0.01)
    assert kg_to_lbs(0) == pytest.approx(0.0, abs=0.01)
    assert kg_to_lbs(None) is None


# Test lbs_to_kg
def test_lbs_to_kg():
    assert lbs_to_kg(154.32) == pytest.approx(70.0, abs=0.01)
    assert lbs_to_kg(0) == pytest.approx(0.0, abs=0.01)
    assert lbs_to_kg(None) is None


# Test cm_to_in
def test_cm_to_in():
    assert cm_to_in(76.2) == pytest.approx(30.0, abs=0.01)
    assert cm_to_in(0) == pytest.approx(0.0, abs=0.01)
    assert cm_to_in(None) is None


# Test in_to_cm
def test_in_to_cm():
    assert in_to_cm(30) == pytest.approx(76.2, abs=0.01)
    assert in_to_cm(0) == pytest.approx(0.0, abs=0.01)
    assert in_to_cm(None) is None


# Test get_display_weight
def test_get_display_weight():
    assert get_display_weight(70, "us") == pytest.approx(154.32, abs=0.01)
    assert get_display_weight(70, "metric") == 70
    assert get_display_weight(None, "us") is None


# Test get_display_waist
def test_get_display_waist():
    assert get_display_waist(76.2, "us") == pytest.approx(30.0, abs=0.01)
    assert get_display_waist(76.2, "metric") == 76.2
    assert get_display_waist(None, "us") is None


# Test get_display_height
def test_get_display_height():
    assert get_display_height(180, "us") == (5, pytest.approx(10.9, abs=0.1))
    assert get_display_height(180, "metric") == 180
    assert get_display_height(None, "us") == (None, None)
