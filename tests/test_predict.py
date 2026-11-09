import fake_api
import predict_core
import weather_api
from conftest import new_client, register, token


def train(client, city="San Jose", years="3"):
    return client.post("/predict", data={"city": city, "years": years,
                                         "csrf_token": token(client)})


def test_experiment_results():
    place = weather_api.geocode("San Jose")
    start, end = weather_api.date_range(3)
    df = weather_api.fetch_daily(place["latitude"], place["longitude"], start, end)
    summary, pred_png, imp_png = predict_core.run_experiment(df)
    methods = {r["method"] for r in summary["rows"]}
    assert methods == {"Linear Regression", "Random Forest", predict_core.BASELINE_TODAY,
                       predict_core.BASELINE_MONTH}
    assert summary["best_model"] in {"Linear Regression", "Random Forest"}
    assert summary["train_end"] < summary["test_start"]          # no time leakage
    assert summary["next_date"] > end.isoformat()
    assert 30 < summary["next_high"] < 110
    assert pred_png.startswith(b"\x89PNG") and imp_png.startswith(b"\x89PNG")


def test_features_have_no_future_data():
    place = weather_api.geocode("Seattle")
    start, end = weather_api.date_range(2)
    df = weather_api.fetch_daily(place["latitude"], place["longitude"], start, end)
    f = predict_core.build_features(df)
    # the target is tomorrow's high, and today's high must equal yesterday's target
    today = f["high_today"].iloc[1:].to_numpy()
    assert (today == f[predict_core.TARGET].iloc[:-1].to_numpy()).all()
    assert f[predict_core.TARGET].isna().iloc[-1]     # last day's tomorrow is unknown


def test_full_training_flow(logged_in):
    resp = train(logged_in)
    assert resp.status_code == 302
    page = logged_in.get(resp.headers["Location"])
    assert b"San Jose, California, United States" in page.data and b"Average error" in page.data
    for chart in ["predictions", "importance"]:
        img = logged_in.get(f"/runs/1/{chart}.png")
        assert img.mimetype == "image/png" and img.data.startswith(b"\x89PNG")
    assert b"Random Forest" in logged_in.get("/dashboard").data or \
        b"Linear Regression" in logged_in.get("/dashboard").data


def test_bad_inputs(logged_in):
    page = logged_in.get(train(logged_in, city="Atlantis").headers["Location"])
    assert b"Could not find a city called" in page.data
    page = logged_in.get(train(logged_in, years="1").headers["Location"])
    assert b"valid amount of history" in page.data
    assert b"No prediction runs yet" in page.data


def test_network_failure_is_reported(logged_in, monkeypatch):
    monkeypatch.setattr(weather_api.requests, "get", fake_api.failing_get)
    page = logged_in.get(train(logged_in).headers["Location"])
    assert b"could not be reached" in page.data


def test_users_cannot_see_each_others_runs(app, logged_in):
    train(logged_in)
    other = new_client(app)
    register(other, "mallory")
    assert other.get("/runs/1").status_code == 404
    assert other.get("/runs/1/predictions.png").status_code == 404
    assert other.post("/runs/1/delete", data={"csrf_token": token(other)}).status_code == 404


def test_delete(logged_in):
    train(logged_in)
    logged_in.post("/runs/1/delete", data={"csrf_token": token(logged_in)})
    assert logged_in.get("/runs/1").status_code == 404
