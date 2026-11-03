"""Prepare a writable demo database without replacing existing cloud records."""
import os, shutil, tempfile, threading
from pathlib import Path
_LOCK=threading.Lock()
def initialize_storage(seed_path, storage_dir=None):
    if storage_dir is None:
        storage_dir=os.environ.get('SMARTPRICE_STORAGE_DIR')
        if not storage_dir:
            mount=Path('/mnt/workspace')
            storage_dir=mount/'smartprice_ai' if mount.is_dir() and os.access(mount,os.W_OK) else Path(tempfile.gettempdir())/'smartprice_ai'
    directory=Path(storage_dir)
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/'smartprice_ai.db'
    with _LOCK:
        if not target.exists():
            fd,name=tempfile.mkstemp(prefix='seed-',suffix='.db',dir=directory)
            os.close(fd)
            staging=Path(name)
            try:
                shutil.copyfile(seed_path,staging)
                os.replace(staging,target)
            finally:
                staging.unlink(missing_ok=True)
    return target
