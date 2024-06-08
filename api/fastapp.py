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
from pydantic import BaseModel
from typing import List
from socketio import AsyncServer, ASGIApp
from dotenv import load_dotenv


# In-memory game store
TABLE_STORE = {}

sys.path.append("../")
from vanillapoker import poker, pokerutils

# Load environment variables from .env file
load_dotenv()

infura_key = os.environ["INFURA_KEY"]
alchemy_key = os.environ["ALCHEMY_KEY"]
infura_url = f"https://base-sepolia.infura.io/v3/{infura_key}"
alchemy_url = f"https://base-sepolia.g.alchemy.com/v2/{alchemy_key}"

web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(alchemy_url)) # if alchemy_url else Web3(Web3.HTTPProvider(infura_url))
token_vault_address = "0xbCb7d24815d3CB781C42A3d5403E3443F1234166"

with open("TokenVault.json", "r") as f:
    token_vault_abi = json.loads(f.read())


# nft_contract_address = "0xc87716e22EFc71D35717166A83eC0Dc751DbC421"
nft_contract_address = "0x79cf350480B2909A241cF51167D83AfA654D4F01"
nft_contract_abi = """
    [{
    "inputs": [
    {
        "internalType": "uint256",
        "name": "tokenId",
        "type": "uint256"
    }
    ],
    "name": "ownerOf",
    "outputs": [
    {
        "internalType": "address",
        "name": "",
        "type": "address"
    }
    ],
    "stateMutability": "view",
    "type": "function"
    }]
"""

