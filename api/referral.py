from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel, Field
from web3 import Web3

from database_utils import get_db_connection


router = APIRouter()

class ReferrerUpdate(BaseModel):
    user_address: str
    x_account: str


@router.post("/addReferrer")
async def add_referrer(referrer_update: ReferrerUpdate):
    connection = await get_db_connection()
    async with connection.cursor() as cursor:
        # Find the address associated with the given x_account
        await cursor.execute(
            """
            SELECT address FROM user_balances
            WHERE x_account = %s
            """,
            (referrer_update.x_account,),
        )
        referrer = await cursor.fetchone()
        if not referrer:
            raise HTTPException(status_code=404, detail="Referrer x_account not found")

        # Convert both addresses to checksum format for comparison
        user_address_checksum = Web3.to_checksum_address(referrer_update.user_address)
        referrer_address_checksum = Web3.to_checksum_address(referrer[0])

        # Check if the user is trying to refer themselves
        if user_address_checksum == referrer_address_checksum:
            raise HTTPException(status_code=400, detail="Self-referral is not allowed")

        print('Referrer:', referrer[0])
        # Update the referrer_address of the user
        try:
            # Start a transaction
            await connection.begin()
            # Update the referrer_address of the user
            await cursor.execute(
                """
                UPDATE user_balances
                SET referrer_address = %s
                WHERE address = %s
                """,
                (referrer[0], user_address_checksum),
            )
            # Atomically increment the referee_count for the referrer
            await cursor.execute(
                """
                UPDATE user_balances
                SET referee_count = referee_count + 1
                WHERE address = %s
                """,
                (referrer[0],),
            )
            # Commit the transaction
            await connection.commit()
        except Exception as e:
            # Rollback in case of error
            await connection.rollback()
            raise HTTPException(status_code=400, detail="Error updating referrer") from e
        finally:
            # Ensure the connection is closed
            connection.close()
    return {"message": "Referrer updated successfully"}

@router.get("/getReferrer/{user_address}")
async def get_referrer(user_address: str):
    connection = await get_db_connection()
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT referrer_address FROM user_balances
            WHERE address = %s
            """,
            (user_address,),
        )
        referrer = await cursor.fetchone()
        if not referrer:
            raise HTTPException(status_code=404, detail="User not found")
        return {"referrer": referrer[0]}

@router.get("/getNumberOfReferee/{referrer_identifier}")
async def get_number_of_referee(referrer_identifier: str):
    connection = await get_db_connection()
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT referee_count FROM user_balances
            WHERE address = %s
            """,
            (referrer_identifier,),
        )
        result = await cursor.fetchone()
        if result:
            return {"number_of_referees": result[0]}
        else:
            return {"number_of_referees": 0}

@router.get("/getReferees/{referrer_identifier}")
async def get_referees(referrer_identifier: str):
    connection = await get_db_connection()
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT address FROM user_balances
            WHERE referrer_address = %s
            """,
            (referrer_identifier,),
        )
        referees = await cursor.fetchall()
        if not referees:
            raise HTTPException(status_code=404, detail="Referrer not found or has no referees")
        return {"referees": [referee[0] for referee in referees]}