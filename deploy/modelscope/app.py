"""ModelScope Streamlit entrypoint; main platform UI lives in platform_app.py."""
from pathlib import Path
import runpy
from cloud_storage import initialize_storage
from smartprice_src import data_access
ROOT=Path(__file__).resolve().parent
data_access.DB_PATH=initialize_storage(ROOT/'data/database/smartprice_ai.db')
runpy.run_path(str(ROOT/'platform_app.py'),run_name='__main__')