# fmt: off
nft_contract_abi = [{'type': 'function', 'name': 'approve', 'inputs': [{'name': 'to', 'type': 'address', 'internalType': 'address'}, {'name': 'tokenId', 'type': 'uint256', 'internalType': 'uint256'}], 'outputs': [], 'stateMutability': 'nonpayable'}, {'type': 'function', 'name': 'balanceOf', 'inputs': [{'name': 'owner', 'type': 'address', 'internalType': 'address'}], 'outputs': [{'name': '', 'type': 'uint256', 'internalType': 'uint256'}], 'stateMutability': 'view'}, {'type': 'function', 'name': 'getApproved', 'inputs': [{'name': 'tokenId', 'type': 'uint256', 'internalType': 'uint256'}], 'outputs': [{'name': '', 'type': 'address', 'internalType': 'address'}], 'stateMutability': 'view'}, {'type': 'function', 'name': 'isApprovedForAll', 'inputs': [{'name': 'owner', 'type': 'address', 'internalType': 'address'}, {'name': 'operator', 'type': 'address', 'internalType': 'address'}], 'outputs': [{'name': '', 'type': 'bool', 'internalType': 'bool'}], 'stateMutability': 'view'}, {'type': 'function', 'name': 'name', 'inputs': [], 'outputs': [{'name': '', 'type': 'string', 'internalType': 'string'}], 'stateMutability': 'view'}, {'type': 'function', 'name': 'ownerOf', 'inputs': [{'name': 'tokenId', 'type': 'uint256', 'internalType': 'uint256'}], 'outputs': [{'name': '', 'type': 'address', 'internalType': 'address'}], 'stateMutability': 'view'}, {'type': 'function', 'name': 'safeTransferFrom', 'inputs': [{'name': 'from', 'type': 'address', 'internalType': 'address'}, {'name': 'to', 'type': 'address', 'internalType': 'address'}, {'name': 'tokenId', 'type': 'uint256', 'internalType': 'uint256'}], 'outputs': [], 'stateMutability': 'nonpayable'}, {'type': 'function', 'name': 'safeTransferFrom', 'inputs': [{'name': 'from', 'type': 'address', 'internalType': 'address'}, {'name': 'to', 'type': 'address', 'internalType': 'address'}, {'name': 'tokenId', 'type': 'uint256', 'internalType': 'uint256'}, {'name': 'data', 'type': 'bytes', 'internalType': 'bytes'}], 'outputs': [], 'stateMutability': 'nonpayable'}, {'type': 'function', 'name': 'setApprovalForAll', 'inputs': [{'name': 'operator', 'type': 'address', 'internalType': 'address'}, {'name': 'approved', 'type': 'bool', 'internalType': 'bool'}], 'outputs': [], 'stateMutability': 'nonpayable'}, {'type': 'function', 'name': 'supportsInterface', 'inputs': [{'name': 'interfaceId', 'type': 'bytes4', 'internalType': 'bytes4'}], 'outputs': [{'name': '', 'type': 'bool', 'internalType': 'bool'}], 'stateMutability': 'view'}, {'type': 'function', 'name': 'symbol', 'inputs': [], 'outputs': [{'name': '', 'type': 'string', 'internalType': 'string'}], 'stateMutability': 'view'}, {'type': 'function', 'name': 'tokenURI', 'inputs': [{'name': 'tokenId', 'type': 'uint256', 'internalType': 'uint256'}], 'outputs': [{'name': '', 'type': 'string', 'internalType': 'string'}], 'stateMutability': 'view'}, {'type': 'function', 'name': 'transferFrom', 'inputs': [{'name': 'from', 'type': 'address', 'internalType': 'address'}, {'name': 'to', 'type': 'address', 'internalType': 'address'}, {'name': 'tokenId', 'type': 'uint256', 'internalType': 'uint256'}], 'outputs': [], 'stateMutability': 'nonpayable'}, {'type': 'event', 'name': 'Approval', 'inputs': [{'name': 'owner', 'type': 'address', 'indexed': True, 'internalType': 'address'}, {'name': 'approved', 'type': 'address', 'indexed': True, 'internalType': 'address'}, {'name': 'tokenId', 'type': 'uint256', 'indexed': True, 'internalType': 'uint256'}], 'anonymous': False}, {'type': 'event', 'name': 'ApprovalForAll', 'inputs': [{'name': 'owner', 'type': 'address', 'indexed': True, 'internalType': 'address'}, {'name': 'operator', 'type': 'address', 'indexed': True, 'internalType': 'address'}, {'name': 'approved', 'type': 'bool', 'indexed': False, 'internalType': 'bool'}], 'anonymous': False}, {'type': 'event', 'name': 'Transfer', 'inputs': [{'name': 'from', 'type': 'address', 'indexed': True, 'internalType': 'address'}, {'name': 'to', 'type': 'address', 'indexed': True, 'internalType': 'address'}, {'name': 'tokenId', 'type': 'uint256', 'indexed': True, 'internalType': 'uint256'}], 'anonymous': False}, {'type': 'error', 'name': 'ERC721IncorrectOwner', 'inputs': [{'name': 'sender', 'type': 'address', 'internalType': 'address'}, {'name': 'tokenId', 'type': 'uint256', 'internalType': 'uint256'}, {'name': 'owner', 'type': 'address', 'internalType': 'address'}]}, {'type': 'error', 'name': 'ERC721InsufficientApproval', 'inputs': [{'name': 'operator', 'type': 'address', 'internalType': 'address'}, {'name': 'tokenId', 'type': 'uint256', 'internalType': 'uint256'}]}, {'type': 'error', 'name': 'ERC721InvalidApprover', 'inputs': [{'name': 'approver', 'type': 'address', 'internalType': 'address'}]}, {'type': 'error', 'name': 'ERC721InvalidOperator', 'inputs': [{'name': 'operator', 'type': 'address', 'internalType': 'address'}]}, {'type': 'error', 'name': 'ERC721InvalidOwner', 'inputs': [{'name': 'owner', 'type': 'address', 'internalType': 'address'}]}, {'type': 'error', 'name': 'ERC721InvalidReceiver', 'inputs': [{'name': 'receiver', 'type': 'address', 'internalType': 'address'}]}, {'type': 'error', 'name': 'ERC721InvalidSender', 'inputs': [{'name': 'sender', 'type': 'address', 'internalType': 'address'}]}, {'type': 'error', 'name': 'ERC721NonexistentToken', 'inputs': [{'name': 'tokenId', 'type': 'uint256', 'internalType': 'uint256'}]}]
# fmt: on

# Create a contract instance
nft_contract_async = web3.eth.contract(
    address=nft_contract_address, abi=nft_contract_abi
)
token_vault = web3.eth.contract(address=token_vault_address, abi=token_vault_abi["abi"])
print(token_vault)
START_TIME = time.time()

TOTAL_TOKENS = 0


def generate_card_properties():
    """
    Use PRNG to deterministically generate random properties for the NFTs
    """
    import random

    random.seed(0)

    # Map from nft tokenId to properties
    nft_map = {}

    for i in range(1000):
        # Copying naming convention from solidity contract
        cardNumber = random.randint(0, 51)
        rarity = random.randint(1, 100)
        nft_map[i] = {"cardNumber": cardNumber, "rarity": rarity, "forSale": False}

    return nft_map

