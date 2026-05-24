import importlib, sys
for pkg in ("selenium","webdriver_manager"):
    try:
        importlib.import_module(pkg)
        print(pkg + " OK")
    except Exception as e:
        print(pkg + " ERROR: " + str(e))
        sys.exit(1)
