from bs4 import BeautifulSoup

def test_mojeek_parses_html():
    html = ('<ul class="results-standard">'
            '<li><a class="ob" href="http://t.com">T</a>'
            '<p class="s">Snip</p></li></ul>')
    soup = BeautifulSoup(html, "html.parser")
    a = soup.select_one("ul.results-standard li a.ob")
    assert a["href"] == "http://t.com"
