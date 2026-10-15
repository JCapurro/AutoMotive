"""The hard stop for a hung tick (repairbot.watchdog)."""
from __future__ import annotations

import threading

import pytest

from repairbot import watchdog


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def unarmed():
    watchdog.disarm()
    yield
    watchdog.disarm()


def armed(clock, limit=600.0):
    expired, exited, done = [], [], threading.Event()

    def exit(code):
        exited.append(code)
        done.set()

    thread = watchdog.arm(limit, expired.append, clock=clock, poll=0.01, exit=exit)
    return thread, expired, exited, done


def test_a_tick_past_its_deadline_is_reported_and_ended():
    clock = Clock()
    thread, expired, exited, done = armed(clock)
    clock.now += 601
    assert done.wait(2)
    thread.join(2)
    assert exited == [3] and expired and expired[0] >= 600


def test_extend_gives_real_work_the_long_budget():
    clock = Clock()
    thread, expired, exited, done = armed(clock)
    clock.now += 300
    watchdog.extend(watchdog.LONG_LIMIT_S, clock=clock)
    clock.now += 900                       # well past the idle limit, inside the long one
    assert not done.wait(0.2)
    clock.now += watchdog.LONG_LIMIT_S
    assert done.wait(2) and exited == [3]


def test_extend_never_shortens_the_deadline():
    clock = Clock()
    thread, expired, exited, done = armed(clock, limit=watchdog.LONG_LIMIT_S)
    watchdog.extend(10, clock=clock)
    clock.now += 600
    assert not done.wait(0.2)
    watchdog.disarm()


def test_disarm_ends_the_watch_without_exiting():
    clock = Clock()
    thread, expired, exited, done = armed(clock)
    watchdog.disarm()
    thread.join(2)
    clock.now += 10_000
    assert not thread.is_alive() and exited == [] and expired == []


def test_without_arm_extend_is_a_no_op():
    watchdog.extend(watchdog.LONG_LIMIT_S)
    assert watchdog._deadline is None


def test_an_expire_hook_that_fails_still_ends_the_process():
    clock = Clock()
    exited, done = [], threading.Event()

    def broken(elapsed):
        raise RuntimeError('log roto')

    def exit(code):
        exited.append(code)
        done.set()

    watchdog.arm(600, broken, clock=clock, poll=0.01, exit=exit)
    clock.now += 601
    assert done.wait(2) and exited == [3]
