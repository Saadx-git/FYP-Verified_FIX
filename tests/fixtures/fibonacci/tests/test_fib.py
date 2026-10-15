from fib import fib


def test_base_cases():
    assert (fib(0), fib(1)) == (0, 1)


def test_fib_2():
    assert fib(2) == 1


def test_fib_3():
    assert fib(3) == 2


def test_fib_10():
    assert fib(10) == 55


def test_sequence():
    assert [fib(i) for i in range(8)] == [0, 1, 1, 2, 3, 5, 8, 13]
