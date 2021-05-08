from prometheus_client import start_http_server, Metric, REGISTRY
from threading import Lock
from cachetools import cached, TTLCache
from requests import Session
import argparse
import json
import logging
import os
import sys
import time

# lock of the collect method
lock = Lock()

# logging setup
log = logging.getLogger('coinmarketcap-exporter')
log.setLevel(logging.INFO)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)

symbol = os.environ.get('SYMBOL', 'XCH')
currency = os.environ.get('CURRENCY', 'USD')
cak = os.environ.get('COINMARKETCAP_API_KEY')
# caching API for 50min
# Note the api limits: https://pro.coinmarketcap.com/features
cache_ttl = int(os.environ.get('CACHE_TTL', 3000))
cache_max_size = int(os.environ.get('CACHE_MAX_SIZE', 10000))
cache = TTLCache(maxsize=cache_max_size, ttl=cache_ttl)

class CoinClient():
  def __init__(self, symbol):
    self.symbol = symbol
    self.url = f'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={symbol}'
    self.headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': cak}

  @cached(cache)
  def quote(self):
    log.info('Fetching data from the API')
    session = Session()
    session.headers.update(self.headers)
    r = session.get(self.url)
    data = json.loads(r.text)
    if 'data' not in data:
      log.error('No data in response. Is your API key set?')
    return data

class CoinCollector():
  def __init__(self, symbol):
    self.client = CoinClient(symbol=symbol)
    self.symbol = symbol

  def collect(self):
    with lock:
      # query the api
      response = self.client.quote()
      metric = Metric('coin_market_quote', 'coinmarketcap quote', 'gauge')
      coinmarketmetric = f'coin_market_quote_{currency}'
      quote = response['data'][self.symbol]['quote'][currency]
      metric.add_sample(coinmarketmetric, value=float(quote['price']), labels={'symbol': self.symbol})
      yield metric

if __name__ == '__main__':
  try:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--port', nargs='?', const=9101, help='The TCP port to listen on', default=9101)
    parser.add_argument('--addr', nargs='?', const='0.0.0.0', help='The interface to bind to', default='0.0.0.0')
    args = parser.parse_args()
    log.info('listening on http://%s:%d/metrics' % (args.addr, args.port))

    REGISTRY.register(CoinCollector(symbol=symbol))
    start_http_server(int(args.port), addr=args.addr)

    while True:
      time.sleep(60)
  except KeyboardInterrupt:
    print(" Interrupted")
    exit(0)
