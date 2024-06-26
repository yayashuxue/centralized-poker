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
import poker_app, referral
from database_utils import get_db_connection, read_balance_one, update_balance

locks = {}

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
app.include_router(poker_app.router)
app.include_router(referral.router)

# Wrap the Socket.IO server with ASGI middleware
socket_app = ASGIApp(poker_app.sio, other_asgi_app=app)


class CreateNftItem(BaseModel):
    tokenId: int
    address: str


class ItemDeposit(BaseModel):
    address: str
    depositAmount: str

class ItemSetTokens(BaseModel):
    address: str
    depositAmount: int

def get_nft_holders():
    # Fine for this to be non-async, only runs on startup
    w3 = Web3(Web3.HTTPProvider(alchemy_url)) # if alchemy_url else Web3(Web3.HTTPProvider(infura_url))
    print(w3)
    # Create a contract instance
    nft_contract = w3.eth.contract(address=nft_contract_address, abi=nft_contract_abi)

    holders = {}
    # Cache previous one to save on calls...
    # fmt: off
    # holders = {'0xD9F8bf1F266E50Bb4dE528007f28c14bb7edaff7': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 42, 43, 44, 45, 46, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 101, 102, 103, 104, 105, 107], '0xC52178a1b28AbF7734b259c27956acBFd67d4636': [41, 47, 96, 97, 98, 99, 100, 106], '0x534631Bcf33BDb069fB20A93d2fdb9e4D4dD42CF': [48], '0x459e213D8B5E79d706aB22b945e3aF983d51BC4C': [108]}
    # fmt: on
    # holders = {Web3.to_checksum_address(x): holders[x] for x in holders}
    # print(holders)
    token_id = 0
    # for addr in holders:
    #     max_token_id = max(holders[addr])
    #     token_id = max(token_id, max_token_id)

    fails = 0
    count = 0
    while count < 1000:
        try:
            owner = None
            owner = nft_contract.functions.ownerOf(token_id).call()
            owner = Web3.to_checksum_address(owner)
            if owner in holders:
                holders[owner].append(token_id)
            else:
                holders[owner] = [token_id]
            # time.sleep(0.25)
        except Exception as e:
            print("FAILED", token_id, owner)
            fails += 1
            # time.sleep(5)
            if fails >= 20:
                print("CRASHED ON", token_id, owner)
                break
        finally:
            token_id += 1
            count += 1
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
nft_owners = get_nft_holders()


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

@app.get("/getUser/{address}")
async def get_user(address: str):
    address = Web3.to_checksum_address(address)
    connection = await get_db_connection()
    async with connection.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT * FROM user_balances WHERE address = %s", (address,))
        user = await cursor.fetchone()
    connection.close()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.get("/isNewUser/{address}")
async def is_new_user(address: str):
    address = Web3.to_checksum_address(address)
    connection = await get_db_connection()
    async with connection.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT * FROM user_balances WHERE address = %s", (address,))
        user = await cursor.fetchone()
    connection.close()
    return {"isNewUser": user is None}

class User(BaseModel):
    address: str
    onChainBal: int
    localBal: int
    inPlay: int
    referrer_address: Optional[str] = Field(None)
    x_account: Optional[str] = Field(None)

class WalletUser(BaseModel):
    address: str
    referrer_address: Optional[str] = Field(None) # Dummy field for now
    x_account: Optional[str] = Field(None)

# @app.post("/users")
# async def create_user(user: User):
async def create_user(address, on_chain_bal, local_bal, in_play, x_account=None):
    address = Web3.to_checksum_address(address)
    connection = await get_db_connection()
    async with connection.cursor() as cursor:
        # Check if user already exists
        await cursor.execute(
            """
            SELECT * FROM user_balances WHERE address = %s
            """,
            (address,),
        )
        result = await cursor.fetchone()
        if result:
            return {"message": "User already exists"}

        # If user does not exist, create new user
        try:
            await cursor.execute(
                """
                INSERT INTO user_balances (address, onChainBal, localBal, inPlay, x_account) 
                VALUES (%s, %s, %s, %s, %s)
                """,
                (address, str(on_chain_bal), str(local_bal), str(in_play), x_account),
            )
            await connection.commit()
        except Exception as e:
            await connection.rollback()
            raise HTTPException(status_code=400, detail="Error creating user") from e
    connection.close()
    return {"message": "User created successfully"}


