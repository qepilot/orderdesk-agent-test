from orderdesk.pricing import apply_discount, line_total


def test_line_total():
    assert line_total(3, 1995) == 5985


def test_no_discount():
    assert apply_discount(10000, 0) == 10000


def test_discount_round_numbers():
    assert apply_discount(10000, 10) == 9000
    assert apply_discount(20000, 15) == 17000


def test_discount_rounds_half_up():
    # Added for issue #103: 19.95 with SAVE15 is 16.9575, which must be charged as 16.96.
    assert apply_discount(1995, 15) == 1696
