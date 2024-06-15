import json
import pytest
import vanillapoker.poker as poker
from unittest.mock import AsyncMock, patch

@pytest.fixture
def t6():
    with patch.object(poker.PokerTable, 'start_turn_timeout', new_callable=AsyncMock), \
         patch.object(poker.PokerTable, 'reset_timeout', new_callable=AsyncMock):
        yield poker.PokerTable(0, 1, 2, 40, 400, 6)

@pytest.fixture
def t2():
    with patch.object(poker.PokerTable, 'start_turn_timeout', new_callable=AsyncMock), \
         patch.object(poker.PokerTable, 'reset_timeout', new_callable=AsyncMock):
        yield poker.PokerTable(0, 1, 2, 40, 400, 2)



@pytest.mark.asyncio
async def test_increment_hand_history(t2):
    t2.events.append("e1")
    t2.events.append("e2")
    assert t2.hand_histories[1] == ["e1", "e2"]
    assert t2.hand_id == 1

    t2._increment_hand_history()
    assert t2.hand_histories[1] == ["e1", "e2"]
    assert t2.hand_id == 2
    assert t2.hand_histories[2] == []

    t2.events.append("e3")
    assert t2.hand_histories[1] == ["e1", "e2"]
    assert t2.hand_id == 2
    assert t2.hand_histories[2] == ["e3"]


@pytest.mark.asyncio
async def test_join_table(t6):
    # Join at a seat that is not 0
    assert t6.seats[2] is None
    t6.join_table(2, 100, "0x123")
    assert t6.seats[2] is not None


@pytest.mark.asyncio
async def test_no_bad_join_tables(t6):
    # Join at a seat that is not 0
    t6.join_table(2, 100, "0x123")
    # Same player Joining at same or different seat should fail..
    with pytest.raises(AssertionError):
        t6.join_table(2, 100, "0x123")
    with pytest.raises(AssertionError):
        t6.join_table(0, 100, "0x123")
    # Different player joining at same seat should fail
    with pytest.raises(AssertionError):
        t6.join_table(2, 100, "0x456")
    # Joining at an out of bounds index should fail
    with pytest.raises(AssertionError):
        t6.join_table(-1, 100, "0x456")
    with pytest.raises(AssertionError):
        t6.join_table(9, 100, "0x456")
    # Bad buying amount should fail
    with pytest.raises(AssertionError):
        t6.join_table(1, 100000, "0x456")
    with pytest.raises(AssertionError):
        t6.join_table(1, 1, "0x456")


@pytest.mark.asyncio
async def test_leave_table(t6):
    t6.join_table(0, 100, "0x123")
    assert t6.seats[0] is not None
    t6.leave_table(0, "0x123")
    assert t6.seats[0] is None


@pytest.mark.asyncio
async def test_rebuy(t6):
    t6.join_table(0, 100, "0x123")
    # SHoudl be able to rebuy for max of 100 more
    t6.rebuy(0, 100, "0x123")
    assert t6.seats[0]["stack"] == 200


@pytest.mark.asyncio
async def test_auto_post_blinds(t6):
    """
    If two players join, check that the blinds are auto posted
    """
    t6.join_table(0, 100, "0x123")
    t6.join_table(1, 100, "0x456")
    # Blinds are 1/2, should be total of 3 in pot
    # Should be at HS_PREFLOP_BETTING stage,
    # With 1 and 2 bet
    assert t6.hand_stage == poker.HS_PREFLOP_BETTING
    assert t6.seats[0]["stack"] == 99
    assert t6.seats[1]["stack"] == 98
    assert t6.seats[0]["bet_street"] == 1
    assert t6.seats[1]["bet_street"] == 2
    assert len(t6.seats[0]["holecards"]) == 2
    assert len(t6.seats[1]["holecards"]) == 2