@app.post("/createUser")
async def createUser(user: WalletUser):
    print("connectWallet called with user:", user)
    connection = await get_db_connection()
    print("Database connection obtained")

    async with connection.cursor() as cursor:
        print("Cursor obtained")
        # Check if x_account already exists
        await cursor.execute(
            """
            SELECT 1 FROM user_balances
            WHERE x_account = %s
            """,
            (user.x_account,)
        )
        result = await cursor.fetchone()
        print(f"Query result for existing x_account: {result}")
        if result:
            print("x_account already exists, raising HTTPException")
            raise HTTPException(status_code=400, detail="x_account already exists")

        # If no existing x_account, proceed to create the user
        try:
            print("Proceeding to create user")
            # Pass default values for the other parameters
            response = await create_user(user.address, 0, 0, 0, user.x_account)
            print(f"User created successfully: {response}")

            # response = await referral.add_referrer(user_address=user.address, x_account=user.x_account)
            return response
        except HTTPException as e:
            print(f"Error creating user: {e}")
            raise e

class UserUpdate(BaseModel):
    address: str = Field(...)
    x_account: Optional[str] = Field(None)

async def update_x_account(address, x_account):
    address = Web3.to_checksum_address(address)
    connection = await get_db_connection()

    async with connection.cursor() as cursor:
        # Check if x_account already exists for a different address
        await cursor.execute(
            """
            SELECT address FROM user_balances
            WHERE x_account = %s AND address != %s
            """,
            (x_account, address),
        )
        existing = await cursor.fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="x_account already exists for another address")

        # Proceed with update if no existing x_account found
        try:
            await cursor.execute(
                """
                UPDATE user_balances
                SET x_account = %s
                WHERE address = %s
                """,
                (x_account, address),
            )
            await connection.commit()
        except Exception as e:
            await connection.rollback()
            raise HTTPException(status_code=400, detail=str(e))

@app.put("/updateUser")
async def update_user(user: UserUpdate):
    print("UPDATING USER", user)
    try:
        response = await update_x_account(user.address, user.x_account)
        return response
    except HTTPException as e:
        raise e
    

class UserBalance(BaseModel):
    address: str
    onChainBal: int
    localBal: int
    inPlay: int


# @app.put("/balances")
# async def update_balance(balance: UserBalance):
# async def update_balance(on_chain_bal_new, local_bal_new, inPlay, address):
#     # (balance.onChainBal, balance.localBal, balance.inPlay, balance.address),
#     address = Web3.to_checksum_address(address)
#     connection = await get_db_connection()
#     print("ACTUALLY SETTING FOR ADDR", address)
#     async with connection.cursor() as cursor:
#         try:
#             await cursor.execute(
#                 """
#                 UPDATE user_balances 
#                 SET onChainBal = %s, localBal = %s, inPlay = %s 
#                 WHERE address = %s
#             """,
#                 (str(on_chain_bal_new), str(local_bal_new), str(inPlay), address),
#             )
#             await connection.commit()
#         except Exception as e:
#             await connection.rollback()
#             raise HTTPException(status_code=400, detail="Error updating balance") from e
#     connection.close()
#     return {"message": "Balance updated successfully"}


# async def read_balance_one(address: str):
#     connection = await get_db_connection()
#     address = Web3.to_checksum_address(address)
#     async with connection.cursor(aiomysql.DictCursor) as cursor:
#         await cursor.execute(
#             "SELECT * FROM user_balances WHERE address = %s", (address,)
#         )
#         balance = await cursor.fetchone()
#         if balance is None:
#             raise HTTPException(status_code=404, detail="User not found")
#         # db entries are now strings
#         balance["onChainBal"] = int(float(balance["onChainBal"]))
#         balance["localBal"] = int(float(balance["localBal"]))
#         balance["inPlay"] = int(float(balance["inPlay"]))
#     connection.close()
#     return balance


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
    user_bal = bal.get("localBal", 0)
    user_bal = 0 if not user_bal else user_bal
    time_elapsed = time.time() - START_TIME

    # """
    earning_rate = calculate_earning_rate(address)
    # Annualized rate - compare to total token supply
    earnings_pct = (time_elapsed / (60 * 60 * 24 * 365)) * earning_rate
    bonus_earnings = int(earnings_pct * TOTAL_TOKENS) # TODO: problematic 
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
                    "twitter": user["x_account"],
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
