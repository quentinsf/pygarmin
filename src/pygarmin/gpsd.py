import json

class Gpsd:

    def __str__(self):
        return json.dumps(self.get_dict())


class TPV(Gpsd):

    def __init__(self, pvt):
        self.pvt = pvt
        self.mode = self._get_mode()
        self.time = self.pvt.get_datetime().astimezone().isoformat()
        self.alt_hae = self.pvt.alt
        self.alt_msl = self.pvt.get_msl_alt()
        # Gpsd assumes a confidence of 50%, and applies a correction to
        # obtain a 95% confidence circle. However, according to the
        # specification the 2-sigma (95th percentile) accuracy value is
        # provided, so no correction is needed.
        self.sep = self.pvt.epe
        self.eph = self.pvt.eph
        self.epv = self.pvt.epv
        self.geoid_sep = -self.pvt.msl_hght  # sign is opposite of garmin sign
        self.lat = self.pvt.get_posn().as_degrees().lat
        self.leapseconds = self.pvt.leap_scnds
        self.lon = self.pvt.get_posn().as_degrees().lon
        self.vel_d = -self.pvt.up  # sign is opposite of garmin sign
        self.vel_e = self.pvt.east
        self.vel_n = self.pvt.north

    def _get_mode(self, product_description=None):
        if product_description:
            fix = self.pvt.get_fix(product_description)
        else:
            fix = self.pvt.get_fix()
        if fix == '2D' or fix == '2D_diff':
            mode = 2
        elif fix == '3D' or fix == '3D_diff':
            mode = 3
        else:
            mode = 1
        return mode


    def get_dict(self):
        return {'class': 'TPV',
                'device': 'device',
                'mode': self.mode,
                'time': self.time,
                'altHAE': self.alt_hae,
                'altMSL': self.alt_msl,
                'sep': self.sep,
                'eph': self.eph,
                'epv': self.epv,
                'geoidSep': self.geoid_sep,
                'lat': self.lat,
                'leapseconds': self.leapseconds,
                'lon': self.lon,
                'velD': self.vel_d,
                'velE': self.vel_e,
                'velN': self.vel_n,
                }


class SAT(Gpsd):
    def __init__(self, sat):
        self.sat = sat
        self.prn = self.sat.get_prn()
        self.az = self.sat.azmth        # Azimuth, degrees from true north
        self.el = self.sat.elev         # Elevation in degrees
        self.ss = self.sat.snr          # Signal to Noise ratio in dBHz
        self.used = self.sat.is_used()  # Used in current solution?

    def get_dict(self):
        return {'PRN': self.prn,
                'az': self.az,
                'el': self.el,
                'ss': self.ss,
                'used': self.used,
                }


class SKY(Gpsd):
    """A SKY object reports a sky view of the GPS satellite positions. If there
    is no GPS device available, or no skyview has been reported yet, only the
    \"class\" field will reliably be present.

    """
    def __init__(self, pvt):
        self.pvt = pvt

    def get_satellites(self):
        records = self.pvt.get_records()
        satelittes = [ SAT(record) for record in records ]
        return satelittes

    def get_dict(self):
        return {'class': 'SKY',
                'satellites': [satellite.get_dict() for satellite in self.get_satellites()],
                }
