import requests
import hmac
import hashlib
import json
import time
import os

# ── API Keys ──
API_KEY    = os.environ.get("API_KEY", "your_api_key_here")
API_SECRET = os.environ.get("API_SECRET", "your_secret_here").encode()

# ── Settings ──
PAIR          = "B-SUI_USDT"
TRADE_QTY     = 10
LEVERAGE      = 5
STOP_LOSS_PCT = 1.5
TP_PCT        = 4.5
INTERVAL      = 60

CANDLE_URL  = "https://public.coindcx.com/market_data/candles?pair=B-SUI_USDT&interval=15m&limit=100"
FUTURES_URL = "https://api.coindcx.com/exchange/v1/derivatives/futures/orders/create"

in_position = False
buy_price   = 0.0
win_count   = 0
loss_count  = 0

def get_signature(json_body):
    return hmac.new(API_SECRET, json_body.encode(), hashlib.sha256).hexdigest()

def get_candles():
    try:
        r    = requests.get(CANDLE_URL, timeout=10)
        data = r.json()
        closes  = [float(c['close'])  for c in data]
        volumes = [float(c['volume']) for c in data]
        return closes, volumes
    except Exception as e:
        print(f"Candle Error: {e}")
        return None, None

def ema(closes, period):
    k   = 2 / (period + 1)
    val = sum(closes[:period]) / period
    for p in closes[period:]:
        val = p * k + val * (1 - k)
    return round(val, 6)

def rsi(closes, period=14):
    gains  = [max(closes[i]-closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1]-closes[i], 0) for i in range(1, len(closes))]
    ag = sum(gains[-period:])  / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100
    return round(100 - 100 / (1 + ag/al), 2)

def get_signal():
    closes, volumes = get_candles()
    if closes is None:
        return "ERROR", 0, {}

    price = closes[-1]
    e20   = ema(closes, 20)
    e50   = ema(closes, 50)
    r     = rsi(closes)
    gap   = round(((e20 - e50) / e50) * 100, 4)
    avg_v = sum(volumes[-20:]) / 20
    vol   = round(volumes[-1] / avg_v, 2)

    info = {
        "price": price,
        "ema20": e20,
        "ema50": e50,
        "gap"  : gap,
        "rsi"  : r,
        "vol"  : vol
    }

    # ── Signal Logic ──
    if e20 > e50 and gap > 0.1 and r < 72:
        signal = "BUY"
    elif e20 < e50 and gap < -0.1 and r > 28:
        signal = "SELL"
    else:
        signal = "HOLD"

    return signal, price, info

def place_order(side, price):
    try:
        timestamp = int(round(time.time() * 1000))
        body = {
            "timestamp":      timestamp,
            "side":           side,
            "pair":           PAIR,
            "order_type":     "limit",
            "price":          round(price, 4),
            "total_quantity": TRADE_QTY,
            "leverage":       LEVERAGE
        }
        json_body = json.dumps(body, separators=(',', ':'))
        signature = get_signature(json_body)
        headers   = {
            'Content-Type':    'application/json',
            'X-AUTH-APIKEY':   API_KEY,
            'X-AUTH-SIGNATURE': signature
        }
        r = requests.post(FUTURES_URL, data=json_body, headers=headers, timeout=10)
        print(f"  Order: {r.json()}")
        return True
    except Exception as e:
        print(f"  Order Error: {e}")
        return False

def check_exit(price):
    global in_position, buy_price, win_count, loss_count
    if not in_position:
        return None
    sl  = buy_price * (1 - STOP_LOSS_PCT / 100)
    tp  = buy_price * (1 + TP_PCT       / 100)
    pnl = round((price - buy_price) / buy_price * 100, 2)
    print(f"  Entry : {buy_price}")
    print(f"  SL    : {round(sl, 4)}")
    print(f"  TP    : {round(tp, 4)}")
    print(f"  PnL   : {pnl}%")
    if price <= sl:
        loss_count += 1
        print("  🔴 STOP LOSS")
        return "EXIT"
    if price >= tp:
        win_count += 1
        print("  🟢 TAKE PROFIT")
        return "EXIT"
    return None

# ═══════════════════════════════
print("═" * 33)
print("   SUI/USDT EMA 20/50 BOT")
print("═" * 33)
print(f" Pair     : {PAIR}")
print(f" Candles  : 15min")
print(f" EMA      : 20 / 50 crossover")
print(f" SL / TP  : {STOP_LOSS_PCT}% / {TP_PCT}%")
print(f" Leverage : {LEVERAGE}x")
print(f" Interval : {INTERVAL}s")
print("═" * 33)

while True:
    try:
        print(f"\n [{time.strftime('%H:%M:%S')}]")
        print(" ─────────────────────────────────")

        signal, price, info = get_signal()

        if signal != "ERROR":
            print(f"  Price : {info['price']}")
            print(f"  EMA20 : {info['ema20']}")
            print(f"  EMA50 : {info['ema50']}")
            print(f"  Gap   : {info['gap']}%")
            print(f"  RSI   : {info['rsi']}")
            print(f"  Vol   : {info['vol']}x")
            print(f"  Trend : {'🟢 BULLISH' if info['ema20'] > info['ema50'] else '🔴 BEARISH'}")
        
        print(f"\n  >>> SIGNAL: {signal} <<<")
        print(f"  Wins: {win_count} | Losses: {loss_count}")

        exit_sig = check_exit(price)

        if exit_sig == "EXIT":
            if place_order("sell", price):
                in_position = False
                buy_price   = 0.0

        elif signal == "BUY" and not in_position:
            if place_order("buy", price):
                in_position = True
                buy_price   = price
                print(f"  ✅ Bought at {price}")

        elif signal == "SELL" and in_position:
            if place_order("sell", price):
                in_position = False
                buy_price   = 0.0
                print(f"  ✅ Sold at {price}")

        print(" ─────────────────────────────────")
        time.sleep(INTERVAL)

    except Exception as e:
        print(f" Error: {e}")
        time.sleep(30)
