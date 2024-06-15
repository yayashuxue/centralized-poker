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