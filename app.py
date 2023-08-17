import asyncio
import json
from datetime import datetime

from flask import Flask

from flask_caching import Cache

from binance import Client, AsyncClient, BinanceSocketManager
from binance.enums import KLINE_INTERVAL_1MINUTE, ORDER_TYPE_MARKET

import numpy as np
import talib
import websocket

from config import Config

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'redis', 'CACHE_REDIS_URL': Config.redis_url})


class BotRSI:

    def __init__(self):
        self.symbol = 'ETHUSDT'
        self.client = Client(Config.api_key, Config.secret_key, testnet=True)
        print(self.client.__dict__)
        self.balance = self.client.futures_account_balance()

    def set_leverage(self, symbol, leverage):
        self.client.futures_change_leverage(symbol=symbol, leverage=leverage)

    def add_new_kline(self, new_kline, symbol):
        klines = cache.get(f'klines_{symbol}_{KLINE_INTERVAL_1MINUTE}')

        if not klines:
            klines = self.client.futures_klines(symbol=symbol, interval=KLINE_INTERVAL_1MINUTE, limit=1000)
            klines.pop(-1)
            klines = [{'close_price': kline[4], 'close_time': kline[6]} for kline in klines]

            cache.set(f'klines_{symbol}_{KLINE_INTERVAL_1MINUTE}', json.dumps(klines))

            return

        klines = json.loads(klines)

        if len(klines) > 999:
            klines.pop(0)

        klines.append(new_kline)
        self.bot_rsi(klines)
        cache.set(f'klines_{symbol}_{KLINE_INTERVAL_1MINUTE}', json.dumps(klines))

    def buy(self, symbol, quantity):
        print('RSI is oversold. Placing buy order.')

        order = self.client.futures_create_order(
            symbol=symbol,
            side='BUY',
            type='MARKET',
            quantity=quantity,
            newClientOrderId='my_order_id'
        )

        order_price = float(order['price'])
        order_status = self.client.futures_get_order(symbol=symbol, orderId=order['orderId'])
        order_price = order_price if order_price else float(order_status['avgPrice'])
        print('1!!!!!!!!!!!!!!!!!!')
        print(order_price)

        # Create the stop loss order
        stop_loss_order = self.client.futures_create_order(
            symbol=symbol,
            side='SELL',
            type='STOP_MARKET',
            quantity=quantity,
            stopPrice=int(order_price - order_price * 0.003),
            activationPrice=order_price,
            closePosition=True,
            newClientOrderId='my_stop_loss_order_id',
            timeInForce='GTE_GTC'
        )

        # Calculate the prices for the 10 take profit orders
        take_profit_prices = []
        take_profit_quantities = []
        for i in range(1, 6):
            take_profit_price = order_price + (order_price * (i * 0.001))  # 0.2% above entry price for each order
            take_profit_quantity = quantity * (1 / 10)  # 20% of original quantity for each order
            take_profit_prices.append(int(take_profit_price))
            take_profit_quantities.append(round(take_profit_quantity, 3))

        # Create the 10 take profit orders
        for i in range(5):
            if i == 4:
                take_profit_order = self.client.futures_create_order(
                    symbol=symbol,
                    side='SELL',
                    type='TAKE_PROFIT_MARKET',
                    quantity=take_profit_quantities[i],
                    stopPrice=take_profit_prices[i],
                    activationPrice=order_price,
                    newClientOrderId=f'my_take_profit_order_{i + 1}',
                    closePosition=True,
                    timeInForce='GTE_GTC'
                )
            else:
                take_profit_order = self.client.futures_create_order(
                    symbol=symbol,
                    side='SELL',
                    type='TAKE_PROFIT_MARKET',
                    quantity=take_profit_quantities[i],
                    stopPrice=take_profit_prices[i],
                    activationPrice=order_price,
                    newClientOrderId=f'my_take_profit_order_{i + 1}',
                    timeInForce='GTE_GTC',
                )

            # Print the order response
            print(take_profit_order)

    def sell(self, symbol, quantity):
        print('RSI is overbought. Placing sell order.')

        order = self.client.futures_create_order(
            symbol=symbol,
            side='SELL',
            type='MARKET',
            quantity=quantity,
            newClientOrderId='my_order_id'
        )

        order_price = float(order['price'])
        order_status = self.client.futures_get_order(symbol=symbol, orderId=order['orderId'])
        order_price = order_price if order_price else float(order_status['avgPrice'])

        print(order_price)

        # Create the stop loss order
        stop_loss_order = self.client.futures_create_order(
            symbol=symbol,
            side='BUY',
            type='STOP_MARKET',
            quantity=quantity,
            stopPrice=int(order_price + order_price * 0.003),
            activationPrice=order['price'],
            closePosition=True,
            newClientOrderId='my_stop_loss_order_id',
            timeInForce='GTE_GTC'
        )

        # Calculate the prices for the 10 take profit orders
        take_profit_prices = []
        take_profit_quantities = []
        for i in range(1, 6):
            take_profit_price = order_price - (order_price * (i * 0.001))  # 10% above entry price for each order
            take_profit_quantity = quantity * (1 / 10)  # 20% of original quantity for each order
            take_profit_prices.append(int(take_profit_price))
            take_profit_quantities.append(round(take_profit_quantity, 3))

        # Create the 10 take profit orders
        for i in range(5):
            if i == 4:
                take_profit_order = self.client.futures_create_order(
                    symbol=symbol,
                    side='BUY',
                    type='TAKE_PROFIT_MARKET',
                    quantity=take_profit_quantities[i],
                    stopPrice=take_profit_prices[i],
                    activationPrice=order_price,
                    newClientOrderId=f'my_take_profit_order_{i + 1}',
                    closePosition=True,
                    timeInForce='GTE_GTC'

                )
            else:
                take_profit_order = self.client.futures_create_order(
                    symbol=symbol,
                    side='BUY',
                    type='TAKE_PROFIT_MARKET',
                    quantity=take_profit_quantities[i],
                    stopPrice=take_profit_prices[i],
                    activationPrice=order_price,
                    newClientOrderId=f'my_take_profit_order_{i + 1}',
                    timeInForce='GTE_GTC',
                )

            # Print the order response
            print(take_profit_order)

    def get_position(self, symbol):
        position = self.client.futures_position_information(symbol=symbol)[0]

        position_profit = float(position['unRealizedProfit'])
        position_entry_price = float(position['entryPrice'])
        position_mark_price = float(position['markPrice'])
        qty = abs(float(position['positionAmt']))

        if position_entry_price != 0:
            if position_entry_price > position_mark_price:
                if position_profit > 0:
                    return {'side': 'SELL', 'qty': qty, 'symbol': symbol}
                elif position_profit < 0:
                    return {'side': 'BUY', 'qty': qty, 'symbol': symbol}
            elif position_entry_price < position_mark_price:
                if position_profit > 0:
                    return {'side': 'BUY', 'qty': qty, 'symbol': symbol}
                elif position_profit < 0:
                    return {'side': 'SELL', 'qty': qty, 'symbol': symbol}
        else:
            return {'side': 'position does not exist'}

    def close_position(self, position):
        side = "BUY" if position['side'] == "SELL" else "SELL"

        order = self.client.futures_create_order(
            symbol=position['symbol'],
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=position['qty']
        )

    def bot_rsi(self, klines):
        rsi_period = 14
        rsi_oversold = 30
        rsi_overbought = 70

        # Find the USDT balance by iterating through the balance list
        usdt_balance = [float(asset['balance']) for asset in self.balance if asset['asset'] == 'USDT'][0]
        usdt_for_position = usdt_balance * 0.10

        # Extract close prices from klines data
        klines_prices = [float(kline['close_price']) for kline in klines]
        close_prices = np.array(klines_prices)

        # Calculate RSI using talib
        rsi_values = talib.RSI(close_prices, timeperiod=rsi_period)

        # Get the latest RSI value
        latest_rsi = rsi_values[-1]
        old_rsi = rsi_values[-2]
        quantity = round(usdt_for_position / klines_prices[-1], 3)

        # Check if the RSI is oversold or overbought
        if old_rsi < rsi_oversold < latest_rsi:
            # Buy signal
            position = self.get_position(self.symbol)
            side = position['side']

            if side == 'BUY':
                ...
            elif side == 'SELL':
                # close position
                self.close_position(position)
                self.buy(self.symbol, quantity)
            else:
                self.buy(self.symbol, quantity)
        elif old_rsi > rsi_overbought > latest_rsi:
            # Sell signal
            position = self.get_position(self.symbol)
            side = position['side']

            if side == 'SELL':
                ...
            elif side == 'BUY':
                self.close_position(position)
                self.sell(self.symbol, quantity)
            else:
                self.sell(self.symbol, quantity)

    async def run_ws_klines(self):
        client = await AsyncClient.create(testnet=True)
        bm = BinanceSocketManager(client)
        # start any sockets here, i.e a trade socket
        ts = bm.kline_futures_socket(self.symbol)
        kline = {}
        # then start receiving messages
        async with ts as tscm:
            while True:
                res = await tscm.recv()
                try:
                    close_time = res['k']['T']
                    close_price = res['k']['c']
                except KeyError as error:
                    print(res)
                    print(error)

                if not kline or kline['close_time'] == close_time:
                    kline = {'close_price': float(close_price), 'close_time': close_time}

                elif kline['close_time'] != close_time:
                    print(f"{kline['close_price']}, {datetime.now()}")
                    self.add_new_kline(kline, self.symbol)  # await
                    kline = {'close_price': float(close_price), 'close_time': close_time}

        await client.close_connection()

        # Set up WebSocket connection
        ws = websocket.WebSocketApp(url, on_message=on_message)

        # Start WebSocket connection
        ws.run_forever()

    def start(self):
        self.set_leverage(self.symbol, 3)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.run_ws_klines())


if __name__ == 'app':
    BotRSI().start()
