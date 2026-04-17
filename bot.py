import requests
import hmac
import hashlib
import json
import time
import os

# Paste your keys directly here for phone testing
API_KEY = "be7077710a52a1fd8568cca583106acd82e2244f7aa7f9af"
API_SECRET = b"9166de9ff3ddc3454ca8fe1f1acc5649b8feefcf3d552d6e6b64e40d87642e1d"

def get_signature(json_body):
    return hmac.new(
        API_SECRET,
        json_body.encode(),
        hashlib.sha256
    ).hexdigest()

def get_balance():
    url = "https://api.coindcx.com/exchange/v1/users/balances"
    timestamp = int(round(time.time() * 1000))
    body = {"timestamp": timestamp}
    json_body = json.dumps(body, separators=(',', ':'))
    signature = get_signature(json_body)
    headers = {
        'Content-Type': 'application/json',
        'X-AUTH-APIKEY': API_KEY,
        'X-AUTH-SIGNATURE': signature
    }
    r = requests.post(url, data=json_body, headers=headers)
    return r.json()

def get_price(pair="B-SUIINR"):
    url = f"https://public.coindcx.com/market_data/candles?pair={pair}&interval=1m&limit=20"
    r = requests.get(url)
    data = r.json()
    closes = [float(c['close']) for c in data]
    return closes

def check_signal():
    closes = get_price()
    short_ma = sum(closes[-5:]) / 5
    long_ma = sum(closes[-20:]) / 20

    if short_ma > long_ma:
        return "BUY"
    elif short_ma < long_ma:
        return "SELL"
    else:
        return "HOLD"

# Main loop
print("Bot started...")
while True:
    signal = check_signal()
    balance = get_balance()
    print(f"Signal: {signal} | Time: {time.ctime()}")
    # Uncomment below only after testing:
    # if signal == "BUY":
    #     place_order("buy", price, quantity)
    time.sleep(60)
