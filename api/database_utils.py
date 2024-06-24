import os
import aiomysql
from web3 import Web3, AsyncWeb3
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    BackgroundTasks,
    WebSocket,
    WebSocketDisconnect,
)


async def get_db_connection():
    connection = await aiomysql.connect(
        host=os.environ['SQL_HOST'],
        port=3306,
        user=os.environ["SQL_USER"],
        password=os.environ["SQL_PASS"],
        db="users",
    )
    return connection


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

async def update_balance(on_chain_bal_new, local_bal_new, inPlay, address):
    # (balance.onChainBal, balance.localBal, balance.inPlay, balance.address),
    address = Web3.to_checksum_address(address)
    connection = await get_db_connection()
    print("ACTUALLY SETTING FOR ADDR", address, on_chain_bal_new, local_bal_new)
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