@pytest.mark.asyncio
async def test_integration_2p_showdown(t2, t6):
    """
    Play a full hand - both players join, play, then quit...
    """
    t = t6
    # Will always be a tie, think it's ok?
    t._get_showdown_val = lambda x: 10
    p0 = "0x123"
    p1 = "0x456"
    t.join_table(0, 100, p0, False)
    t.join_table(1, 100, p1, False)

    t.take_action(poker.ACT_SB_POST, p0, 1)
    t.take_action(poker.ACT_BB_POST, p1, 2)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CALL, p0, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CHECK, p1, 0)

    assert t.hand_stage == poker.HS_FLOP_BETTING
    assert len(t.board) == 3

    t.take_action(poker.ACT_BET, p0, 5)
    t.take_action(poker.ACT_BET, p1, 10)
    t.take_action(poker.ACT_CALL, p0, 0)

    assert t.hand_stage == poker.HS_TURN_BETTING
    assert len(t.board) == 4

    t.take_action(poker.ACT_CHECK, p0, 0)
    t.take_action(poker.ACT_CHECK, p1, 0)

    assert t.hand_stage == poker.HS_RIVER_BETTING
    assert len(t.board) == 5

    t.take_action(poker.ACT_BET, p0, 5)
    t.take_action(poker.ACT_CALL, p1, 0)

    # Should have completed showdown and settle!
    assert t.hand_stage == poker.HS_SB_POST_STAGE
    # It was a split pot, so both should have 100
    assert t.seats[0]["stack"] == 100
    assert t.seats[1]["stack"] == 100


@pytest.mark.asyncio
async def test_integration_2p_fold(t2, t6):
    t = t6
    # Will always be a tie, think it's ok?
    t._get_showdown_val = lambda x: 10
    p0 = "0x123"
    p1 = "0x456"
    t.join_table(0, 100, p0, False)
    t.join_table(1, 100, p1, False)

    t.take_action(poker.ACT_SB_POST, p0, 1)
    t.take_action(poker.ACT_BB_POST, p1, 2)
    t.take_action(poker.ACT_FOLD, p0, 0)

    # After the fold it should progress all the way to the end and credit winnings to p1
    assert t.hand_stage == poker.HS_SB_POST_STAGE
    # It was a split pot, so both should have 100
    assert t.seats[0]["stack"] == 99
    assert t.seats[1]["stack"] == 101


@pytest.mark.asyncio
async def test_integration_2p_allin(t2, t6):
    t = t6
    # Will always be a tie, think it's ok?
    t._get_showdown_val = lambda x: 10
    p0 = "0x123"
    p1 = "0x456"
    t.join_table(0, 100, p0, False)
    t.join_table(1, 100, p1, False)

    # Check that the seats have been correctly initialized
    assert t.seats[0] is not None
    assert t.seats[1] is not None

    t.take_action(poker.ACT_SB_POST, p0, 1)
    t.take_action(poker.ACT_BB_POST, p1, 2)
    t.take_action(poker.ACT_BET, p0, 100)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CALL, p1, 0)

    # After the fold it should progress all the way to the end and credit winnings to p1
    assert t.hand_stage == poker.HS_SB_POST_STAGE
    # It was a split pot, so both should have 100
    assert t.seats[0]["stack"] == 100
    assert t.seats[1]["stack"] == 100


@pytest.mark.asyncio
async def test_integration_3p_showdown(t6):
    t = t6
    t._get_showdown_val = lambda x: 10
    p0 = "0x123"
    p1 = "0x456"
    p2 = "0x789"
    t.join_table(0, 100, p0, False)
    t.join_table(1, 100, p1, False)
    t.join_table(2, 100, p2, False)

    t.take_action(poker.ACT_SB_POST, p0, 1)
    t.take_action(poker.ACT_BB_POST, p1, 2)
    t.take_action(poker.ACT_CALL, p2, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CALL, p0, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CHECK, p1, 0)
    assert t.hand_stage == poker.HS_FLOP_BETTING
    assert len(t.board) == 3

    t.take_action(poker.ACT_BET, p0, 10)
    t.take_action(poker.ACT_BET, p1, 20)
    t.take_action(poker.ACT_CALL, p2, 0)
    t.take_action(poker.ACT_CALL, p0, 0)
    assert t.hand_stage == poker.HS_TURN_BETTING
    assert len(t.board) == 4

    t.take_action(poker.ACT_CHECK, p0, 0)
    t.take_action(poker.ACT_CHECK, p1, 0)
    t.take_action(poker.ACT_CHECK, p2, 0)
    assert t.hand_stage == poker.HS_RIVER_BETTING
    assert len(t.board) == 5

    t.take_action(poker.ACT_BET, p0, 5)
    t.take_action(poker.ACT_CALL, p1, 0)
    t.take_action(poker.ACT_CALL, p2, 0)

    # Should have completed showdown and settle!
    assert t.hand_stage == poker.HS_SB_POST_STAGE
    # It was a split pot, so both should have 100
    assert t.seats[0]["stack"] == 100
    assert t.seats[1]["stack"] == 100
    assert t.seats[2]["stack"] == 100


