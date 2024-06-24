import os
import sys
import time
import traceback
import json
import random
import traceback
from web3 import Web3, AsyncWeb3
from eth_account import Account
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    BackgroundTasks,
    WebSocket,
    WebSocketDisconnect,
)
import aiomysql
from contextlib import asynccontextmanager
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List
from socketio import AsyncServer, ASGIApp
from dotenv import load_dotenv
from typing import Optional
from asyncio import Lock
sys.path.append("../")
from vanillapoker import poker, pokerutils
from fastapi import APIRouter
from database_utils import *
from ws_utils import *


router = APIRouter()

# Classes
class ItemJoinTable(BaseModel):
    tableId: str
    address: str
    depositAmount: int
    seatI: int


class ItemLeaveTable(BaseModel):
    tableId: str
    address: str
    seatI: int


class ItemRebuy(BaseModel):
    tableId: str
    address: str
    rebuyAmount: str
    seatI: int


class ItemTakeAction(BaseModel):
    tableId: str
    address: str
    seatI: int
    actionType: int
    amount: int


class ItemCreateTable(BaseModel):
    smallBlind: int
    bigBlind: int
    minBuyin: int
    maxBuyin: int
    numSeats: int

### Classes end

### Helper functions
# Have to initialize the lookup tables before the API will work
def load_lookup_tables():
    with open("lookup_table_flushes.json", "r") as f:
        lookup_table_flush_5c = json.loads(f.read())

    with open("lookup_table_basic_7c.json", "r") as f:
        lookup_table_basic_7c = json.loads(f.read())

    return lookup_table_flush_5c, lookup_table_basic_7c

def gen_new_table_id():
    table_id = None
    random.seed(int(time.time()))
    while not table_id or table_id in TABLE_STORE:
        table_id = 10000 + int(random.random() * 990000)
    return str(table_id)


### Helper functions end

# Load lookup tables
lookup_table_flush_5c, lookup_table_basic_7c = load_lookup_tables()
poker.PokerTable.set_lookup_tables(lookup_table_basic_7c, lookup_table_flush_5c)

# In-memory game store
TABLE_STORE = {}

# Locks for player actions
locks = {}



# Join/Leave table endpoints
@router.post("/joinTable")
async def join_table(item: ItemJoinTable):
    table_id = item.tableId
    player_id = Web3.to_checksum_address(item.address)
    deposit_amount = int(item.depositAmount)

    # Create a lock for the player if it doesn't exist
    if player_id not in locks:
        locks[player_id] = Lock()

    async with locks[player_id]:
        # Need to move balance to temp funds
        bal_db = await read_balance_one(player_id)
        if bal_db["localBal"] < deposit_amount:
            raise HTTPException(status_code=400, detail="Insufficient balance")

        local_bal = bal_db["localBal"] - deposit_amount
        in_play = bal_db["inPlay"] + deposit_amount

        print("JOINING TABLE")
        # update_balance(on_chain_bal_new, local_bal_new, inPlay, address)
        await update_balance(bal_db["onChainBal"], local_bal, in_play, player_id)

        seat_i = item.seatI
        if table_id not in TABLE_STORE:
            return {"success": False, "error": "Table not found!"}
        poker_table_obj = TABLE_STORE[table_id]
        # Not using seat_i for now
        # poker_table_obj.join_table(seat_i, deposit_amount, player_id)
        poker_table_obj.join_table_next_seat_i(deposit_amount, player_id)
        await ws_emit_actions(table_id, poker_table_obj)
    return {"success": True}

@router.post("/leaveTable")
async def leave_table(item: ItemLeaveTable):
    table_id = item.tableId
    player_id = Web3.to_checksum_address(item.address)
    seat_i = item.seatI
    if table_id not in TABLE_STORE:
        return {"success": False, "error": "Table not found!"}

    poker_table_obj = TABLE_STORE[table_id]
    seat_i = poker_table_obj.player_to_seat[player_id]
    table_stack = poker_table_obj.seats[seat_i]["stack"]
    # poker_table_obj.leave_table(seat_i, player_id)
    # try:
    poker_table_obj.leave_table_no_seat_i(player_id)
    # except:
    #     err = traceback.format_exc()
    #     return {"success": False, "error": err}
    bal_db = await read_balance_one(player_id)

    local_bal = bal_db["localBal"] + table_stack
    # TODO - this assumes they're only ever at one table at a time...
    in_play = 0

    # update_balance(on_chain_bal_new, local_bal_new, inPlay, address)
    await update_balance(bal_db["onChainBal"], local_bal, in_play, player_id)

    await ws_emit_actions(table_id, poker_table_obj)
    return {"success": True}

# Table actions
@router.post("/rebuy")
async def rebuy(item: ItemRebuy):
    table_id = item.tableId
    player_id = Web3.to_checksum_address(item.address)
    rebuy_amount = item.rebuyAmount
    seat_i = item.seatI

    if table_id not in TABLE_STORE:
        return {"success": False, "error": "Table not found!"}
    poker_table_obj = TABLE_STORE[table_id]

    seat_i = poker_table_obj.player_to_seat[player_id]
    table_stack = poker_table_obj.seats[seat_i]["stack"]
    bal_db = await read_balance_one(player_id)
    # TODO - this assumes they're only ever at one table at a time...
    in_play = table_stack + rebuy_amount

    # update_balance(on_chain_bal_new, local_bal_new, inPlay, address)
    await update_balance(bal_db["onChainBal"], bal_db["localBal"], in_play, player_id)

    # poker_table_obj.rebuy(seat_i, rebuy_amount, player_id)
    # try:
    poker_table_obj.rebuy_no_seat_i(rebuy_amount, player_id)
    # except:
    #     err = traceback.format_exc()
    #     return {"success": False, "error": err}

    await ws_emit_actions(table_id, poker_table_obj)
    return {"success": True}

