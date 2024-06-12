import json
import itertools
import copy
import random
from functools import reduce
from enum import Enum
from typing import List, Tuple
from dataclasses import dataclass
from typing import Optional
from vanillapoker import pokerutils


# First 13 prime numbers
# Multiply them together to get a unique value, which we can use to
# evaluate hand strength using a lookup table
prime_mapping = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41]


# class HandStage(Enum):
# Make them ints to simplify serialization
HS_SB_POST_STAGE = 0
HS_BB_POST_STAGE = 1
HS_HOLECARDS_DEAL = 2
HS_PREFLOP_BETTING = 3
HS_FLOP_DEAL = 4
HS_FLOP_BETTING = 5
HS_TURN_DEAL = 6
HS_TURN_BETTING = 7
HS_RIVER_DEAL = 8
HS_RIVER_BETTING = 9
HS_SHOWDOWN = 10
HS_SETTLE = 11


# class ActionType(Enum):
ACT_SB_POST = 0
ACT_BB_POST = 1
ACT_BET = 2
ACT_FOLD = 3
ACT_CALL = 4
ACT_CHECK = 5


@dataclass
class HandState:
    player_stack: int
    player_bet_street: int
    hand_stage: int  # HandStage
    last_action_type: int  # ActionType
    last_action_amount: int
    transition_next_street: bool
    facing_bet: int
    last_raise: int
    button: int


