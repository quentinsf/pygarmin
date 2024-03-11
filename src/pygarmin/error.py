class GarminError(Exception):
    """Base class for exceptions."""
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class LinkError(GarminError):
    """Exception raised for errors in the communications link."""
    pass


class ProtocolError(GarminError):
    "Exception raised for errors in a higher-layer protocol."
    pass
