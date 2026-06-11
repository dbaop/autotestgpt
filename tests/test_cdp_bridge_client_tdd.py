from service.cdp_bridge_client import CdpBridgeClient


def test_main_cdp_bridge_health_check_posts_initialize_body():
    from pathlib import Path

    source = Path("main.py").read_text(encoding="utf-8")

    assert '"http://localhost:18700/mcp"' in source
    assert "data=data" in source
    assert 'method="POST"' in source


def test_cdp_bridge_call_parses_structured_content_result(monkeypatch):
    client = CdpBridgeClient()
    client._available = True

    def fake_post(method, params=None, init=False):
        return {
            "structuredContent": {
                "result": '{"tabs":[{"id":"tab-1","url":"https://example.test","title":"Example"}]}'
            },
            "isError": False,
        }

    monkeypatch.setattr(client, "_post", fake_post)

    result = client.get_tabs()

    assert result["ok"] is True
    assert result["tabs"][0]["id"] == "tab-1"


def test_cdp_bridge_navigate_returns_error_for_error_status(monkeypatch):
    client = CdpBridgeClient()
    client._available = True

    def fake_post(method, params=None, init=False):
        return {
            "content": [
                {
                    "type": "text",
                    "text": '{"status":"error","error":"extension not paired"}',
                }
            ],
            "isError": True,
        }

    monkeypatch.setattr(client, "_post", fake_post)

    result = client.navigate("https://example.test")

    assert result["ok"] is False
    assert "extension not paired" in result["error"]
