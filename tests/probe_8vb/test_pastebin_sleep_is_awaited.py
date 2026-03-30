import ast

def test_pastebin_sleep_is_awaited():
    src = open("discovery/ti_feed_adapter.py").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and \
           node.name == "scrape_pastebin_for_keyword":
            func_src = ast.unparse(node)
            assert "await asyncio.sleep" in func_src, \
                "asyncio.sleep musí být awaited!"
            break
