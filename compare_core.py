"""Comparison table and charts for two cities (from the weather comparison project)."""
import io

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COLORS = ["#e8743b", "#2a6fdb"]
METRICS = ["Days of data", "Average high (F)", "Average low (F)", "Hottest day (F)",
           "Coldest night (F)", "Rainy days (%)", "Total rain (in)", "Average max wind (mph)"]


def comparison_table(frames):
    """frames: {city label: DataFrame}. Returns {city label: {metric: value}}."""
    table = {}
    for city, df in frames.items():
        table[city] = {
            "Days of data": int(len(df)),
            "Average high (F)": round(float(df["temp_high_f"].mean()), 1),
            "Average low (F)": round(float(df["temp_low_f"].mean()), 1),
            "Hottest day (F)": round(float(df["temp_high_f"].max()), 1),
            "Coldest night (F)": round(float(df["temp_low_f"].min()), 1),
            "Rainy days (%)": round(float((df["precip_in"] >= 0.01).mean() * 100), 1),
            "Total rain (in)": round(float(df["precip_in"].sum()), 1),
            "Average max wind (mph)": round(float(df["wind_max_mph"].mean()), 1),
        }
    return table


def takeaways(table):
    """A few plain-English findings."""
    (a, ta), (b, tb) = list(table.items())[:2]
    out = []
    gap = ta["Average high (F)"] - tb["Average high (F)"]
    if abs(gap) < 0.5:
        out.append(f"{a} and {b} have almost the same average high.")
    else:
        warm, cool = (a, b) if gap > 0 else (b, a)
        out.append(f"{warm} is warmer: its average high is {abs(gap):.1f} F above {cool}'s.")
    ra, rb = ta["Total rain (in)"], tb["Total rain (in)"]
    if min(ra, rb) > 0:
        wet, dry = (a, b) if ra >= rb else (b, a)
        out.append(f"{wet} is wetter: about {max(ra, rb) / min(ra, rb):.1f}x "
                   f"the rainfall of {dry}.")
    elif max(ra, rb) > 0:
        out.append(f"{a if ra > rb else b} had rain while the other city had none recorded.")
    return out


def _png(fig):
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return buf.getvalue()


def temperature_chart(frames):
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, (city, df) in enumerate(frames.items()):
        color = COLORS[i % len(COLORS)]
        ax.plot(df["date"], df["temp_high_f"].rolling(30, min_periods=10).mean(),
                color=color, linewidth=2.5, label=f"{city} high")
        ax.plot(df["date"], df["temp_low_f"].rolling(30, min_periods=10).mean(),
                color=color, linewidth=2, linestyle="--", label=f"{city} low")
    ax.set_title("Temperature Comparison (30-day averages)", fontsize=14, fontweight="bold")
    ax.set_ylabel("Temperature (F)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    return _png(fig)


def rainfall_chart(frames):
    monthly = pd.DataFrame({city: df.groupby(df["date"].dt.to_period("M"))["precip_in"].sum()
                            for city, df in frames.items()}).fillna(0)
    labels = monthly.index.astype(str)
    width = 0.8 / len(monthly.columns)
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, city in enumerate(monthly.columns):
        positions = [j - 0.4 + width * (i + 0.5) for j in range(len(monthly))]
        ax.bar(positions, monthly[city], width, label=city, color=COLORS[i % len(COLORS)])
    step = max(1, len(labels) // 12)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels(labels[::step], rotation=45, ha="right")
    ax.set_title("Monthly Rainfall Comparison", fontsize=14, fontweight="bold")
    ax.set_ylabel("Rain (inches)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend()
    return _png(fig)


def combined_csv(frames):
    data = pd.concat([df.assign(city=city) for city, df in frames.items()], ignore_index=True)
    cols = ["date", "city", "temp_high_f", "temp_low_f", "precip_in", "wind_max_mph"]
    return data[cols].to_csv(index=False, date_format="%Y-%m-%d").encode()