# Storing NFT metadata properties locally for now - in future pull from chain
nft_map = generate_card_properties()
# Track true/false - listed for sale?
nft_listings_map = {}


sio = AsyncServer(async_mode="asgi", cors_allowed_origins="*")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # await database.database.connect()
    pass
    yield
    pass
    # await database.database.disconnect()


app = FastAPI(lifespan=lifespan)

# Add CORS middleware to FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Wrap the Socket.IO server with ASGI middleware
socket_app = ASGIApp(sio, other_asgi_app=app)


# Have to initialize the lookup tables before the API will work
def load_lookup_tables():
    with open("lookup_table_flushes.json", "r") as f:
        lookup_table_flush_5c = json.loads(f.read())

    with open("lookup_table_basic_7c.json", "r") as f:
        lookup_table_basic_7c = json.loads(f.read())

    return lookup_table_flush_5c, lookup_table_basic_7c


lookup_table_flush_5c, lookup_table_basic_7c = load_lookup_tables()
poker.PokerTable.set_lookup_tables(lookup_table_basic_7c, lookup_table_flush_5c)


# Define Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    print("Client connected:", sid)


@sio.event
async def disconnect(sid):
    print("Client disconnected:", sid)


async def ws_emit_actions(table_id, poker_table_obj):
    # while True:
    #     is_event, event = poker_table_obj.get_next_event(0)
    #     if is_event:
    #         await sio.emit(table_id, event)
    #     else:
    #         break
    while poker_table_obj.events_pop:
        event = poker_table_obj.events_pop.pop(0)
        print("EMITTING EVENT", event)
        await sio.emit(table_id, event)


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


class CreateNftItem(BaseModel):
    tokenId: int
    address: str


class ItemDeposit(BaseModel):
    address: str
    depositAmount: str


@app.post("/joinTable")
async def join_table(item: ItemJoinTable):
    table_id = item.tableId
    player_id = Web3.to_checksum_address(item.address)
    deposit_amount = int(item.depositAmount)

    # Need to move balance to temp funds
    bal_db = await read_balance_one(player_id)
    assert bal_db["localBal"] >= deposit_amount

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


@app.post("/leaveTable")
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


@app.post("/rebuy")
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


@app.post("/takeAction")
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

    # try:
    poker_table_obj.take_action(action_type, player_id, amount)
    # except:
    #     err = traceback.format_exc()
    #     return {"success": False, "error": err}

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


def gen_new_table_id():
    table_id = None
    random.seed(int(time.time()))
    while not table_id or table_id in TABLE_STORE:
        table_id = 10000 + int(random.random() * 990000)
    return str(table_id)


@app.post("/createNewTable")
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
    poker_table_obj = poker.PokerTable(
        small_blind, big_blind, min_buyin, max_buyin, num_seats
    )
    table_id = gen_new_table_id()
    TABLE_STORE[table_id] = poker_table_obj
    # except:
    #     err = traceback.format_exc()
    #     return {"tableId": None, "success": False, "error": err}

    # And cache it!
    # store_table(table_id, poker_table_obj.serialize())

    # Does this make sense?  Returning null response for all others
    return {"success": True, "tableId": table_id}


@app.get("/getTables")
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


@app.get("/getTable")
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


@app.get("/getHandHistory")
async def get_hand_history(tableId: str, handId: int):
    if tableId not in TABLE_STORE:
        return {"success": False, "error": "Table not found!"}

    poker_table_obj = TABLE_STORE[tableId]
    if handId == -1:
        handIds = sorted(list(poker_table_obj.hand_histories.keys()))
        handId = handIds[-1]
    return {"hh": poker_table_obj.hand_histories[handId]}


