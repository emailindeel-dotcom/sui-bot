import requests
import time
import hmac
import hashlib
import json
import pandas as pd
import os

# ================= CONFIG =================
API_KEY = "YOUR_API_KEY"
API_SECRET = b"YOUR_API_SECRET"

PAIR = "B-SUI_INR"
BAR_INTERVAL = "15m"
TRADE_AMOUNT = 50  # ₹50 per trade

BASE_URL = "https://api.coindcx.com"

position = None  # Track current position
last_trade_time = 0

# ==========================================

def get_signature(payload):
    return hmac.new(API_SECRET, payload.encode(), hashlib.sha256).hexdigest()

# Fetch candles
def get_candles():
    # Step 1: Get markets
    markets = requests.get("https://api.coindcx.com/exchange/v1/markets_details").json()

    # Step 2: Find correct symbol for SUI/INR
    pair_data = next((m for m in markets if "SUI" in m['symbol'] and "INR" in m['symbol']), None)

    if pair_data is None:
        print("SUI/INR pair not found")
        return None

    symbol = pair_data['symbol']
    print("Using symbol:", symbol)

    # Step 3: Fetch candles
    url = f"https://public.coindcx.com/market_data/candles?pair={symbol}&interval={BAR_INTERVAL}"
    response = requests.get(url)

    if response.status_code != 200:
        print("API error:", response.status_code)
        return None

    data = response.json()

    if not data:
        print("No candle data from API for:", symbol)
        return None

    # Step 4: Convert to DataFrame
    df = pd.DataFrame(data, columns=[
        "timestamp", "Open", "High", "Low", "Close", "Volume"
    ])

    df["Close"] = df["Close"].astype(float)
    df["High"] = df["High"].astype(float)
    df["Low"] = df["Low"].astype(float)

    return df

# Calculate CCI manually
def calculate_cci(df, period):
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: (abs(x - x.mean())).mean())
    cci = (tp - sma) / (0.015 * mad)
    return cci

# Signal Logic
def generate_signal(df):
    if len(df) < 600:
        return None

    df["CCI"] = calculate_cci(df, 525)
    df["CCI_SMA"] = df["CCI"].rolling(475).mean()

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # BUY crossover
    if prev["CCI"] < prev["CCI_SMA"] and curr["CCI"] > curr["CCI_SMA"]:
        return "BUY"

    # SELL crossover
    elif prev["CCI"] > prev["CCI_SMA"] and curr["CCI"] < curr["CCI_SMA"]:
        return "SELL"

    return None

# Place order
def place_order(side, quantity):
    time_stamp = int(round(time.time() * 1000))

    body = {
        "side": side,
        "order_type": "market_order",
        "market": PAIR,
        "total_quantity": quantity,
        "timestamp": time_stamp
    }

    json_body = json.dumps(body, separators=(',', ':'))
    signature = get_signature(json_body)

    headers = {
        'Content-Type': 'application/json',
        'X-AUTH-APIKEY': API_KEY,
        'X-AUTH-SIGNATURE': signature
    }

    response = requests.post(
        f"{BASE_URL}/exchange/v1/orders/create",
        data=json_body,
        headers=headers
    )

    print("Order:", side, "| Response:", response.json())

# Main bot loop
def run_bot():
    global position, last_trade_time

    print("Bot Started...")

    while True:
        try:
            df = get_candles()
            signal = generate_signal(df)

            current_price = df.iloc[-1]["Close"]
            quantity = TRADE_AMOUNT / current_price

            # Cooldown (45 min)
            if time.time() - last_trade_time < 2700:
                print("Cooldown active...")
                time.sleep(60)
                continue

            if signal == "BUY" and position != "LONG":
                print("BUY SIGNAL")
                place_order("buy", quantity)
                position = "LONG"
                last_trade_time = time.time()

            elif signal == "SELL" and position != "SHORT":
                print("SELL SIGNAL")
                place_order("sell", quantity)
                position = "SHORT"
                last_trade_time = time.time()

            else:
                print("No signal")

        except Exception as e:
            print("Error:", e)


        time.sleep(60 * 15)  # 15 min candle

# Start bot
if __name__ == "__main__":
    run_bot()
