import json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from .data_access import load_daily_operating_frame

def build_forecast_frame(db_path=None):
    df = load_daily_operating_frame(db_path).copy()
    df = df.sort_values("date").reset_index(drop=True)
    df["lag_1_visitors"] = df["actual_visitors"].shift(1)
    df["lag_7_visitors"] = df["actual_visitors"].shift(7)
    df["rolling_7d_mean_visitors"] = df["actual_visitors"].shift(1).rolling(7).mean()
    df["month_sin"] = np.sin(2 * np.pi * df["month_num"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month_num"] / 12)
    df["weekday_sin"] = np.sin(2 * np.pi * df["weekday_num"] / 7)
    df["weekday_cos"] = np.cos(2 * np.pi * df["weekday_num"] / 7)
    return df.dropna(subset=["lag_1_visitors", "lag_7_visitors", "rolling_7d_mean_visitors"]).reset_index(drop=True)

def run_forecast_backtest(db_path=None, model_dir=None, report_dir=None, split_date="2025-11-01"):
    df = build_forecast_frame(db_path)
    categorical = pd.get_dummies(df["weather_type"], prefix="weather", dtype=int)
    features = pd.concat([
        df[[
            "avg_temp_c", "precipitation_mm", "marketing_campaign_flag",
            "special_event_flag", "planned_open_hours", "is_weekend",
            "is_holiday", "is_school_vacation", "month_sin", "month_cos",
            "weekday_sin", "weekday_cos", "competitor_price_cny",
            "lag_1_visitors", "lag_7_visitors", "rolling_7d_mean_visitors"
        ]].reset_index(drop=True),
        categorical.reset_index(drop=True)
    ], axis=1)
    target = df["actual_visitors"].astype(float)
    train_mask = df["date"] < pd.Timestamp(split_date)
    test_mask = ~train_mask
    if train_mask.sum() < 100 or test_mask.sum() < 30:
        raise ValueError("Not enough rows for chronological train/test split.")

    model = RandomForestRegressor(
        n_estimators=350,
        max_depth=8,
        min_samples_leaf=3,
        max_features=0.9,
        random_state=20261102,
        n_jobs=-1
    )
    model.fit(features.loc[train_mask], target.loc[train_mask])
    pred = model.predict(features.loc[test_mask])
    actual = target.loc[test_mask].to_numpy()
    baseline = df.loc[test_mask, "lag_7_visitors"].to_numpy()
    errors = actual - pred
    mae = float(mean_absolute_error(actual, pred))
    rmse = float(np.sqrt(mean_squared_error(actual, pred)))
    wape = float(np.abs(errors).sum() / max(np.abs(actual).sum(), 1))
    baseline_mae = float(mean_absolute_error(actual, baseline))
    baseline_wape = float(np.abs(actual - baseline).sum() / max(np.abs(actual).sum(), 1))
    metrics = {
        "model": "RandomForestRegressor",
        "train_period": [df.loc[train_mask, "date"].min().strftime("%Y-%m-%d"),
                         df.loc[train_mask, "date"].max().strftime("%Y-%m-%d")],
        "test_period": [df.loc[test_mask, "date"].min().strftime("%Y-%m-%d"),
                        df.loc[test_mask, "date"].max().strftime("%Y-%m-%d")],
        "train_rows": int(train_mask.sum()),
        "test_rows": int(test_mask.sum()),
        "mae_visitors": round(mae, 2),
        "rmse_visitors": round(rmse, 2),
        "wape": round(wape, 4),
        "r_squared": round(float(r2_score(actual, pred)), 4),
        "baseline_lag7_mae_visitors": round(baseline_mae, 2),
        "baseline_lag7_wape": round(baseline_wape, 4),
        "evaluation_note": (
            "Chronological holdout with rolling one-step-ahead lag features. "
            "For each test date, lag features use observed prior-day history; "
            "this is not a fixed-origin 60-day forecast."
        )
    }
    backtest = df.loc[test_mask, ["date", "actual_visitors", "lag_7_visitors"]].copy()
    backtest["predicted_visitors"] = pred
    backtest["baseline_lag7_visitors"] = baseline
    backtest["absolute_error"] = np.abs(actual - pred)
    backtest["date"] = backtest["date"].dt.strftime("%Y-%m-%d")

    if model_dir:
        model_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": model, "feature_columns": list(features.columns)}, model_dir / "visitor_forecast_model.joblib")
    if report_dir:
        report_dir.mkdir(parents=True, exist_ok=True)
        backtest.to_csv(report_dir / "visitor_forecast_backtest.csv", index=False, encoding="utf-8-sig")
        (report_dir / "visitor_forecast_metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return model, metrics, backtest
