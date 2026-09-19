def test_css_is_served_without_debug(client, settings):
    settings.DEBUG = False
    r = client.get("/static/letters/access.css")
    assert r.status_code == 200
    assert b".access-form" in b"".join(r.streaming_content)


def test_logo_is_shown_on_the_form(client, app_settings):
    r = client.get("/letter/")
    assert "letters/map_logo.jpg" in r.content.decode()
    assert client.get("/static/letters/map_logo.jpg").status_code == 200