def get_nft_holders():
    # Fine for this to be non-async, only runs on startup
    w3 = Web3(Web3.HTTPProvider(alchemy_url)) # if alchemy_url else Web3(Web3.HTTPProvider(infura_url))
    print(w3)
    # Create a contract instance
    nft_contract = w3.eth.contract(address=nft_contract_address, abi=nft_contract_abi)

    # Cache previous one to save on calls...
    # fmt: off
    holders = {'0xD9F8bf1F266E50Bb4dE528007f28c14bb7edaff7': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 42, 43, 44, 45, 46, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 101, 102, 103, 104, 105, 107], '0xC52178a1b28AbF7734b259c27956acBFd67d4636': [41, 47, 96, 97, 98, 99, 100, 106], '0x534631Bcf33BDb069fB20A93d2fdb9e4D4dD42CF': [48], '0x459e213D8B5E79d706aB22b945e3aF983d51BC4C': [108]}
    # fmt: on
    holders = {Web3.to_checksum_address(x): holders[x] for x in holders}
    print(holders)
    token_id = 0
    for addr in holders:
        max_token_id = max(holders[addr])
        token_id = max(token_id, max_token_id)

    fails = 0
    while True:
        try:
            token_id += 1
            owner = None
            owner = nft_contract.functions.ownerOf(token_id).call()
            owner = Web3.to_checksum_address(owner)
            if owner in holders:
                holders[owner].append(token_id)
            else:
                holders[owner] = [token_id]
            # time.sleep(0.25)
        except Exception as e:
            print("FAILED", e)
            fails += 1
            # time.sleep(5)
            if fails >= 10:
                print("CRASHED ON", token_id, owner)
                break
    global TOTAL_TOKENS
    TOTAL_TOKENS += token_id * 1000
    print("CURRENT HOLDERS")
    print(holders)

    return holders


# Hardcode this?  Figure out clean way to get it...
# nft_owners = {"0xC52178a1b28AbF7734b259c27956acBFd67d4636": [0]}
# TODO - reenable this...
# print("SKIPPING NFT_OWNERS...")
nft_owners = {}
# nft_owners = get_nft_holders()


def calculate_earning_rate(address):
    """
    Calculate the earning rate for a given address based on the rarity of their NFTs.

    :param address: Ethereum address of the user (string)
    :return: Earning rate as a float between 0 and 1
    """
    global nft_owners, nft_map

    address = Web3.to_checksum_address(address)
    user_nfts = nft_owners.get(address, [])
    
    total_rarity = sum(nft_map[tokenId]["rarity"] for holder in nft_owners for tokenId in nft_owners[holder])
    user_rarity_sum = sum(nft_map[tokenId]["rarity"] for tokenId in user_nfts)
    
    earning_rate = user_rarity_sum / total_rarity if total_rarity > 0 else 0
    
    return earning_rate

@app.get("/getUserNFTs")
async def get_user_nfts(address: str):
    # Get a list of tokenIds of NFTs this user owns
    address = Web3.to_checksum_address(address)
    user_nfts = nft_owners.get(address, [])
    ret_data = {tokenId: nft_map[tokenId] for tokenId in user_nfts}
    for tokenId in user_nfts:
        ret_data[tokenId]["forSale"] = tokenId in nft_listings_map
    return ret_data


@app.get("/getNFTMetadata")
async def get_nft_metadata(tokenId: int):
    # {'cardNumber': 12, 'rarity': 73}
    nft_map[tokenId]["forSale"] = tokenId in nft_listings_map
    return nft_map[tokenId]


@app.post("/createNewNFT")
async def create_new_nft(item: CreateNftItem):
    """
    This will be called by the front end immediatly before
    the transaction is sent to the blockchain.  We should
    return the expected NFT number here.
    """
    # So ugly but we need to iterate?
    # next_token_id = 0
    # for owner in nft_owners:
    #     for token_id in nft_owners[owner]:
    #         next_token_id = max(next_token_id, token_id + 1)
    token_id = item.tokenId

    owner = Web3.to_checksum_address(item.address)
    if owner in nft_owners:
        nft_owners[owner].append(token_id)
    else:
        nft_owners[owner] = [token_id]

    global TOTAL_TOKENS
    TOTAL_TOKENS += 1000
    try:
        bal_db = await read_balance_one(owner)
        local_bal_new = bal_db["localBal"] + 500
        await update_balance(
            bal_db["onChainBal"], local_bal_new, bal_db["inPlay"], owner
        )
    except:
        # {"address":"0x123","onChainBal":115,"localBal":21,"inPlay":456}
        local_bal_new = 1000
        await create_user(owner, 0, local_bal_new, 0)

    # {'cardNumber': 12, 'rarity': 73}
    # "tokenId": next_token_id,
    return nft_map[token_id]


async def get_db_connection():
    connection = await aiomysql.connect(
        host="localhost",
        port=3306,
        user=os.environ["SQL_USER"],
        password=os.environ["SQL_PASS"],
        db="users",
    )
    return connection


# Keep this call for debugging...
@app.get("/users")
async def read_users():
    global TOTAL_TOKENS
    connection = await get_db_connection()
    async with connection.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT * FROM user_balances")
        users = await cursor.fetchall()
    connection.close()
    # [{"address":"0x123","onChainBal":115,"localBal":21,"inPlay":456}]
    print("GOT USERS", users)
    return users


