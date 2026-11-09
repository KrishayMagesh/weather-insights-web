import compare_core
import fake_api
import weather_api
from conftest import new_client, register, token


def compare(client, a="San Jose", b="Seattle", years="2"):
    return client.post("/compare", data={"city_a": a, "city_b": b, "years": years,
                                         "csrf_token": token(client)})


def test_geocode_and_fetch():
    place = weather_api.geocode("Seattle")
    assert place["label"] == "Seattle, Washington, United States"
    start, end = weather_api.date_range(1)
    df = weather_api.fetch_daily(place["latitude"], place["longitude"], start, end)
    assert len(df) > 300 and set(weather_api.COLUMNS.values()) <= set(df.columns)


def test_table_and_takeaways():
    start, end = weather_api.date_range(2)
    frames = {name: weather_api.fetch_daily(weather_api.geocode(name)["latitude"],
                                            weather_api.geocode(name)["longitude"], start, end)
              for name in ["San Jose", "Seattle"]}
    table = compare_core.comparison_table(frames)
    assert list(table["San Jose"]) == compare_core.METRICS
    text = " ".join(compare_core.takeaways(table))
    assert "San Jose is warmer" in text and "Seattle is wetter" in text
    assert compare_core.temperature_chart(frames).startswith(b"\x89PNG")
    assert compare_core.combined_csv(frames).startswith(b"date,city,")


def test_full_comparison_flow(logged_in):
    resp = compare(logged_in)
    assert resp.status_code == 302
    page = logged_in.get(resp.headers["Location"])
    assert b"San Jose, California, United States" in page.data
    assert b"Average high (F)" in page.data
    for chart in ["temperature", "rainfall"]:
        img = logged_in.get(f"/comparisons/1/{chart}.png")
        assert img.mimetype == "image/png" and img.data.startswith(b"\x89PNG")
    assert logged_in.get("/comparisons/1/data.csv").data.startswith(b"date,city,")
    assert b"vs. Seattle" in logged_in.get("/dashboard").data


def test_bad_inputs(logged_in):
    page = logged_in.get(compare(logged_in, b="Atlantis").headers["Location"])
    assert b"Could not find a city called" in page.data
    page = logged_in.get(compare(logged_in, b="San Jose").headers["Location"])
    assert b"two different cities" in page.data
    page = logged_in.get(compare(logged_in, years="99").headers["Location"])
    assert b"valid time range" in page.data
    assert b"No comparisons yet" in page.data


def test_network_failure_is_reported(logged_in, monkeypatch):
    monkeypatch.setattr(weather_api.requests, "get", fake_api.failing_get)
    page = logged_in.get(compare(logged_in).headers["Location"])
    assert b"could not be reached" in page.data


def test_users_cannot_see_each_others_comparisons(app, logged_in):
    compare(logged_in)
    other = new_client(app)
    register(other, "mallory")
    assert other.get("/comparisons/1").status_code == 404
    assert other.get("/comparisons/1/data.csv").status_code == 404
    assert other.post("/comparisons/1/delete",
                      data={"csrf_token": token(other)}).status_code == 404


def test_delete(logged_in):
    compare(logged_in)
    logged_in.post("/comparisons/1/delete", data={"csrf_token": token(logged_in)})
    assert logged_in.get("/comparisons/1").status_code == 404
