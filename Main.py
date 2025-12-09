import os
import time
import math
import logging
import pandas as pd
import numpy as np
from binance.client import Client

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger()

# Env vars from Railway
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
TRADE_USD = float(os.getenv("TRADE_USD", 10))
TESTNET = os.getenv("TESTNET", "true").lower() == "true"

INTERVAL = Client.KLINE_INTERVAL_1MINUTE
SMA_SHORT = 10
SMA_LONG = 50

# Initialize Binance client
client = Client(API_KEY, API_SECRET)

if TESTNET:
    client.API_URL = "https://testnet.binance.vision/api"
    log.info("Using TESTNET")
else:
    log.info("Using LIVE environment")

# Fetch klines
def get_klines(symbol, interval, limit=200):
    data = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(data, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote","trades","tb_base","tb_quote","ignore"
    ])
    df["close"] = df["close"].astype(float)
    return df

# SMA calculation
def sma(df, period):
    return df["close"].rolling(period).mean()

# Convert USD to valid Binance quantity
def get_quantity(symbol, usd):
    price = float(client.get_symbol_ticker(symbol=symbol)["price"])
    qty = usd / price

    info = client.get_symbol_info(symbol)
    for f in info["filters"]:
        if f["filterType"] == "LOT_SIZE":
            step = float(f["stepSize"])
            min_qty = float(f["minQty"])
            qty = math.floor(qty / step) * step
            if qty < min_qty:
                raise Exception("Qty below minimum for Binance")
            return qty
    return qty

# Place order
def order(side, qty):
    try:
        res = client.create_order(
            symbol=SYMBOL,
            side=side,
            type="MARKET",
            quantity=qty
        )
        log.info(f"{side} order executed: {res}")
    except Exception as e:
        log.error(f"Order failed: {e}")

# Bot loop
def run():
    log.info(f"Bot started for {SYMBOL}")
    last_signal = None

    while True:
        try:
            df = get_klines(SYMBOL, INTERVAL, limit=100)
            df["sma_short"] = sma(df, SMA_SHORT)
            df["sma_long"] = sma(df, SMA_LONG)

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            buy_signal = prev.sma_short <= prev.sma_long and latest.sma_short > latest.sma_long
            sell_signal = prev.sma_short >= prev.sma_long and latest.sma_short < latest.sma_long

            if buy_signal and last_signal != "BUY":
                qty = get_quantity(SYMBOL, TRADE_USD)
                order("BUY", qty)
                last_signal = "BUY"

            elif sell_signal and last_signal != "SELL":
                qty = get_quantity(SYMBOL, TRADE_USD)
                order("SELL", qty)
                last_signal = "SELL"

            time.sleep(25)

        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run()
