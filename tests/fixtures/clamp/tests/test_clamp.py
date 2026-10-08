from mathx.clamp import clamp


def test_clamp_high():
    assert clamp(15, 0, 10) == 10


def test_in_range_unchanged():
    assert clamp(5, 0, 10) == 5
