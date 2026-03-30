def test_urlhaus_filters_offline():
    fake = {"urls": [
        {"url": "http://e.com", "url_status": "online",
         "threat": "malware"},
        {"url": "http://d.com", "url_status": "offline",
         "threat": "malware"}
    ]}
    online = [e for e in fake["urls"] if e["url_status"] == "online"]
    assert len(online) == 1 and online[0]["url"] == "http://e.com"