class PokerTable:
    """
    Class containing state for an individual poker table
    All game actions will modify this class
    """

    lookup_table_basic_7c = {}
    lookup_table_flush_5c = {}

    def __init__(
        self,
        small_blind: int,
        big_blind: int,
        min_buyin: int,
        max_buyin: int,
        num_seats: int,
    ):

        self.small_blind = small_blind
        self.big_blind = big_blind
        self.min_buyin = min_buyin
        self.max_buyin = max_buyin
        self.num_seats = num_seats

        # Should these contain empty player objects instead?
        self.seats = [None for _ in range(num_seats)]
        self.player_to_seat = {}

        self.hand_stage = HS_SB_POST_STAGE
        # Pot up to this point in the hand
        self.pot_initial = 0
        # Track side pots here
        self.pots_complete = []
        self.button = 0
        self.whose_turn = 0
        self.closing_action_count = 0
        self.facing_bet = 0
        self.last_raise = 0
        self.last_action_type = None
        self.last_action_amount = 0

        self.deck = list(range(52))
        random.shuffle(self.deck)
        self.board = []

        # Append every single event here for the api to pop them off
        # TODO - look to be smarter about this...
        self.events_pop = []
        # Will be specific to table: f"{table_id}-{hand_id}" is full unique hand identifier
        # Note - first hand_id will actually be 1 (it's incremented in another function)
        self.hand_id = 0
        self.hand_histories = {}
        self._increment_hand_history()

    def _increment_hand_history(self):
        # Map from hand_id to events list
        self.hand_id += 1
        self.events = []
        # This way we'll track hand histories for in-progress hands
        self.hand_histories[self.hand_id] = self.events
        self.event_i = 0

    @property
    def pot_total(self):
        """
        Pot including all bets on current street
        """
        bet_street = sum([x["bet_street"] for x in self.seats if x is not None])
        return self.pot_initial + bet_street

    @property
    def num_active_players(self):
        return sum(
            [
                1
                for player in self.seats
                if player is not None and player["in_hand"] and player["stack"] > 0
            ]
        )

    def get_next_event(self):
        if self.event_i < len(self.events):
            event = self.events[self.event_i]
            self.event_i += 1
            return True, event
        return False, None

    def all_folded(self):
        # TODO - definitely cleaner logic for this, look to refactor
        return (
            sum(
                [1 for player in self.seats if player is not None and player["in_hand"]]
            )
            == 1
        )

    def allin(self):
        # TODO - definitely cleaner logic for this, look to refactor
        return (
            sum(
                [
                    1
                    for player in self.seats
                    if player is not None and player["in_hand"] and player["stack"] > 0
                ]
            )
            <= 1
        ) and self.closing_action_count == 0

    def serialize(self):
        """
        Store full game state in a way that we can stash it in a mysql table
        """
        return json.dumps(self.__dict__)

    def deserialize(self, dat):
        self.__dict__ = json.loads(dat)

    @classmethod
    def set_lookup_tables(cls, lookup_table_basic_7c, lookup_table_flush_5c):
        cls.lookup_table_basic_7c = lookup_table_basic_7c
        cls.lookup_table_flush_5c = lookup_table_flush_5c

    def join_table_next_seat_i(self, deposit_amount: int, address: str):
        """
        Helper function to add player to next available seat
        """
        for seat_i, player in enumerate(self.seats):
            if player is None:
                self.join_table(seat_i, deposit_amount, address)
                break

    def leave_table_no_seat_i(self, address: str):
        for seat_i, player in enumerate(self.seats):
            if player is None:
                continue
            if player["address"] == address:
                self.leave_table(seat_i, address)
                return
        raise Exception("Player not in game!")

    def rebuy_no_seat_i(self, rebuy_amount: int, address: str):
        for seat_i, player in enumerate(self.seats):
            if player["address"] == address:
                self.rebuy(seat_i, rebuy_amount, address)
                return
        raise Exception("Player not in game!")

    def join_table(
        self, seat_i: int, deposit_amount: int, address: str, auto_post=True
    ):
        """
        address should be a unique identifier for that player
        """
        assert 0 <= seat_i <= self.num_seats - 1, "Invalid seat_i!"
        assert self.seats[seat_i] == None, "seat_i taken!"
        assert address not in self.player_to_seat, "Player already joined!"
        assert (
            self.min_buyin <= deposit_amount <= self.max_buyin
        ), "Invalid deposit amount!"
        self.seats[seat_i] = {
            "address": address,
            "stack": deposit_amount,
            "in_hand": True,
            "auto_post": auto_post,
            # "sitting_out": False,
            "bet_street": 0,
            "showdown_val": 8000,
            "holecards": [],
            "last_action_type": None,
            "last_amount": None,
        }
        self.player_to_seat[address] = seat_i

        # If they join when a hand is in progress, wait until next hand
        if self.hand_stage != HS_SB_POST_STAGE:
            self.seats[seat_i]["in_hand"] = False

        tag_jt = {
            "tag": "joinTable",
            "player": address,
            "seat": seat_i,
            "depositAmount": deposit_amount,
        }
        self.events.append(tag_jt)
        self.events_pop.append(tag_jt)

        # If they're the FIRST player to join - give them the button and whose_turn?
        if sum([1 for player in self.seats if player is not None]) == 1:
            self.button = seat_i
            self.whose_turn = seat_i

        # This will check for auto-posting
        self._transition_hand_stage()

    def leave_table(self, seat_i: int, address: str):
        assert self.seats[seat_i]["address"] == address, "Player not at seat!"
        self.seats[seat_i] = None
        self.player_to_seat.pop(address)
        tag_lt = {"tag": "leaveTable", "player": address, "seat": seat_i}
        self.events.append(tag_lt)
        self.events_pop.append(tag_lt)

    def rebuy(self, seat_i: int, rebuy_amount: int, address: str):
        assert self.seats[seat_i]["address"] == address, "Player not at seat!"
        new_stack = self.seats[seat_i]["stack"] + rebuy_amount
        assert self.min_buyin <= new_stack <= self.max_buyin, "Invalid rebuy amount"
        self.seats[seat_i]["stack"] = new_stack

        tag_rb = {
            "tag": "rebuy",
            "player": address,
            "seat": seat_i,
            "rebuyAmount": rebuy_amount,
        }
        self.events.append(tag_rb)
        self.events_pop.append(tag_rb)

    @staticmethod
    def _transition_hand_state(
        hs: HandState, action_type: int, amount: int
    ) -> HandState:
        # Do we really need to copy this?
        hs_new = copy.deepcopy(hs)

        if action_type == ACT_SB_POST:
            # CHECKS:
            # we're at the proper stage

            # hs_new.hand_stage = ACT_BB_POST
            hs_new.facing_bet = amount
            hs_new.last_raise = amount
            hs_new.player_stack -= amount
            hs_new.player_bet_street = amount
            hs_new.last_action_amount = amount
        elif action_type == ACT_BB_POST:
            # CHECKS:
            # we're at the proper stage

            # hs_new.hand_stage = HS_HOLECARDS_DEAL
            hs_new.facing_bet = amount
            hs_new.last_raise = amount
            hs_new.player_stack -= amount
            hs_new.player_bet_street = amount
            hs_new.last_action_amount = amount
        elif action_type == ACT_BET:
            # CHECKS:
            # facing action is valid
            # bet amount is valid

            # If they're betting it MUST be an amount greater than the previous amount bet
            # on this street...
            bet_amount_new = amount - hs.player_bet_street
            hs_new.player_stack -= bet_amount_new
            hs_new.player_bet_street = amount
            assert amount > hs.facing_bet, "Invalid bet amount!"
            hs_new.facing_bet = amount
            hs_new.last_raise = hs.player_bet_street - hs.facing_bet
            # For bets it reopens action
            hs_new.last_action_amount = bet_amount_new
        elif action_type == ACT_FOLD:
            # CHECKS:
            # None?  But what if someone folds before they post SB/BB?

            hs_new.last_action_amount = 0
        elif action_type == ACT_CALL:
            # CHECKS:
            # facing action is valid (bet, call, fold?)

            call_amount_new = hs.facing_bet - hs.player_bet_street
            call_amount_new = min(call_amount_new, hs.player_stack)
            hs_new.player_stack -= call_amount_new
            hs_new.player_bet_street += call_amount_new
            hs_new.last_action_amount = call_amount_new
        elif action_type == ACT_CHECK:
            # CHECKS:
            # facing action is valid (check, None)

            hs_new.last_action_amount = 0

        assert hs_new.player_stack >= 0, "Insufficient funds!"
        hs_new.last_action_type = action_type

        return hs_new

    def take_action(self, action_type: int, address: str, amount: int, external=True):
        seat_i = self.player_to_seat[address]
        assert seat_i == self.whose_turn, "Not player's turn!"

        # Make sure it's their turn to act and they're in the hand?
        player_data = self.seats[seat_i]
        assert player_data["in_hand"], "Player not in hand!"

        hs = HandState(
            player_stack=player_data["stack"],
            player_bet_street=player_data["bet_street"],
            hand_stage=self.hand_stage,
            last_action_type=self.last_action_type,
            last_action_amount=self.last_action_amount,
            transition_next_street=False,
            facing_bet=self.facing_bet,
            last_raise=self.last_raise,
            button=self.button,
        )

        hs_new = self._transition_hand_state(hs, action_type, amount)

        self.seats[seat_i]["stack"] = hs_new.player_stack
        self.seats[seat_i]["bet_street"] = hs_new.player_bet_street
        self.seats[seat_i]["last_action_type"] = action_type
        self.seats[seat_i]["last_amount"] = amount
        if action_type == ACT_FOLD:
            self.seats[seat_i]["in_hand"] = False
        # Reset action count if it was a bet, otherwise it should increment
        # And we'll increment it as we skip over players...
        if action_type in [ACT_SB_POST, ACT_BB_POST]:
            self.closing_action_count = -1
        elif action_type in [ACT_BET]:
            self.closing_action_count = 0

        self.last_action_type = hs_new.last_action_type
        self.last_action_amount = hs_new.last_action_amount
        # self.pot = self.pot
        # self.closing_action_count = hs_new.closing_action_count
        self.facing_bet = hs_new.facing_bet
        self.last_raise = hs_new.last_raise
        self.button = hs_new.button

        # Will set whose_turn, safe to increment every time
        self._increment_whose_turn()

        # TODO -
        # we'll clear out events when we transition to nex<t hand
        # -so how do we cleanly access any final event in API?
        # stack_arr = [x["stack"] for x in self.seats if x is not None else None]
        players = [pokerutils.build_player_data(seat) for seat in self.seats]
        action = {
            "tag": "gameState",
            "potInitial": self.pot_initial,
            "pot": self.pot_total,
            "players": players,
            "button": self.button,
            "whoseTurn": self.whose_turn,
            "board": self.board,
            "handStage": self.hand_stage,
            "facingBet": self.facing_bet,
            "lastRaise": self.last_raise,
            "action": {
                "type": action_type,
                "amount": amount,
            },
        }
        self.events.append(action)
        self.events_pop.append(action)

        # When we post blinds we don't want to call this
        posted = action_type in [ACT_SB_POST, ACT_BB_POST]
        if external:
            self._transition_hand_stage(posted=posted)

    def _settle(self):
        """
        At this point every player should have a "sd_value" set for their hands
        Evaluate whose is the LOWEST, and they win the pot
        """
        # Hacking in action here...
        action = {"tag": "settle", "pots": []}

        for pot in self.pots_complete:
            winner_val = 9000
            winner_i = []
            # Will consist of 'amount' and 'players'
            for seat_i in pot["players"]:
                if self.seats[seat_i]["showdown_val"] < winner_val:
                    winner_val = self.seats[seat_i]["showdown_val"]
                    winner_i = [seat_i]
                elif self.seats[seat_i]["showdown_val"] == winner_val:
                    winner_i.append(seat_i)
            # Credit winnings
            for seat_i in winner_i:
                self.seats[seat_i]["stack"] += pot["amount"] / len(winner_i)
            # And add our event
            # [{ potTotal: 60, winners: { 0: 60 } }];
            # pot_dict = {seat_i: pot["amount"] / len(winner_i) for seat_i in winner_i}
            winner_dict = {seat_i: pot["amount"] / len(winner_i) for seat_i in winner_i}
            pot_dict = {"potTotal": pot["amount"], "winners": winner_dict}
            action["pots"].append(pot_dict)

        self.events.append(action)
        self.events_pop.append(action)

    def _get_showdown_val(self, cards):
        """
        Showdown value
        """
        assert len(cards) == 7
        # First get non-flush lookup value
        primes = [prime_mapping[x % 13] for x in cards]
        hand_val = reduce(lambda x, y: x * y, primes)
        lookup_val = self.lookup_table_basic_7c[str(int(hand_val))]

        # Check for a flush too...
        for suit in range(4):
            matches = [prime_mapping[x % 13] for x in cards if x // 13 == suit]
            if len(matches) >= 5:
                # Can have different combinations of 5 cards
                combos = itertools.combinations(matches, 5)
                for c in combos:
                    hand_val = reduce(lambda x, y: x * y, c)
                    lookup_val_ = self.lookup_table_flush_5c[str(int(hand_val))]
                    lookup_val = min(lookup_val, lookup_val_)

        return lookup_val

    def _showdown(self):
        """
        This will only be called if we get to showdown
        For all players still in the hand, calculate their showdown value and store it
        """
        action = {"tag": "showdown", "cards": [], "handStrs": []}

        # If everyone else folded - no lookups!
        # Otherwise their showdown_vals should still be at 8000
        still_in_hand = [p for p in self.seats if p is not None and p["in_hand"]]
        if len(still_in_hand) == 1:
            # This will award full pot to them
            still_in_hand[0]["showdown_val"] = 0
        else:
            for player in self.seats:
                if player is not None and player["in_hand"]:
                    holecards = player["holecards"]
                    player["showdown_val"] = self._get_showdown_val(
                        holecards + self.board
                    )
                    action["cards"].append(player["holecards"])
                    handStr = [
                        x
                        for x in pokerutils.card_descs
                        if x[0] <= player["showdown_val"]
                    ][-1][1]
                    action["handStrs"].append(handStr)
                else:
                    action["cards"].append([])
                    action["handStrs"].append("")

            # Only send showdown event if we had a real showdown
            self.events.append(action)
            self.events_pop.append(action)

    def _calculate_final_pot(self):
        """
        Any player who is still in_hand and has a stack > 0 is at showdown
        """
        street_players = [
            i
            for i in range(len(self.seats))
            if self.seats[i] is not None
            and self.seats[i]["in_hand"]
            and self.seats[i]["stack"] > 0
        ]
        main_pot_amount = self.pot_initial - sum(
            [x["amount"] for x in self.pots_complete]
        )
        main_pot = {"players": street_players, "amount": main_pot_amount}
        self.pots_complete.append(main_pot)

    def _next_street(self):
        """
        also want it here...
        """
        # We'll overwrite the bet_this_street amounts, so need to store new pot here first
        pot_initial_new = self.pot_total

        # If there were all-ins on previous streets, this will be what's left for sidepots
        # This should ALWAYS go to the first side pot calculated here
        pot_initial_left = self.pot_initial - sum(
            [x["amount"] for x in self.pots_complete]
        )
        bet_this_street_amounts = [x["bet_street"] for x in self.seats if x is not None]

        # TODO - this is hardcoded for 2p
        # Kind of ugly but set it one seat BEFOFE the first to act and then increment -
        # The issue is that if we have a 3 way pot, and first to act folds on an earlier
        # street, it will make it so it's their turn
        self.whose_turn = (self.button - 1) % self.num_seats
        self._increment_whose_turn()

        self.facing_bet = 0
        self.last_raise = 0
        self.last_action_type = None
        self.last_action_amount = 0
        self.closing_action_count = 0

        # Have to do this before clearing out player bet_street values
        street_players = [
            i
            for i in range(len(self.seats))
            if self.seats[i] is not None
            and self.seats[i]["in_hand"]
            and self.seats[i]["bet_street"] > 0
        ]

        # Reset player actions
        all_ins = []
        for player_i, player in enumerate(self.seats):
            if player is not None:
                # Determine if they went all-in, if yes we need to track side pots
                # This should also track main pot if it goes to showdown?
                if player["stack"] == 0 and player["bet_street"] > 0:
                    all_ins.append({"player": player_i, "amount": player["bet_street"]})
                player["last_action_type"] = None
                player["last_amount"] = None
                player["bet_street"] = 0

        # Sort from low to high
        all_ins.sort(key=lambda x: x["amount"])
        # Number of players who are still in the hand and were active on this street
        # We'll sort based on them
        for i in range(len(all_ins)):
            ai = all_ins[i]
            assert ai["amount"] >= 0
            # Can happen if two players are AI for same amount
            if ai["amount"] == 0:
                continue
            # Pot starting on this street, EXCLUDING any side pots
            # pot_initial_new is TOTAL
            # open_pot = pot_initial_new - sum([x["amount"] for x in self.pots_complete])
            # assert open_pot > 0

            # Just the amount from this street
            bet_this_street_amounts_here = [
                min(x, ai["amount"]) for x in bet_this_street_amounts
            ]
            bet_this_street_amounts = [
                x - min(x, ai["amount"]) for x in bet_this_street_amounts
            ]
            side_pot_amount = sum(bet_this_street_amounts_here)
            if i == 0:
                side_pot_amount += pot_initial_left

            # Due to check above should never even be 0
            side_pot = {"players": street_players, "amount": side_pot_amount}
            self.pots_complete.append(side_pot)
            # And remove this player from 'street_players'...
            street_players = [i for i in street_players if i != ai["player"]]
            all_ins = [
                {"player": x["player"], "amount": x["amount"] - ai["amount"]}
                for x in all_ins
            ]

        self.pot_initial = pot_initial_new

    def _next_hand(self):
        self.pot_initial = 0

        self.closing_action_count = 0
        self.facing_bet = 0
        self.last_raise = 0
        self.last_action_type = None
        self.last_action_amount = 0
        self.board = []
        self.pots_complete = []

        self.deck = list(range(52))

        random.shuffle(self.deck)

        # And set all player sd values to highest value
        for seat_i in range(self.num_seats):
            if self.seats[seat_i]:
                self.seats[seat_i]["bet_street"] = 0
                self.seats[seat_i]["showdown_val"] = 8000
                self.seats[seat_i]["holecards"] = []
                # If they went bust this hand - set them to be inactive!
                if (
                    self.seats[seat_i]["stack"] <= self.small_blind
                    # or self.seats[seat_i]["sitting_out"]
                ):
                    self.leave_table_no_seat_i(self.seats[seat_i]['address'])
                    # self.seats[seat_i] = None
                    # self.seats[seat_i]["in_hand"] = False
                    # self.seats[seat_i]["sitting_out"] = True
                # else:
                #     self.seats[seat_i]["in_hand"] = True
                #     self.seats[seat_i]["sitting_out"] = False

        self._increment_button()
        self.whose_turn = self.button

        self._increment_hand_history()

    def _handle_auto_post(self, post_type: str):
        # If we have two active players and game is in preflop stage - Post!
        assert post_type in ["SB", "BB"]
        # Only do it if we have at least two players?
        active = sum(
            [
                1
                for p in self.seats
                if p is not None
                # if p is not None and p["in_hand"] and not p["sitting_out"]
            ]
        )
        if active < 2:
            return False

        if post_type == "SB" and len([p for p in self.seats if p is not None]) >= 2:
            assert self.hand_stage == HS_SB_POST_STAGE, "Bad hand stage!"
            if (
                self.seats[self.whose_turn]["auto_post"]
                # and not self.seats[self.whose_turn]["sitting_out"]
            ):
                address_sb = self.seats[self.whose_turn]["address"]
                self.take_action(
                    ACT_SB_POST, address_sb, self.small_blind, external=False
                )
                return True
        elif post_type == "BB":
            # whose_turn should have been incremented
            if (
                self.seats[self.whose_turn]["auto_post"]
                # and not self.seats[self.whose_turn]["sitting_out"]
            ):
                address_bb = self.seats[self.whose_turn]["address"]
                self.take_action(
                    ACT_BB_POST, address_bb, self.big_blind, external=False
                )
                return True
        return False

    def _increment_button(self):
        """
        Should always progress to the next active player
        """
        # Sanity check - don't call it if there's only one player left
        print("incrementing button")
        active_players = 0
        for i in range(self.num_seats):
            seat = self.seats[i]
            # if seat is not None and not seat.get("sitting_out", True):
            if seat is not None:
                active_players += 1

        # TODO - how do we handle moving button if there are players sitting out?
        # Think we should still move it or a player might end up posting twice in a row?
        # What if there are empty seats?
        # @julie: remove sitting_out and just remove player if they are out of $$$
        if active_players >= 2:
            while True:
                self.button = (self.button + 1) % self.num_seats
                if self.seats[self.button] is not None:
                    break

                # if self.seats[self.button] is None:
                #     continue
                # if not self.seats[self.button]["sitting_out"]:
                #     break
        print("Done incrementing button")


    def _increment_whose_turn(self):
        """
        Progress to the next active player
        """
        # Can we keep our assertion?  Avoids while loop though
        inc = False
        for i in range(self.whose_turn + 1, self.whose_turn + 1 + self.num_seats):
            check_i = i % self.num_seats
            self.closing_action_count += 1
            if self.seats[check_i] is None:
                continue
            # They have to be in the hand and have some funds
            if self.seats[check_i]["in_hand"] and self.seats[check_i]["stack"] > 0:
                self.whose_turn = check_i
                inc = True
                break

        # Can go beyond num_seats in variety of ways
        # assert self.closing_action_count <= (
        #     self.num_seats + 1
        # ), "Too high closing_action_count!"

        # Sanity check - should always have a player left if we increment
        # assert inc, "Failed to increment whose_turn!"

    def _deal_holecards(self):
        for seat_i in range(self.num_seats):
            if self.seats[seat_i]:
                if not self.seats[seat_i]["in_hand"]:
                    continue
                # Keep first 5 cards for boardcards, deal from after that?
                start_i = 5 + seat_i * 2
                cards = self.deck[start_i : start_i + 2]
                self.seats[seat_i]["holecards"] = cards
                tag_hc = {"tag": "cards", "cardType": f"p{seat_i}", "cards": cards}
                self.events.append(tag_hc)
                self.events_pop.append(tag_hc)

        # HACK - sending gamestate again
        players = [pokerutils.build_player_data(seat) for seat in self.seats]
        action = {
            "tag": "gameState",
            "potInitial": self.pot_initial,
            "pot": self.pot_total,
            "players": players,
            "button": self.button,
            "whoseTurn": self.whose_turn,
            "board": self.board,
            "handStage": self.hand_stage,
            "facingBet": self.facing_bet,
            "lastRaise": self.last_raise,
            "action": {
                "type": None,
                "amount": None,
            },
        }
        self.events.append(action)
        self.events_pop.append(action)

    def _deal_flop(self):
        if not self.all_folded():
            self.board = self.deck[0:3]
            tag_flop = {"tag": "cards", "cardType": "flop", "cards": self.deck[0:3]}
            self.events.append(tag_flop)
            self.events_pop.append(tag_flop)

    def _deal_turn(self):
        if not self.all_folded():
            self.board = self.deck[:4]
            tag_turn = {"tag": "cards", "cardType": "turn", "cards": self.deck[3:4]}
            self.events.append(tag_turn)
            self.events_pop.append(tag_turn)

    def _deal_river(self):
        if not self.all_folded():
            self.board = self.deck[:5]
            tag_river = {"tag": "cards", "cardType": "river", "cards": self.deck[4:5]}
            self.events.append(tag_river)
            self.events_pop.append(tag_river)

    def _hand_stage_over_check(self):
        street_over = self.closing_action_count >= self.num_seats
        return street_over

    def _transition_hand_stage(self, **kwargs):
        """
        Keep transitioning state until it's time to wait for external action...
        """
        if not self.all_folded():
            players = [pokerutils.build_player_data(seat) for seat in self.seats]
            action = {
                "tag": "gameState",
                "potInitial": self.pot_initial,
                "pot": self.pot_total,
                "players": players,
                "button": self.button,
                "whoseTurn": self.whose_turn,
                "board": self.board,
                "handStage": self.hand_stage,
                "facingBet": self.facing_bet,
                "lastRaise": self.last_raise,
                "action": {
                    "type": None,
                    "amount": None,
                },
            }
            self.events.append(action)
            self.events_pop.append(action)

        if self.hand_stage == HS_SB_POST_STAGE:
            posted = kwargs.get("posted")
            if not posted:
                posted = self._handle_auto_post("SB")
            if posted:
                self.hand_stage += 1
                self._transition_hand_stage()
            return
        elif self.hand_stage == HS_BB_POST_STAGE:
            posted = kwargs.get("posted")
            if not posted:
                posted = self._handle_auto_post("BB")
            if posted:
                self.hand_stage += 1
                self._transition_hand_stage()
            return
        elif self.hand_stage == HS_HOLECARDS_DEAL:
            self._deal_holecards()
            self.hand_stage += 1
            self._transition_hand_stage()
            return
        elif self.hand_stage == HS_PREFLOP_BETTING:
            # If we're at preflop betting stage - we should wait for external action
            # Use '1' as default closing_action_count: if we're all-in it will proceed!
            if self._hand_stage_over_check() or self.all_folded() or self.allin():
                self.hand_stage += 1
                self._next_street()
                self._transition_hand_stage()
            return
        elif self.hand_stage == HS_FLOP_DEAL:
            self._deal_flop()
            self.hand_stage += 1
            self._transition_hand_stage()
            return
        elif self.hand_stage == HS_FLOP_BETTING:
            if self._hand_stage_over_check() or self.all_folded() or self.allin():
                self.hand_stage += 1
                self._next_street()
                self._transition_hand_stage()
            return
        elif self.hand_stage == HS_TURN_DEAL:
            self._deal_turn()
            self.hand_stage += 1
            self._transition_hand_stage()
            return
        elif self.hand_stage == HS_TURN_BETTING:
            if self._hand_stage_over_check() or self.all_folded() or self.allin():
                self.hand_stage += 1
                self._next_street()
                self._transition_hand_stage()
            return
        elif self.hand_stage == HS_RIVER_DEAL:
            self._deal_river()
            self.hand_stage += 1
            self._transition_hand_stage()
            return
        elif self.hand_stage == HS_RIVER_BETTING:
            if self._hand_stage_over_check() or self.all_folded() or self.allin():
                self.hand_stage += 1
                self._next_street()
                self._calculate_final_pot()
                self._transition_hand_stage()
            return
        elif self.hand_stage == HS_SHOWDOWN:
            self._showdown()
            # self._settle()  Do this in HS_SETTLE...
            self.hand_stage += 1
            self._transition_hand_stage()
            return
        elif self.hand_stage == HS_SETTLE:
            print("Settling...", self)
            self._settle()
            self._next_hand()
            # And reset back to post blinds stage!
            self.hand_stage = 0
            self._transition_hand_stage()
            return