class User(BaseModel):
    address: str
    onChainBal: int
    localBal: int
    inPlay: int


# @app.post("/users")
# async def create_user(user: User):
async def create_user(address, on_chain_bal, local_bal, in_play):
    address = Web3.to_checksum_address(address)
    connection = await get_db_connection()
    async with connection.cursor() as cursor:
        try:
            await cursor.execute(
                """
                INSERT INTO user_balances (address, onChainBal, localBal, inPlay) 
                VALUES (%s, %s, %s, %s)
            """,
                (address, str(on_chain_bal), str(local_bal), str(in_play)),
            )
            await connection.commit()
        except Exception as e:
            await connection.rollback()
            raise HTTPException(status_code=400, detail="Error creating user") from e
    connection.close()
    return {"message": "User created successfully"}


class UserBalance(BaseModel):
    address: str
    onChainBal: int
    localBal: int
    inPlay: int


# @app.put("/balances")
# async def update_balance(balance: UserBalance):
async def update_balance(on_chain_bal_new, local_bal_new, inPlay, address):
    # (balance.onChainBal, balance.localBal, balance.inPlay, balance.address),
    address = Web3.to_checksum_address(address)
    connection = await get_db_connection()
    print("ACTUALLY SETTING FOR ADDR", address)
    async with connection.cursor() as cursor:
        try:
            await cursor.execute(
                """
                UPDATE user_balances 
                SET onChainBal = %s, localBal = %s, inPlay = %s 
                WHERE address = %s
            """,
                (str(on_chain_bal_new), str(local_bal_new), str(inPlay), address),
            )
            await connection.commit()
        except Exception as e:
            await connection.rollback()
            raise HTTPException(status_code=400, detail="Error updating balance") from e
    connection.close()
    return {"message": "Balance updated successfully"}


# @app.get("/balance_one")
async def read_balance_one(address: str):
    connection = await get_db_connection()
    address = Web3.to_checksum_address(address)
    async with connection.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute(
            "SELECT * FROM user_balances WHERE address = %s", (address,)
        )
        balance = await cursor.fetchone()
        if balance is None:
            raise HTTPException(status_code=404, detail="User not found")
        # db entries are now strings
        balance["onChainBal"] = int(float(balance["onChainBal"]))
        balance["localBal"] = int(float(balance["localBal"]))
        balance["inPlay"] = int(float(balance["inPlay"]))
    connection.close()
    return balance


class WithdrawItem(BaseModel):
    address: str
    amount: int


@app.post("/withdraw")
async def withdraw(item: WithdrawItem):
    # Amount should be TOKEN amount!!!  Not eth!

    # Steps:
    # 1. Make sure they actually have that amount available
    # 2. Calculate how much they should get (keep ratios the same)
    # 3. Update their balance in the database - (only localBal?)
    # 4. Update total supply
    # 5. Call the withdraw function on the TokenVault contract

    address = Web3.to_checksum_address(item.address)
    amount = item.amount

    # They should not be able to withdraw if they don't have a balance, so
    # let this one fail
    bal_db = await read_balance_one(address)
    assert bal_db["localBal"] >= amount

    # {"address":"0x123","onChainBal":115,"localBal":21,"inPlay":456}

    # plypkr = web3.eth.contract(address=plypkr_address, abi=plypkr_abi)

    # 2. seeing how much they should get
    total_eth = await web3.eth.get_balance(token_vault_address)
    
    global TOTAL_TOKENS
    their_pct = amount / TOTAL_TOKENS
    # This will be in gwei
    cashout_amount_eth = int(their_pct * total_eth)

    # 3. Update their balance in the database - (only localBal?)
    local_bal_new = bal_db["localBal"] - amount
    await update_balance(bal_db["onChainBal"], local_bal_new, bal_db["inPlay"], address)

    # 4. Update total supply
    TOTAL_TOKENS -= amount

    # 5. Call the withdraw function on the TokenVault contract
    private_key = os.environ["PRIVATE_KEY"]
    account = Account.from_key(private_key)
    # account = web3.eth.account.privateKeyToAccount(private_key)
    account_address = account.address
    # bal = await plypkr.functions.balanceOf(account_address).call()
    # Step 4: Call the withdraw function on the TokenVault contract
    print("CASHING OUT...", address, cashout_amount_eth)

    nonce = await web3.eth.get_transaction_count(account_address)
    address = Web3.to_checksum_address(address)
    withdraw_txn = await token_vault.functions.withdraw(
        address, cashout_amount_eth
    ).build_transaction(
        {
            "from": account_address,
            "nonce": nonce,
            # "gas": 2000000,
            # "gasPrice": web3.to_wei("50", "gwei"),
        }
    )
    signed_withdraw_txn = web3.eth.account.sign_transaction(
        withdraw_txn, private_key=private_key
    )
    withdraw_txn_hash = await web3.eth.send_raw_transaction(
        signed_withdraw_txn.rawTransaction
    )
    print(f"Deposit transaction hash: {withdraw_txn_hash.hex()}")
    # await web3.eth.wait_for_transaction_receipt(withdraw_txn_hash)
    return {"success": True}