@pytest.mark.asyncio
async def test_integration_3p_one_fold(t6):
    t = t6
    t._get_showdown_val = lambda x: 10
    p0 = "0x123"
    p1 = "0x456"
    p2 = "0x789"
    t.join_table(0, 100, p0, False)
    t.join_table(1, 100, p1, False)
    t.join_table(2, 100, p2, False)

    t.take_action(poker.ACT_SB_POST, p0, 1)
    t.take_action(poker.ACT_BB_POST, p1, 2)
    t.take_action(poker.ACT_CALL, p2, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CALL, p0, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CHECK, p1, 0)
    assert t.hand_stage == poker.HS_FLOP_BETTING
    assert len(t.board) == 3

    t.take_action(poker.ACT_BET, p0, 10)
    t.take_action(poker.ACT_FOLD, p1, 20)
    t.take_action(poker.ACT_CALL, p2, 0)
    assert t.hand_stage == poker.HS_TURN_BETTING
    assert len(t.board) == 4

    t.take_action(poker.ACT_CHECK, p0, 0)
    t.take_action(poker.ACT_CHECK, p2, 0)
    assert t.hand_stage == poker.HS_RIVER_BETTING
    assert len(t.board) == 5

    t.take_action(poker.ACT_BET, p0, 5)
    t.take_action(poker.ACT_CALL, p2, 0)

    # Should have completed showdown and settle!
    assert t.hand_stage == poker.HS_SB_POST_STAGE
    # p1 folded, so others should each win 1...
    assert t.seats[0]["stack"] == 101
    assert t.seats[1]["stack"] == 98
    assert t.seats[2]["stack"] == 101


@pytest.mark.asyncio
async def test_integration_3p_two_folds(t6):
    t = t6
    t._get_showdown_val = lambda x: 10
    p0 = "0x123"
    p1 = "0x456"
    p2 = "0x789"
    t.join_table(0, 100, p0, False)
    t.join_table(1, 100, p1, False)
    t.join_table(2, 100, p2, False)

    t.take_action(poker.ACT_SB_POST, p0, 1)
    t.take_action(poker.ACT_BB_POST, p1, 2)
    t.take_action(poker.ACT_CALL, p2, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CALL, p0, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CHECK, p1, 0)
    assert t.hand_stage == poker.HS_FLOP_BETTING
    assert len(t.board) == 3

    t.take_action(poker.ACT_CHECK, p0, 0)
    t.take_action(poker.ACT_BET, p1, 10)
    t.take_action(poker.ACT_FOLD, p2, 0)
    t.take_action(poker.ACT_FOLD, p0, 0)

    # P1 should have won pot - blinds from each player so 2 each
    assert t.hand_stage == poker.HS_SB_POST_STAGE
    # It was a split pot, so both should have 100
    assert t.seats[0]["stack"] == 98
    assert t.seats[1]["stack"] == 104
    assert t.seats[2]["stack"] == 98


@pytest.mark.asyncio
async def test_integration_3p_allin(t6):
    t = t6
    t._get_showdown_val = lambda x: 10
    p0 = "0x123"
    p1 = "0x456"
    p2 = "0x789"
    t.join_table(0, 100, p0, False)
    t.join_table(1, 100, p1, False)
    t.join_table(2, 100, p2, False)

    t.take_action(poker.ACT_SB_POST, p0, 1)
    t.take_action(poker.ACT_BB_POST, p1, 2)
    t.take_action(poker.ACT_CALL, p2, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CALL, p0, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CHECK, p1, 0)
    assert t.hand_stage == poker.HS_FLOP_BETTING
    assert len(t.board) == 3

    # Everyone AI on flop
    t.take_action(poker.ACT_BET, p0, 98)
    t.take_action(poker.ACT_CALL, p1, 0)
    t.take_action(poker.ACT_CALL, p2, 0)

    # Should progress to river and split pot
    assert t.hand_stage == poker.HS_SB_POST_STAGE
    # It was a split pot, so both should have 100
    assert t.seats[0]["stack"] == 100
    assert t.seats[1]["stack"] == 100
    assert t.seats[2]["stack"] == 100


