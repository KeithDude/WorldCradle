import pytest

import ports
from games.base import ActionError


def test_alloc_skips_used_ports_and_reserves_them():
    used = {7777, 7778}
    assert ports.alloc("game", 7777, used) == 7779
    assert 7779 in used


def test_alloc_span_needs_a_free_block():
    used = {7778}
    assert ports.alloc("game", 7777, used, span=2) == 7779      # 7777-7778 is broken by 7778
    assert {7779, 7780} <= used


def test_claim_refuses_privileged_taken_and_garbage():
    with pytest.raises(ActionError):
        ports.claim(80, set())
    with pytest.raises(ActionError):
        ports.claim(7777, {7777})
    with pytest.raises(ActionError):
        ports.claim("not a port", set())
    used = set()
    assert ports.claim(" 8211 ", used, span=2) == 8211 and {8211, 8212} <= used
