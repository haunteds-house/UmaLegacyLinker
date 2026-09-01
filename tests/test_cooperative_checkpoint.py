from uma_legacy_linker.parent_optimizer import CooperativeCheckpoint, cooperative_checkpoint


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_checkpoint_yields_only_after_elapsed_interval() -> None:
    clock = FakeClock()
    calls: list[float] = []

    def callback() -> None:
        calls.append(clock.now)
        clock.now += 0.050

    checkpoint = CooperativeCheckpoint(
        callback,
        interval_seconds=0.010,
        clock=clock,
    )

    checkpoint()
    clock.now = 0.009
    checkpoint()
    assert calls == []

    clock.now = 0.010
    checkpoint()
    assert calls == [0.010]

    # The next deadline starts after the callback returns, not before its
    # simulated scheduling delay.
    clock.now = 0.069
    checkpoint()
    assert calls == [0.010]
    clock.now = 0.070
    checkpoint()
    assert calls == [0.010, 0.070]


def test_checkpoint_factory_preserves_one_shared_deadline() -> None:
    checkpoint = CooperativeCheckpoint(lambda: None)

    assert cooperative_checkpoint(checkpoint) is checkpoint
    assert callable(cooperative_checkpoint(None))
