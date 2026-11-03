import warnings
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from .data_access import load_daily_product_features

FORMULA = (
    "np.log(net_orders) ~ np.log(list_unit_price_cny) "
    "+ is_weekend + is_holiday + is_school_vacation "
    "+ avg_temp_c + precipitation_mm "
    "+ marketing_campaign_flag + special_event_flag "
    "+ competitor_price_cny + C(weather_type) + C(month_num)"
)

def fit_price_elasticity_models(db_path=None):
    frame = load_daily_product_features(db_path)
    frame = frame.copy()
    frame = frame[
        (frame["net_orders"] > 0)
        & (frame["list_unit_price_cny"] > 0)
    ].copy()

    results = []
    model_objects = {}
    diagnostics = []
    for product_id, group in frame.groupby("product_id"):
        group = group.copy()
        if len(group) < 90:
            diagnostics.append({
                "product_id": product_id, "status": "INSUFFICIENT_DATA",
                "nobs": int(len(group)), "message": "Fewer than 90 positive-sales daily observations."
            })
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = smf.ols(FORMULA, data=group).fit(cov_type="HC3")
            term = "np.log(list_unit_price_cny)"
            ci = model.conf_int().loc[term]
            beta = float(model.params[term])
            pvalue = float(model.pvalues[term])
            results.append({
                "product_id": product_id,
                "product_name": group["product_name"].iloc[0],
                "nobs": int(model.nobs),
                "price_elasticity": beta,
                "std_error_hc3": float(model.bse[term]),
                "p_value": pvalue,
                "ci_95_lower": float(ci.iloc[0]),
                "ci_95_upper": float(ci.iloc[1]),
                "r_squared": float(model.rsquared),
                "adjusted_r_squared": float(model.rsquared_adj),
                "interpretation": (
                    "需求对价格较敏感" if beta < -1
                    else "需求对价格相对不敏感" if beta > -1
                    else "估计弹性接近单位弹性"
                ),
                "statistical_significance_5pct": bool(pvalue < 0.05),
                "model_note": "OLS log-log; HC3 robust standard errors; synthetic data"
            })
            model_objects[product_id] = model
            diagnostics.append({
                "product_id": product_id,
                "status": "FIT_OK",
                "nobs": int(model.nobs),
                "aic": float(model.aic),
                "bic": float(model.bic),
                "condition_number": float(model.condition_number),
                "message": "Product-level log-log regression with calendar and weather controls."
            })
        except Exception as exc:
            diagnostics.append({
                "product_id": product_id,
                "status": "FIT_FAILED",
                "nobs": int(len(group)),
                "message": str(exc)
            })

    return pd.DataFrame(results), model_objects, pd.DataFrame(diagnostics), frame

def predict_product_orders(model, feature_row, price_cny):
    row = feature_row.copy()
    row["list_unit_price_cny"] = float(price_cny)
    pred_log = float(model.predict(pd.DataFrame([row])).iloc[0])
    smearing = float(np.mean(np.exp(model.resid)))
    return max(0.0, float(np.exp(pred_log) * smearing))
