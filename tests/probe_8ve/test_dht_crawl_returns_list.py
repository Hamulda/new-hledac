import asyncio
from hledac.universal.dht.kademlia_node import crawl_dht_for_keyword


def test_dht_crawl_returns_list():
    result = asyncio.run(crawl_dht_for_keyword("malware", duration_s=1))
    assert isinstance(result, list)
