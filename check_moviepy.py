import importlib, traceback
try:
    importlib.import_module('moviepy.editor')
    print('moviepy.editor import OK')
except Exception:
    traceback.print_exc()

