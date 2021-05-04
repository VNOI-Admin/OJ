EPS = 1e-6


def float_compare_equal(a, b, eps=EPS):
    return abs(a - b) < eps