@pytest.mark.asyncio
async def test_integration_3p_weird_allin(t2, t6):
    t = t6
    t._get_showdown_val = lambda x: 10
    p0 = "0x123"
    p1 = "0x456"
    p2 = "0x789"
    p3 = "0xabc"
    t.join_table(0, 200, p0, False)
    t.join_table(1, 100, p1, False)
    t.join_table(2, 50, p2, False)
    t.join_table(3, 100, p3, False)

    t.take_action(poker.ACT_SB_POST, p0, 1)
    t.take_action(poker.ACT_BB_POST, p1, 2)
    t.take_action(poker.ACT_CALL, p2, 0)
    t.take_action(poker.ACT_CALL, p3, 0)

    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CALL, p0, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CHECK, p1, 0)
    assert t.hand_stage == poker.HS_FLOP_BETTING
    assert len(t.board) == 3

    # Preflop betting was 8
    # Flop betting was
    # all-in on flop - P1 betting more than others but less than their stack
    t.take_action(poker.ACT_CHECK, p0, 0)
    t.take_action(poker.ACT_BET, p1, 10)
    t.take_action(poker.ACT_CALL, p2, 0)
    t.take_action(poker.ACT_CALL, p3, 0)
    t.take_action(poker.ACT_BET, p0, 123)
    t.take_action(poker.ACT_FOLD, p1, 0)
    t.take_action(poker.ACT_CALL, p2, 0)
    t.take_action(poker.ACT_CALL, p3, 0)

    # Should progress to river again, and pot splitting should result in
    # each player getting their original stack back
    assert t.hand_stage == poker.HS_SB_POST_STAGE
    # It was a split pot, so both should have 100
    # p1 put in 2 preflop and 10 on flop, so should be 12 to split among everyonoe
    assert t.seats[0]["stack"] == 204
    # p1 is down 12
    assert t.seats[1]["stack"] == 88
    assert t.seats[2]["stack"] == 54
    assert t.seats[3]["stack"] == 104
    print(t.events)


@pytest.mark.asyncio
async def test_integration_2p_fold_two_hands(t6):
    t = t6
    # Will always be a tie, think it's ok?
    t._get_showdown_val = lambda x: 10
    p0 = "0x123"
    p1 = "0x456"
    t.join_table(0, 100, p0, False)
    t.join_table(1, 100, p1, False)

    t.take_action(poker.ACT_SB_POST, p0, 1)
    t.take_action(poker.ACT_BB_POST, p1, 2)
    t.take_action(poker.ACT_FOLD, p0, 0)

    # assert not t.seats[0]["sitting_out"]
    # assert not t.seats[1]["sitting_out"]

    # After the fold it should progress all the way to the end and credit winnings to p1
    assert t.hand_stage == poker.HS_SB_POST_STAGE
    # It was a split pot, so both should have 100
    assert t.seats[0]["stack"] == 99
    assert t.seats[1]["stack"] == 101

    assert t.button == 1
    assert t.whose_turn == 1

    # Do another hand and make sure it still works
    t.take_action(poker.ACT_SB_POST, p1, 1)
    t.take_action(poker.ACT_BB_POST, p0, 2)
    t.take_action(poker.ACT_FOLD, p1, 0)

    # After the fold it should progress all the way to the end and credit winnings to p1
    assert t.hand_stage == poker.HS_SB_POST_STAGE
    # It was a split pot, so both should have 100
    assert t.seats[0]["stack"] == 100
    assert t.seats[1]["stack"] == 100
    # assert t.seats[0]["in_hand"]
    # assert t.seats[1]["in_hand"]
    # assert not t.seats[0]["sitting_out"]
    # assert not t.seats[1]["sitting_out"]


@pytest.mark.asyncio
async def test_integration_3p_open_fold(t2, t6):
    t = t6
    t._get_showdown_val = lambda x: 10
    p0 = "0x123"
    p1 = "0x456"
    p2 = "0x789"
    t.join_table(0, 200, p0, False)
    t.join_table(1, 100, p1, False)
    t.join_table(2, 50, p2, False)

    t.take_action(poker.ACT_SB_POST, p0, 1)
    t.take_action(poker.ACT_BB_POST, p1, 2)
    t.take_action(poker.ACT_CALL, p2, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CALL, p0, 0)
    assert t.hand_stage == poker.HS_PREFLOP_BETTING
    t.take_action(poker.ACT_CHECK, p1, 0)
    assert t.hand_stage == poker.HS_FLOP_BETTING
    assert len(t.board) == 3

    t.take_action(poker.ACT_FOLD, p0, 0)
    t.take_action(poker.ACT_CHECK, p1, 0)
    t.take_action(poker.ACT_CHECK, p2, 0)

    assert t.hand_stage == poker.HS_TURN_BETTING
    assert len(t.board) == 4
    assert t.whose_turn == 1