@app.post("/deposited")
async def post_deposited(item: ItemDeposit):
    """
    After user deposits to contract, update their balance in the database
    """
    address = Web3.to_checksum_address(item.address)
    deposit_amount = item.depositAmount
    deposit_amount = int(deposit_amount)
    # So get the DIFF between what they have and what we've tracked
    print("DEPOSITED", address, deposit_amount)
    global TOTAL_TOKENS

    # Get the balance in Wei
    total_eth = await web3.eth.get_balance(token_vault_address)
    deposit_share = deposit_amount / total_eth
    token_amount = int(deposit_share * TOTAL_TOKENS)
    TOTAL_TOKENS += token_amount
    print("GOT VALUES")
    print(deposit_amount, total_eth, deposit_share, token_amount)

    # {"address":"0x123","onChainBal":115,"localBal":21,"inPlay":456}
    try:
        bal_db = await read_balance_one(address)
        on_chain_bal_new = bal_db["onChainBal"] + deposit_amount
        local_bal_new = bal_db["localBal"] + token_amount
        await update_balance(on_chain_bal_new, local_bal_new, bal_db["inPlay"], address)
    except:
        # {"address":"0x123","onChainBal":115,"localBal":21,"inPlay":456}
        on_chain_bal_new = deposit_amount
        local_bal_new = token_amount
        print("CREATING NEW USER...", address, on_chain_bal_new, local_bal_new, 0)
        await create_user(address, on_chain_bal_new, local_bal_new, 0)

    # Update local state tally...
    TOTAL_TOKENS += deposit_amount
    return {"success": True}


@app.get("/getTokenBalance")
async def get_token_balance(address: str):
    # {"address":"0x123","onChainBal":115,"localBal":21,"inPlay":456}
    try:
        address = Web3.to_checksum_address(address)
    except:
        pass
    try:
        bal = await read_balance_one(address)
    except:
        return {"data": 0}
    print("GOT TOKEN BALANCE", bal)
    user_bal = bal.get("localBal", 0)
    user_bal = 0 if not user_bal else user_bal
    time_elapsed = time.time() - START_TIME

    # """
    earning_rate = calculate_earning_rate(address)
    # Annualized rate - compare to total token supply
    earnings_pct = (time_elapsed / (60 * 60 * 24 * 365)) * earning_rate
    print("ADDRESS, EARNINGS PCT", address, earnings_pct)
    bonus_earnings = int(earnings_pct * TOTAL_TOKENS)
    # Set a minimum rate of 1 token every 30 seconds?
    # But cap it at 2 tokens every 30 seconds...
    if earning_rate > 0:
        tokens_per_day = (60 * 60 * 24) / 30
        days_elapsed = time_elapsed / (60 * 60 * 24)
        fake_earnings_min = int(days_elapsed * tokens_per_day)
        fake_earnings_max = fake_earnings_min * 2
        bonus_earnings = max(bonus_earnings, fake_earnings_min)
        bonus_earnings = min(bonus_earnings, fake_earnings_max)
    user_bal += bonus_earnings
    # """
    # Their 'localBal' is their available balance, think that's all we need to return?
    return {"data": user_bal}


@app.get("/getEarningRate")
async def get_earning_rate(address: str):
    # Get their NFTs - sum up the rarity values and divide by 100?  Or normalize?
    address = Web3.to_checksum_address(address)
    earning_rate = calculate_earning_rate(address)
    return {"data": earning_rate}


@app.get("/getRealTimeConversion")
async def get_real_time_conversion():
    # Divide token count by ETH count ...
    # TODO - get this count
    total_tokens = TOTAL_TOKENS

    # Get the balance in Wei
    total_eth = await web3.eth.get_balance(token_vault_address)
    total_eth = total_eth / 10**18
    print("GOT VALUES", TOTAL_TOKENS, total_eth);
    if total_eth > 0:
        conv = total_tokens / total_eth
    else:
        conv = 100_000
    return {"data": conv, "total_tokens": total_tokens, "total_eth": total_eth}


