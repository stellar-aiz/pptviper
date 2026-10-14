"""Independent reference values for WCAG and CIEDE2000 calculations."""

import pytest

from pptviper.color_math import composite, contrast, delta_e_2000, lab


def test_wcag_reference_values():
    assert contrast((0, 0, 0), (255, 255, 255)) == 21
    assert contrast((12, 30, 45), (12, 30, 45)) == 1
    assert composite((255, 255, 255), 0.5, (0, 0, 0)) == (127.5, 127.5, 127.5)
    assert contrast((255, 255, 255), (127.5, 127.5, 127.5)) == pytest.approx(
        3.976653, abs=1e-6
    )


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((50, 2.6772, -79.7751), (50, 0, -82.7485), 2.0425),
        ((50, 3.1571, -77.2803), (50, 0, -82.7485), 2.8615),
        ((50, 2.8361, -74.0200), (50, 0, -82.7485), 3.4412),
        ((50, -1.3802, -84.2814), (50, 0, -82.7485), 1.0000),
        ((50, 0, 0), (50, -1, 2), 2.3669),
    ],
)
def test_sharma_reference_pairs(a, b, expected):
    assert delta_e_2000(a, b) == pytest.approx(expected, abs=0.00005)
    assert delta_e_2000(b, a) == pytest.approx(expected, abs=0.00005)


def test_srgb_to_lab():
    assert lab((0, 0, 0)) == (0, 0, 0)
    assert lab((255, 255, 255)) == pytest.approx((100, 0, 0), abs=0.001)
