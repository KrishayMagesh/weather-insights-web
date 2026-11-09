"""Train and evaluate next-day high temperature models for one city.

Same method as the weather prediction project: features from today and the last few days,
a time-based train/test split, two baselines, Linear Regression and Random Forest.
"""
import io

import matplotlib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TEST_FRACTION = 0.2
TARGET = "target_high_tomorrow"
FEATURES = ["high_today", "high_yesterday", "high_2days_ago", "high_7day_avg", "low_today",
            "rain_today", "rain_3day_total", "wind_today", "season_sin", "season_cos"]
BASELINE_TODAY = "Baseline: same as today"
BASELINE_MONTH = "Baseline: monthly average"


def build_features(df):
    """One row per day: today's features and (when known) tomorrow's high."""
    g = df.sort_values("date").reset_index(drop=True)
    f = pd.DataFrame({"date": g["date"]})
    f["high_today"] = g["temp_high_f"]
    f["high_yesterday"] = g["temp_high_f"].shift(1)
    f["high_2days_ago"] = g["temp_high_f"].shift(2)
    f["high_7day_avg"] = g["temp_high_f"].rolling(7).mean()
    f["low_today"] = g["temp_low_f"]
    f["rain_today"] = g["precip_in"]
    f["rain_3day_total"] = g["precip_in"].rolling(3).sum()
    f["wind_today"] = g["wind_max_mph"]
    tomorrow = g["date"] + pd.Timedelta(days=1)
    f["season_sin"] = np.sin(2 * np.pi * tomorrow.dt.day_of_year / 365.25)
    f["season_cos"] = np.cos(2 * np.pi * tomorrow.dt.day_of_year / 365.25)
    f["tomorrow_month"] = tomorrow.dt.month
    f[TARGET] = g["temp_high_f"].shift(-1)
    return f.dropna(subset=FEATURES).reset_index(drop=True)


def make_models():
    return {
        "Linear Regression": LinearRegression(),
        "Random Forest": RandomForestRegressor(n_estimators=200, min_samples_leaf=3,
                                               random_state=42, n_jobs=1),
    }


def run_experiment(df):
    """Return (summary dict, predictions chart PNG, feature importance PNG)."""
    features = build_features(df)
    labeled = features.dropna(subset=[TARGET]).reset_index(drop=True)
    cutoff = labeled["date"].iloc[int(len(labeled) * (1 - TEST_FRACTION))]
    train, test = labeled[labeled["date"] < cutoff], labeled[labeled["date"] >= cutoff]

    monthly = train.groupby("tomorrow_month")[TARGET].mean()
    predictions = {
        BASELINE_TODAY: test["high_today"].to_numpy(),
        BASELINE_MONTH: test["tomorrow_month"].map(monthly).fillna(train[TARGET].mean())
                                              .to_numpy(),
    }
    models = make_models()
    for name, model in models.items():
        model.fit(train[FEATURES], train[TARGET])
        predictions[name] = model.predict(test[FEATURES])

    rows = []
    for name, predicted in predictions.items():
        rows.append({"method": name,
                     "mae": round(float(mean_absolute_error(test[TARGET], predicted)), 2),
                     "rmse": round(float(np.sqrt(mean_squared_error(test[TARGET], predicted))), 2),
                     "r2": round(float(r2_score(test[TARGET], predicted)), 2)})
    rows.sort(key=lambda r: r["mae"])
    mae = {r["method"]: r["mae"] for r in rows}
    best = min(models, key=lambda n: mae[n])
    baseline = mae[BASELINE_TODAY]

    # Next-day prediction: retrain the best model on every labeled day, then predict the
    # day after the most recent data.
    final = make_models()[best].fit(labeled[FEATURES], labeled[TARGET])
    last = features.iloc[[-1]]
    next_date = (last["date"].iloc[0] + pd.Timedelta(days=1)).date()

    summary = {
        "rows": rows, "best_model": best, "best_mae": mae[best], "baseline_mae": baseline,
        "improvement_pct": round((baseline - mae[best]) / baseline * 100, 1) if baseline else 0.0,
        "beat_baseline": mae[best] < baseline,
        "n_train": int(len(train)), "n_test": int(len(test)),
        "train_end": train["date"].max().date().isoformat(),
        "test_start": test["date"].min().date().isoformat(),
        "next_date": next_date.isoformat(),
        "next_high": round(float(final.predict(last[FEATURES])[0]), 1),
    }
    return summary, _predictions_png(test, predictions[best], best), \
        _importance_png(models["Random Forest"])


def _png(fig):
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return buf.getvalue()


def _predictions_png(test, predicted, name):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    days = test["date"] + pd.Timedelta(days=1)
    ax.plot(days, test[TARGET], color="black", linewidth=1.6, label="Actual high")
    ax.plot(days, predicted, color="#e8743b", linewidth=1.6, label=f"Predicted ({name})")
    ax.set_title("Predicted vs. actual daily high (test period)", fontweight="bold")
    ax.set_ylabel("Temperature (F)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    return _png(fig)


def _importance_png(forest):
    importance = pd.Series(forest.feature_importances_, index=FEATURES).sort_values()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(importance.index, importance.values, color="#2a6fdb")
    ax.set_title("Which inputs mattered most? (Random Forest)", fontweight="bold")
    ax.set_xlabel("Importance")
    return _png(fig)