@app.get("/getLeaderboard")
async def get_leaderboard():
    global TOTAL_TOKENS
    connection = await get_db_connection()
    async with connection.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT * FROM user_balances")
        users = await cursor.fetchall()
    connection.close()
    # [{"address":"0x123","onChainBal":115,"localBal":21,"inPlay":456}]
    leaders = []
    for user in users:
        if len(user["address"]) == 42:
            earning_rate = calculate_earning_rate(user["address"])
            bal_tot = int(float(user["localBal"])) + int(float(user["inPlay"]))
            leaders.append(
                {
                    "address": user["address"],
                    "balance": bal_tot,
                    "earningRate": earning_rate,
                }
            )
    print("GOT USERS", users)
    return {"leaderboard": leaders}


@app.post("/updateTokenBalances")
async def update_token_balances():
    """
    Before shutting down - call this ONCE so we track updated balances
    """
    connection = await get_db_connection()
    async with connection.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT * FROM user_balances")
        users = await cursor.fetchall()
    connection.close()

    for bal_db in users:
        user_bal = bal_db.get("localBal", 0)
        user_bal = 0 if not user_bal else user_bal
        time_elapsed = time.time() - START_TIME

        earning_rate = calculate_earning_rate(bal_db["address"])
        # Annualized rate
        earnings_pct = (time_elapsed / (60 * 60 * 24 * 365)) * earning_rate
        user_bal += int(earnings_pct * TOTAL_TOKENS)
        local_bal_new = user_bal

        await update_balance(
            bal_db["onChainBal"], local_bal_new, bal_db["inPlay"], bal_db["address"]
        )
    return {"success": True}


class ItemTransferNFT(BaseModel):
    from_: str
    to_: str
    tokenId: int


# @app.post("/transferNFT")
# async def transfer_nft(item: ItemTransferNFT):
async def transfer_nft(from_, to_, tokenId):
    # Endpoint (plus many others) need to be secured so users can't directly call this endpoint
    # from_ = item.from_
    from_ = Web3.to_checksum_address(from_)
    # to_ = item.to_
    to_ = Web3.to_checksum_address(to_)
    # tokenId = item.tokenId

    # Our call...
    # nft_contract.transferFrom(from_, to_, tokenId)

    # 5. Call the withdraw function on the TokenVault contract
    private_key = os.environ["PRIVATE_KEY"]
    account = Account.from_key(private_key)
    # account = web3.eth.account.privateKeyToAccount(private_key)
    account_address = account.address
    # bal = await plypkr.functions.balanceOf(account_address).call()
    # Step 4: Call the withdraw function on the TokenVault contract
    nonce = await web3.eth.get_transaction_count(account_address)

    transfer_txn = await nft_contract_async.functions.transferFrom(
        from_, to_, tokenId
    ).build_transaction(
        {
            "from": account_address,
            "nonce": nonce,
            # "gas": 2000000,
            # "gasPrice": web3.to_wei("50", "gwei"),
        }
    )

    signed_withdraw_txn = web3.eth.account.sign_transaction(
        transfer_txn, private_key=private_key
    )
    withdraw_txn_hash = await web3.eth.send_raw_transaction(
        signed_withdraw_txn.rawTransaction
    )
    print(f"Deposit transaction hash: {withdraw_txn_hash.hex()}")
    # await web3.eth.wait_for_transaction_receipt(withdraw_txn_hash)
    return {"success": True}


class ItemListNFT(BaseModel):
    address: str
    tokenId: int
    amount: int


@app.post("/listNFT")
async def list_nft(item: ItemListNFT):
    """
    Lets a user put an NFT for sale on the marketplace
    Need to secure this endpoint too...
    """
    # Ensure user owns this nft before listing it
    address = Web3.to_checksum_address(item.address)
    user_nfts = nft_owners.get(address, [])
    assert item.tokenId in user_nfts, "User does not own nft!"
    nft_listings_map[item.tokenId] = {"seller": address, "amount": item.amount}
    nft_map[item.tokenId]["forSale"] = True
    return {"success": True}


class ItemBuyNFT(BaseModel):
    addressBuyer: str
    tokenId: int


class ItemCancelNFT(BaseModel):
    address: str
    tokenId: int


@app.post("/cancelListing")
async def cancel_listing(item: ItemCancelNFT):
    nft_map[item.tokenId]["forSale"] = False
    try:
        nft_listings_map.pop(item.tokenId)
    except:
        pass
    return {"success": True}


