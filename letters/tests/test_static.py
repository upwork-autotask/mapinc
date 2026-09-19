def test_css_is_served_without_debug(client, settings):
    settings.DEBUG = False
    r = client.get("/static/letters/access.css")
    assert r.status_code == 200
    assert b".access-form" in b"".join(r.streaming_content)
