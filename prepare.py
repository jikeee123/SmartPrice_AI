from smartprice_src.platform_core import require_valid
from smartprice_src.scenario_engine import train_forecaster
from smartprice_src.forecasting import run_forecast_backtest
from smartprice_src.data_access import ROOT
if __name__=='__main__':
    require_valid()
    run_forecast_backtest(model_dir=ROOT/'models',report_dir=ROOT/'reports'/'stage3')
    _,_,_,metrics,_=train_forecaster()
    print('Validated and retrained in current environment:',metrics)