@app.post("/buyNFT")
async def buy_nft(item: ItemBuyNFT):
    # Completes a trade...
    nft_data = nft_listings_map[item.tokenId]
    # nft_data["seller"]
    # nft_data["amount"]

    # In DB - change token balances of each user involved
    bal_db_seller = await read_balance_one(item.addressBuyer)
    bal_db_buyer = await read_balance_one(nft_data["seller"])

    # Buyer MUST have enough funds to buy it...
    # [{"address":"0x123","onChainBal":115,"localBal":21,"inPlay":456}]
    assert bal_db_buyer["localBal"] >= nft_data["amount"]

    # Do this first, since they might not have called 'approve' on the nft
    await transfer_nft(nft_data["seller"], item.addressBuyer, item.tokenId)

    await update_balance(
        bal_db_buyer["onChainBal"],
        bal_db_buyer["localBal"] - nft_data["amount"],
        bal_db_buyer["inPlay"],
        bal_db_buyer["address"],
    )
    await update_balance(
        bal_db_seller["onChainBal"],
        bal_db_seller["localBal"] + nft_data["amount"],
        bal_db_seller["inPlay"],
        bal_db_seller["address"],
    )

    # And need to update our local mapping too
    if item.addressBuyer not in nft_owners:
        nft_owners[item.addressBuyer] = []
    nft_owners[item.addressBuyer].append(item.tokenId)
    nft_owners[nft_data["seller"]].remove(item.tokenId)
    nft_map[item.tokenId]["forSale"] = False
    nft_listings_map.pop(item.tokenId)


@app.get("/getListings")
async def get_listings():
    ret_data = []
    # {"seller": item.address, "amount": item.amount}
    for tokenId in nft_listings_map:
        nft_listings_map[tokenId]
        ret_data.append(
            {
                "tokenId": tokenId,
                "seller": nft_listings_map[tokenId]["seller"],
                "amount": nft_listings_map[tokenId]["amount"],
                "metadata": nft_map[tokenId],
            }
        )
    return {"data": ret_data}


class ItemAirdrop(BaseModel):
    address: str


@app.post("/airdrop")
async def do_airdrop(item: ItemAirdrop):
    address = Web3.to_checksum_address(item.address)

    # Hardcode the amount we'll send to them...
    # .001 eth =
    amount_wei = 10**15

    # 5. Call the withdraw function on the TokenVault contract
    private_key = os.environ["PRIVATE_KEY"]
    account = Account.from_key(private_key)
    account_address = account.address
    nonce = await web3.eth.get_transaction_count(account_address)
    gas_price = await web3.eth.gas_price

    # Build the transaction
    tx = {
        "nonce": nonce,
        "to": address,
        "value": amount_wei,
        "gas": 21000,
        "gasPrice": gas_price,
        "from": account_address,
        "chainId": 84532,
    }

    signed_tx = web3.eth.account.sign_transaction(tx, private_key)
    tx_hash = await web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    print("DONE", tx_hash)
    return {"success": True}


@app.get("/getGamestate")
async def get_gamestate(tableId: str):
    if tableId not in TABLE_STORE:
        return {"success": False, "error": "Table not found!"}
    poker_table_obj = TABLE_STORE[tableId]
    return {"data": poker_table_obj.serialize()}


class ItemSetTokens(BaseModel):
    address: str
    depositAmount: int


@app.post("/setTokens")
async def set_tokens(item: ItemSetTokens):
    address = item.address
    deposit_amount = item.depositAmount
    deposit_amount = int(deposit_amount)
    # So get the DIFF between what they have and what we've tracked

    # {"address":"0x123","onChainBal":115,"localBal":21,"inPlay":456}
    try:
        bal_db = await read_balance_one(address)
        on_chain_bal_new = 0
        local_bal_new = bal_db["localBal"] + deposit_amount
        await update_balance(on_chain_bal_new, local_bal_new, bal_db["inPlay"], address)
    except:
        # {"address":"0x123","onChainBal":115,"localBal":21,"inPlay":456}
        on_chain_bal_new = 0
        local_bal_new = deposit_amount
        print("CREATING NEW USER...", address, on_chain_bal_new, local_bal_new, 0)
        await create_user(address, on_chain_bal_new, local_bal_new, 0)

    return {"success": True}


# RUN:
# uvicorn fastapp:socket_app --host 127.0.0.1 --port 8000
