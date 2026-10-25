"""B2.10: IP bo'yicha siljuvchi oyna (``upapi.ratelimit``)."""

from upapi.ratelimit import SlidingWindow


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limit_and_window() -> None:
    clock = Clock()
    w = SlidingWindow(2, 60, clock=clock)
    assert [w.hit("a"), w.hit("a"), w.hit("a")] == [True, True, False]
    assert w.hit("b")  # boshqa kalit — alohida
    clock.now += 59
    assert not w.hit("a")  # rad etilgan urinish oynani uzaytirmaydi, lekin hali 60 s o'tmagan
    clock.now += 1
    assert w.hit("a") and w.hit("a") and not w.hit("a")


def test_old_keys_are_pruned() -> None:
    clock = Clock()
    w = SlidingWindow(1, 10, clock=clock)
    for i in range(100):
        w.hit(f"10.0.0.{i}")
    assert len(w._hits) == 100
    clock.now += 11
    w.hit("x")
    assert list(w._hits) == ["x"]
