import logging

# Set default logging handler to avoid "No handler found" warnings.
log = logging.getLogger('garmin')
log.addHandler(logging.NullHandler())