@router.post("/takeAction")
async def take_action(item: ItemTakeAction):
    table_id = item.tableId
    player_id = Web3.to_checksum_address(item.address)
    seat_i = item.seatI
    action_type = int(item.actionType)
    amount = int(item.amount)
    if table_id not in TABLE_STORE:
        return {"success": False, "error": "Table not found!"}
    poker_table_obj = TABLE_STORE[table_id]
    start_hand_stage = poker_table_obj.hand_stage

    try:
        poker_table_obj.take_action(action_type, player_id, amount)
    except Exception as e:
        print("ERROR TAKING ACTION", e)
        raise HTTPException(status_code=400, detail=str(e))
    
    await ws_emit_actions(table_id, poker_table_obj)

    # Only cache if we completed a hand!
    """
    end_hand_stage = poker_table_obj.hand_stage
    if end_hand_stage < start_hand_stage:
        print("UPDATING FOR TABLEID", table_id)
        try:
            update_table(table_id, poker_table_obj.serialize())
        except:
            err = traceback.format_exc()
            print("Intitial instantiation failed!", err)
            return False, {}
    """
    return {"success": True}

# Table management
@router.post("/createNewTable")
async def create_new_table(item: ItemCreateTable):
    # Need validation here too?
    small_blind = item.smallBlind
    big_blind = item.bigBlind
    min_buyin = item.minBuyin
    max_buyin = item.maxBuyin
    num_seats = item.numSeats

    # try:
    # Validate params...
    assert num_seats in [2, 6, 9]
    assert big_blind == small_blind * 2
    # Min_buyin
    assert 10 * big_blind <= min_buyin <= 400 * big_blind
    assert 10 * big_blind <= max_buyin <= 1000 * big_blind
    assert min_buyin <= max_buyin
    table_id = gen_new_table_id()
    poker_table_obj = poker.PokerTable(
        table_id, small_blind, big_blind, min_buyin, max_buyin, num_seats
    )
    TABLE_STORE[table_id] = poker_table_obj
    # except:
    #     err = traceback.format_exc()
    #     return {"tableId": None, "success": False, "error": err}

    # And cache it!
    # store_table(table_id, poker_table_obj.serialize())

    # Does this make sense?  Returning null response for all others
    return {"success": True, "tableId": table_id}

@router.get("/getTables")
async def get_tables():
    # Example element...
    # {
    #     "tableId": 456,
    #     "numSeats": 6,
    #     "smallBlind": 1,
    #     "bigBlind": 2,
    #     "minBuyin": 20,
    #     "maxBuyin": 400,
    #     "numPlayers": 2,
    # },
    tables = []
    for table_id, table_obj in TABLE_STORE.items():
        num_players = len([seat for seat in table_obj.seats if seat is not None])
        table_info = {
            "tableId": table_id,
            "numSeats": table_obj.num_seats,
            "smallBlind": table_obj.small_blind,
            "bigBlind": table_obj.big_blind,
            "minBuyin": table_obj.min_buyin,
            "maxBuyin": table_obj.max_buyin,
            "numPlayers": num_players,
        }
        tables.append(table_info)
        print(table_id, table_obj)

    return {"tables": tables}

@router.get("/getTable")
async def get_table(table_id: str):
    if table_id not in TABLE_STORE:
        return {"success": False, "error": "Table not found!"}

    poker_table_obj = TABLE_STORE[table_id]

    players = [pokerutils.build_player_data(seat) for seat in poker_table_obj.seats]
    table_info = {
        "tableId": table_id,
        "numSeats": poker_table_obj.num_seats,
        "smallBlind": poker_table_obj.small_blind,
        "bigBlind": poker_table_obj.big_blind,
        "minBuyin": poker_table_obj.min_buyin,
        "maxBuyin": poker_table_obj.max_buyin,
        "players": players,
        "board": poker_table_obj.board,
        "pot": poker_table_obj.pot_total,
        "potInitial": poker_table_obj.pot_initial,
        "button": poker_table_obj.button,
        "whoseTurn": poker_table_obj.whose_turn,
        # name is string, value is int
        "handStage": poker_table_obj.hand_stage,
        "facingBet": poker_table_obj.facing_bet,
        "lastRaise": poker_table_obj.last_raise,
        "action": {
            "type": poker_table_obj.last_action_type,
            "amount": poker_table_obj.hand_stage,
        },
    }
    return {"table_info": table_info}

@router.get("/getHandHistory")
async def get_hand_history(tableId: str, handId: int):
    if tableId not in TABLE_STORE:
        return {"success": False, "error": "Table not found!"}

    poker_table_obj = TABLE_STORE[tableId]
    if handId == -1:
        handIds = sorted(list(poker_table_obj.hand_histories.keys()))
        handId = handIds[-1]
    return {"hh": poker_table_obj.hand_histories[handId]}
    ...

# Game state
@router.get("/getGamestate")
async def get_gamestate(tableId: str):
    if tableId not in TABLE_STORE:
        return {"success": False, "error": "Table not found!"}
    poker_table_obj = TABLE_STORE[tableId]
    return {"data": poker_table_obj.serialize()}

