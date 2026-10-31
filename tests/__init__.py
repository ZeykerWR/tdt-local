import logging

# Keep the library quiet while testing; assertLogs still works.
logging.getLogger("tdtlocal").addHandler(logging.NullHandler())
