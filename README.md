## How to run
1. Add .env file
```
SQL_USER=flask_user_0123
SQL_PASS=<fill in>
SQL_HOST=localhost
SQL_DB=poker_app_db
INFURA_KEY=<fill in>
ALCHEMY_KEY=<fill in>
PRIVATE_KEY=<fill in>
PURE_POKER_TESTING=False
```

3. Locally initialize database through mysql
#### This will log you into a mysql shell for managing the databases
`sudo mysql -u root -p`

### Choose a password, whatever password you choose should be the one in the .env file above
`CREATE USER 'flask_user_0123'@'%' IDENTIFIED BY '<put some password here>';`

### Create the database we'll use
`CREATE DATABASE users;`

### Switch to it
`USE users;`

### Create the table we'll use
```
CREATE TABLE vacant_user_balances (
    address VARCHAR(255),
    onChainBal BIGINT,
    localBal INT,
    inPlay INT,
    referrer_address VARCHAR(255),
    x_account VARCHAR(255),
    referee_count INT
);
```
3. run
```
cd api/
uvicorn fastapp:socket_app --host 127.0.0.1 --port 8000
```

## Poker Logic Testing Guideline
0. create .env file. add PURE_POKER_TESTING=True in the file. Or type cat PURE_POKER_TESTING=True > .env in terminal
1. Go to tests/
2. pip3 install requirements.txt
3. pytest test_poker.py (install any other package that's not instaleld)

## Key files invovled:
vanillapoker/
    poker.py
    pokerutils.py
tests/
    test_poker.py
