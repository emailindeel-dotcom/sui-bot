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
    closes, highs, lows, volumes = get_candles()
    if closes is None:
        return "ERROR", 0

    price     = closes[-1]
    short_ema = ema(closes[-SHORT_PERIOD*3:], SHORT_PERIOD)
    long_ema  = ema(closes[-LONG_PERIOD*3:],  LONG_PERIOD)
    rsi       = calculate_rsi(closes, RSI_PERIOD)
    macd      = calculate_macd(closes)

    # Calculate difference between EMAs
    diff    = short_ema - long_ema
    diff_pct = (diff / long_ema) * 100

    print(f"SUI Price   : {price}")
    print(f"EMA({SHORT_PERIOD})      : {round(short_ema, 4)}")
    print(f"EMA({LONG_PERIOD})      : {round(long_ema, 4)}")
    print(f"EMA Diff %  : {round(diff_pct, 4)}%")
    print(f"RSI(14)     : {rsi}")
    print(f"MACD        : {macd}")

    # ── THRESHOLD: even 0.01% difference triggers signal ──
    THRESHOLD = 0.01

    if diff_pct > THRESHOLD:
        trend = "BUY"
    elif diff_pct < -THRESHOLD:
        trend = "SELL"
    else:
        trend = "HOLD"

    # RSI filter
    if trend == "BUY"  and rsi > 75:
        trend = "HOLD"  # overbought, skip buy
    if trend == "SELL" and rsi < 25:
        trend = "HOLD"  # oversold, skip sell

    print(f"EMA Trend   : {trend}")
    print(f"RSI Filter  : {'BLOCKED' if (trend == 'HOLD' and rsi > 75) or (trend == 'HOLD' and rsi < 25) else 'PASSED'}")

    return trend, price

