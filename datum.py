"""

   Datums and other conversions.
   This is meant to be pretty and understandable rather than fast.

   Geodetic datums are models of the shape of the earth. The earth is
   rather irregular and attempts to simplify it by assuming that it is
   basically an ellipsoid, for example, tend to be reasonably accurate
   only for a local area. This is why so many datums are in use.

   The most common datum for international purposes is WGS84, and the
   parameters of the other ones are usually quoted as differences from
   WGS84.  In this module. a Datum object represents a datum and
   converts lat/lon points in that datum to and from WGS84.
   
   A reference datum consists of a particular shape of ellipsoid and
   an x, y, z offset.  The ellipsoid is defined by its semi-major-axis
   'a' (in this case, the equatorial radius) and its semi-minor-axis
   'b' (the polar radius).  In most cases, rather than using 'b'
   directly, we are interested in the difference between the two - the
   degree to which the earth is considered to be 'flattened' at the
   poles. So the flattening, f, is given by (a-b)/a.

   An example use:

     import datum
     osd = datum.DatumFromName ('Ordnance Survey of Great Britain 36')
     print osd.toWGS84deg(12.3,54.3) 

   (c) 2003 Quentin Stafford-Fraser <www.qandr.org/quentin>
       
   Partly derived from some python code by Joseph Newman
   which in turn came from C code by Alan Jones

"""

import math
import refdatum

# These are for convenience:

def DEG_TO_RAD(angle): return angle*0.0174532925199

def RAD_TO_DEG(angle): return angle/0.0174532925199

# First we define an ellipsoid

class Ellipsoid:
    def __init__(self, a, invf):
        """
        Create an ellipsoid.  Flattenings tend to be incoveniently
        small numbers (typically 0.0033), so they are often quoted
        as their reciprocal.  The invf parameter expected here is 1/f.
        The value es is the first eccentricity squared, which is
        useful later.
        """
        self.a = a
        self.f = 1.0/invf
        self.es = 2 * self.f  -  self.f * self.f


def EllipsoidFromName(name):
    """
    Create a standard ellipsoid from the parameters in
    refdatum.py
    """
    re =  refdatum.Ellipsoids[name]
    return Ellipsoid(re[0], re[1])



class Datum:
    def __init__(self, ellipsoid, dx, dy, dz):
        """
          All parameters give the WGS84 values relative to this datum.
          So dx is the WGS84 X value minus the local datum X value, etc.
          dx, dy, dz are the X,Y,Z offsets.
        """
        global WGS84Datum
        self.dx = dx
        self.dy = dy
        self.dz = dz
        # self.ell = ellipsoid
        self.a = ellipsoid.a
        self.f = ellipsoid.f
        self.wgse = EllipsoidFromName("WGS 84")
        self.da = self.wgse.a - self.a
        self.df = self.wgse.f - self.f

    def fromWGS84rad(self, lat, lon, alt=0.0):
        return self.molodensky(lat, lon, alt,
                               -self.dx, -self.dy, -self.dz,
                               self.wgse.a, self.wgse.f,
                               -self.da, -self.df)

    def fromWGS84deg(self, lat, lon, alt=0.0):
        latrad = DEG_TO_RAD(lat)
        lonrad = DEG_TO_RAD(lon)
        newlat, newlon, newalt = self.fromWGS84rad(latrad, lonrad, alt)
        return (RAD_TO_DEG(newlat), RAD_TO_DEG(newlon), newalt)

    def toWGS84rad(self, lat, lon, alt=0.0):
        return self.molodensky(lat, lon, alt,
                               self.dx, self.dy, self.dz,
                               self.a, self.f,
                               self.da, self.df)

    def toWGS84deg(self, lat, lon, alt=0.0):
        latrad = DEG_TO_RAD(lat)
        lonrad = DEG_TO_RAD(lon)
        newlat, newlon, newalt = self.toWGS84rad(latrad, lonrad, alt)
        return (RAD_TO_DEG(newlat), RAD_TO_DEG(newlon), newalt)

    # everything in radians here
    def molodensky(self, lat, lon,  alt, dx, dy, dz, from_a, from_f, da, df):
        sinlat = math.sin (lat)
        coslat = math.cos (lat)
        sinlon = math.sin (lon)
        coslon = math.cos (lon)
        sin1 = math.sin (math.pi / (3600.0 * 180.0))
        bdiva = 1.0 - from_f
        esq = (2.0 - from_f)*from_f
        exp = 1.0 - esq*sinlat*sinlat
        sqrtexp = math.sqrt (exp)
        rn = from_a / sqrtexp
        rm = from_a * (1.0 - esq) / (exp*sqrtexp)
        dlat = (- dx*sinlat*coslon - dy*sinlat*sinlon + dz*coslat +
                da*(rn*esq*sinlat*coslat)/from_a +
                df*(rm/bdiva + rn*bdiva)*sinlat*coslat) / (rm + alt)
        dlon = (-dx*sinlon +dy*coslon)/((rn+alt)*coslat)
        dh = (dx*coslat*coslon +
              dy*coslat*sinlon +
              dz*sinlat-
              da*from_a/rn +
              df*bdiva*rn*sinlat*sinlat)
        newlat = lat + dlat
        newlon = lon + dlon
        newalt = alt + dh
        return (newlat, newlon, newalt)


# Then we use the ellipsoids to define datums
def DatumFromName(name):
    rd = refdatum.Datums[name]
    e = EllipsoidFromName(rd[0])
    return Datum(e, rd[1], rd[2], rd[3])


# A simple test routine

def test():
     osd = DatumFromName ('Ordnance Survey of Great Britain 36')
     nad = DatumFromName ('North America 1927 mean')
     wlat, wlon, walt    = (12.3, 45.6, 78)
     print "lat, lon, alt =", wlat, wlon, walt
     olat, olon, oalt    = osd.fromWGS84deg(wlat,wlon,walt)
     wlat2, wlon2, walt2 = osd.toWGS84deg(olat, olon, oalt)
     print "Under OSGB datum =", olat, olon, oalt
     print "errors after conversion back = ",
     print wlat2-wlat, wlon2-wlon, walt2-walt

if __name__ == '__main__':
    test()
