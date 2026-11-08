
from pathlib import Path
import json
import warnings

import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

warnings.filterwarnings("ignore")


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "room_climate_all_rooms.csv"
RESULT_DIR = BASE_DIR / "results"

RESULT_DIR.mkdir(parents=True, exist_ok=True)

FREQUENCY = "15min"
HORIZONS = [1, 2, 3, 4]

MIN_COMPLETENESS = 70.0
MAX_DATA_AGE_MINUTES = 60

LAGS = [0, 1, 2, 4, 8, 96, 672]


# ============================================================
# 1. LOAD DATA
# ============================================================

def load_data():

    if not DATA_FILE.exists():
        raise FileNotFoundError(f"CSV nicht gefunden: {DATA_FILE}")

    print("Lade Raumklimadaten ...")

    df = pd.read_csv(DATA_FILE)

    required = {"timestamp", "room_id", "temperature_c"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"Fehlende CSV-Spalten: {missing}")

    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True, errors="coerce"
    )

    df["temperature_c"] = pd.to_numeric(
        df["temperature_c"], errors="coerce"
    )

    df = df.dropna(subset=["timestamp", "room_id"])

    df["room_id"] = df["room_id"].astype(str)

    if "temperature_conflict" in df.columns:
        conflicts = df["temperature_conflict"].astype(str).str.lower().isin(
            ["true", "1", "yes"]
        )
        df.loc[conflicts, "temperature_c"] = np.nan

    df = df.sort_values(["room_id", "timestamp"])

    print(f"Datensätze geladen: {len(df):,}")
    print(f"Räume gefunden: {df['room_id'].nunique()}")

    return df


# ============================================================
# 2. DATA QUALITY
# ============================================================

def evaluate_data_quality(df):

    global_latest = df["timestamp"].max()
    quality = []

    for room_id, group in df.groupby("room_id"):

        group = group.sort_values("timestamp")

        series = (
            group.drop_duplicates("timestamp")
            .set_index("timestamp")["temperature_c"]
            .sort_index()
        )

        full_index = pd.date_range(
            start=series.index.min(),
            end=series.index.max(),
            freq=FREQUENCY,
            tz="UTC"
        )

        aligned = series.reindex(full_index)

        completeness = aligned.notna().mean() * 100
        last_valid = aligned.last_valid_index()

        age_minutes = (
            (global_latest - last_valid).total_seconds() / 60
            if last_valid is not None else np.inf
        )

        eligible = (
            completeness >= MIN_COMPLETENESS
            and age_minutes <= MAX_DATA_AGE_MINUTES
        )

        quality.append({
            "room_id": room_id,
            "total_intervals": len(aligned),
            "valid_intervals": int(aligned.notna().sum()),
            "completeness_percent": round(completeness, 2),
            "last_measurement": last_valid,
            "data_age_minutes": round(age_minutes, 2),
            "status": "eligible" if eligible else "insufficient_data"
        })

    result = pd.DataFrame(quality)
    result.to_csv(RESULT_DIR / "data_quality.csv", index=False)

    return result


# ============================================================
# 3. FEATURES
# ============================================================

def create_features(series):

    frame = pd.DataFrame(index=series.index)

    frame["temperature_current"] = series

    for lag in LAGS[1:]:
        frame[f"temperature_lag_{lag}"] = series.shift(lag)

    frame["hour_sin"] = np.sin(
        2 * np.pi * frame.index.hour / 24
    )

    frame["hour_cos"] = np.cos(
        2 * np.pi * frame.index.hour / 24
    )

    frame["weekday_sin"] = np.sin(
        2 * np.pi * frame.index.dayofweek / 7
    )

    frame["weekday_cos"] = np.cos(
        2 * np.pi * frame.index.dayofweek / 7
    )

    return frame


# ============================================================
# 4. MODEL EVALUATION AND FORECASTING
# ============================================================

def calculate_metrics(actual, predicted):

    return {
        "MAE": mean_absolute_error(actual, predicted),
        "RMSE": np.sqrt(mean_squared_error(actual, predicted))
    }


def train_room_model(room_id, series):

    features = create_features(series)

    room_results = []
    forecasts = []

    for horizon in HORIZONS:

        target = series.shift(-horizon)
        dataset = features.copy()
        dataset["target"] = target

        # No imputation of target values.
        dataset = dataset.dropna()

        if len(dataset) < 500:
            continue

        X = dataset.drop(columns="target")
        y = dataset["target"]

        # Chronological 70 / 15 / 15 split.
        n = len(dataset)
        train_end = int(n * 0.70)
        val_end = int(n * 0.85)

        X_train = X.iloc[:train_end]
        y_train = y.iloc[:train_end]

        X_val = X.iloc[train_end:val_end]
        y_val = y.iloc[train_end:val_end]

        X_test = X.iloc[val_end:]
        y_test = y.iloc[val_end:]

        if len(X_val) == 0 or len(X_test) == 0:
            continue

        # Persistence baseline: latest known temperature.
        persistence_val = X_val["temperature_current"].values

        rf = RandomForestRegressor(
            n_estimators=200,
            max_depth=15,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )

        rf.fit(X_train, y_train)

        rf_val = rf.predict(X_val)

        persistence_mae = mean_absolute_error(
            y_val, persistence_val
        )

        rf_mae = mean_absolute_error(y_val, rf_val)

        selected = (
            "random_forest"
            if rf_mae < persistence_mae
            else "persistence"
        )

        # Evaluate selected model on untouched test data.
        if selected == "random_forest":
            prediction_test = rf.predict(X_test)
        else:
            prediction_test = X_test["temperature_current"].values

        metrics = calculate_metrics(y_test, prediction_test)

        room_results.append({
            "room_id": room_id,
            "horizon_minutes": horizon * 15,
            "selected_model": selected,
            "validation_persistence_mae": persistence_mae,
            "validation_rf_mae": rf_mae,
            "test_mae": metrics["MAE"],
            "test_rmse": metrics["RMSE"],
            "test_samples": len(y_test)
        })

        # Refit the selected RF using all available historical data.
        # The final model exists only in memory.
        if selected == "random_forest":

            final_model = RandomForestRegressor(
                n_estimators=200,
                max_depth=15,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1
            )

            final_model.fit(X, y)

        # Forecast from the latest observation with complete features.
        latest_features = features.dropna()

        if not latest_features.empty:

            latest = latest_features.iloc[[-1]]
            origin = latest.index[0]

            if selected == "random_forest":
                forecast_value = float(final_model.predict(latest)[0])
            else:
                forecast_value = float(
                    latest["temperature_current"].iloc[0]
                )

            forecasts.append({
                "room_id": room_id,
                "forecast_origin": origin,
                "forecast_timestamp": (
                    origin + pd.Timedelta(minutes=horizon * 15)
                ),
                "horizon_minutes": horizon * 15,
                "predicted_temperature_c": forecast_value,
                "model_type": selected
            })

    return room_results, forecasts


# ============================================================
# 5. MULTI-ROOM PIPELINE
# ============================================================

def main():

    df = load_data()

    quality = evaluate_data_quality(df)

    all_results = []
    all_forecasts = []

    eligible_rooms = quality.loc[
        quality["status"] == "eligible", "room_id"
    ].tolist()

    print("\nDatenqualitätsübersicht:")
    print(quality[["room_id", "completeness_percent", "status"]].to_string(
        index=False
    ))

    print(f"\nForecast-fähige Räume: {len(eligible_rooms)}")
    print(f"Nicht geeignete Räume: {len(quality) - len(eligible_rooms)}")

    for room_id in eligible_rooms:

        print(f"\nTrainiere Raum: {room_id}")

        room_data = df[df["room_id"] == room_id]

        series = (
            room_data.drop_duplicates("timestamp")
            .set_index("timestamp")["temperature_c"]
            .sort_index()
        )

        full_index = pd.date_range(
            start=series.index.min(),
            end=series.index.max(),
            freq=FREQUENCY,
            tz="UTC"
        )

        series = series.reindex(full_index)

        results, forecasts = train_room_model(room_id, series)

        all_results.extend(results)
        all_forecasts.extend(forecasts)

    pd.DataFrame(all_results).to_csv(
        RESULT_DIR / "evaluation_results.csv", index=False
    )

    pd.DataFrame(all_forecasts).to_csv(
        RESULT_DIR / "forecasts.csv", index=False
    )

    summary = {
        "total_rooms": int(len(quality)),
        "eligible_rooms": int(len(eligible_rooms)),
        "insufficient_data_rooms": int(
            len(quality) - len(eligible_rooms)
        ),
        "trained_room_horizon_pairs": len(all_results),
        "generated_forecasts": len(all_forecasts)
    }

    with open(RESULT_DIR / "summary.json", "w") as f:
        json.dump(summary, f, indent=4)

    print("\n======================================")
    print("MULTI-ROOM FORECASTING ABGESCHLOSSEN")
    print("======================================")
    print(json.dumps(summary, indent=4))


if __name__ == "__main__":
    main()
