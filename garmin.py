#!/usr/bin/env python
"""
   garmin
   
   This module implements the protocol used for communication by the
   Garmin GPS receivers. It is based on the official description
   available from Garmin at
   
   http://www.garmin.com/support/commProtocol.html

   There are lots of variations in the protocols employed by different
   Garmin products. This module tries to cover most of them, which is
   why it looks so big! Only a small subset of the module will be used
   by any particular model. It can easily be extended to cover any
   models not currently included.

   For documentation, see the source.

   (c) 1999 Quentin Stafford-Fraser <quentin@att.com>
   
"""

import os, string, struct, time

debug = 0

# Introduction =====================================================

# There are 3 levels of protocol documented:
#
#       Application  (highest level)
#       Link
#       Physical     (lowest level)
#
# Garmin documents the various versions of these under labels of
# Pxxx, Lxxx, Axxx etc, and this convention is followed here.
# There are also various data types, named Dxxx.

# Roughly speaking, the Physical protocols specify RS232, the Link
# protocols specify a packet structure for sending messages to and
# fro, and the Application protocol specify what can actually go in
# those packets.


# secs from Unix epoch (start of 1970) to Sun Dec 31 00:00:00 1989
TimeEpoch = 631065600   


# Physical protocols ===============================================

# See the Garmin docs for this. At the time of writing, the only
# documented physical layer is P000 which is roughly RS232 at 9600
# baud, 8 data bits, no parity, 1 stop bit. Unlike pure RS232, no
# negative voltages are used, but that is normally not too important.

# In software, we model this as something that has read and write
# methods, which can be used by the higher protocol levels. Later, we
# subclass this as something which handles Unix serial ports.

class P000:
   " Physical layer for communicating with Garmin "
   def read(n):
      pass
   def write(n):
      pass

# Link protocols ===================================================

LinkException = "Link Error"

class L000:
   "Basic Link Protocol"
   Pid_Ack_Byte = 6
   Pid_Nak_Byte = 21
   Pid_Protocol_Array = 253
   Pid_Product_Rqst = 254
   Pid_Product_Data = 255

   # DataLinkEscape etc
   DLE                  = "\x10"
   ETX                  = "\x03"
   EOM                  = DLE+ETX

   def __init__(self, physicalLayer):
      self.phys = physicalLayer

   def sendPacket(self, ptype, data, readAck=1):
      " Send a message. By default this will also wait for the ack."
      if type(data) == type(""):
         ld = chr(len(data))
      else: # XXX assume 16-bit integer for now
         ld = chr(2)
         data = struct.pack("<h",data)
      tp = chr(ptype)
      chk = self.checksum( tp + ld + data)
      escline = self.escape( ld + data + chk)
      bytes = self.DLE + tp + escline + self.EOM 
      self.phys.write(bytes)
      if readAck:
         self.readAcknowledge(ptype)

   def readPacket(self, sendAck=1):
      " Read a message. By default this will also send the ack."
      dle = self.phys.read(1)
      # Find the start of a message
      while dle != self.DLE:
         print "resync - expected DLE and got something else"
         dle = self.phys.read(1)
      # We've now found either the start or the end of a msg
      # Try reading the type.
      tp = self.phys.read(1)
      if tp == self.ETX:
         # It was the end!
         dle = self.phys.read(1)
         tp = self.phys.read(1)
      # Now we should be synchronised
      ptype = ord(tp)
      ld = self.readEscapedByte()
      datalen = ord(ld)
      data = ""
      for i in range(0, datalen):
         data = data + self.readEscapedByte()
      ck = self.readEscapedByte()
      if ck != self.checksum(tp + ld + data):
         raise LinkException, "Invalid checksum"
      eom = self.phys.read(2)
      assert(eom==self.EOM, "Invalid EOM seen")
      if sendAck:
         self.sendAcknowledge(ptype)
      return (ptype, data)

   def expectPacket(self, ptype):
      "Expect and read a particular msg type. Return data."
      tp, data = self.readPacket()
      if tp != ptype:
         raise LinkException, "Expected msg type %d, got %d" % (ptype, tp)
      return data

   def readAcknowledge(self, ptype):
      "Read an ack msg in response to a particular sent msg"
      tp, data = self.readPacket(0)
      if tp != self.Pid_Ack_Byte or ord(data[0]) != ptype:
         raise LinkException, "Acknowledge error"

   def sendAcknowledge(self, ptype):
      self.sendPacket(self.Pid_Ack_Byte, struct.pack("<h", ptype), 0)
      
   def readEscapedByte(self):
      c = self.phys.read(1)
      if c == self.DLE:
         c = self.phys.read(1)
      return c

   def checksum(self, data):
      sum = 0
      for i in data:
         sum = sum + ord(i)
      sum = sum % 256
      return chr((256-sum) % 256)

   def escape(self, data):
      "Escape any DLE characters"
      return string.join(string.split(data, self.DLE), self.DLE+self.DLE)

# L001 builds on L000

class L001(L000):
   "Link protocol 1"
   Pid_Command_Data = 10
   Pid_Xfer_Cmplt = 12
   Pid_Date_Time_Data = 14
   Pid_Position_Data = 17
   Pid_Prx_Wpt_Data = 19
   Pid_Records = 27
   Pid_Rte_Hdr = 29
   Pid_Rte_Wpt_Data = 30
   Pid_Almanac_Data = 31
   Pid_Trk_Data = 34
   Pid_Wpt_Data = 35
   Pid_Pvt_Data = 51

# L002 builds on L000

class L002(L000):
   "Link Protocol 2"
   Pid_Almanac_Data = 4
   Pid_Command_Data = 11
   Pid_Xfer_Cmplt = 12
   Pid_Date_Time_Data = 20
   Pid_Position_Data = 24
   Pid_Records = 35
   Pid_Rte_Hdr = 37
   Pid_Rte_Wpt_Data = 39
   Pid_Wpt_Data = 43


# Application Protocols =======================================

ProtocolException = "Protocol Error"

# A000 and A001 are used to find out what is on the other end of the
# wire, and hence which other protocols we can use.

class A000:
   "Product Data Protocol"

   def __init__(self, linkLayer):
      self.link = linkLayer

   def getProductData(self):
      fmt = "<hh"
      self.link.sendPacket(self.link.Pid_Product_Rqst,"")
      data = self.link.expectPacket(self.link.Pid_Product_Data)
      (prod_id, soft_ver)   = struct.unpack(fmt, data[:4])
      prod_descs = string.split(data[4:-1], "\0")
      return (prod_id, soft_ver/100.0, prod_descs)

class A001:
   "Protocol Capabilities Protocol"
   # Fairly complex, and not yet implemented
   pass
      
# Commands  ---------------------------------------------------

class A010:
   "Device Command Protocol 1"
   Cmnd_Abort_Transfer = 0   # abort current transfer 
   Cmnd_Transfer_Alm = 1     # transfer almanac 
   Cmnd_Transfer_Posn = 2    # transfer position 
   Cmnd_Transfer_Prx = 3     # transfer proximity waypoints 
   Cmnd_Transfer_Rte = 4     # transfer routes 
   Cmnd_Transfer_Time = 5    # transfer time 
   Cmnd_Transfer_Trk = 6     # transfer track log 
   Cmnd_Transfer_Wpt = 7     # transfer waypoints 
   Cmnd_Turn_Off_Pwr = 8     # turn off power 
   Cmnd_Start_Pvt_Data = 49  # start transmitting PVT data 
   Cmnd_Stop_Pvt_Data = 50   # stop transmitting PVT data 

class A011:
   "Device Command Protocol 2"
   Cmnd_Abort_Transfer = 0   # abort current transfer
   Cmnd_Transfer_Alm = 4     # transfer almanac
   Cmnd_Transfer_Rte = 8     # transfer routes
   Cmnd_Transfer_Time = 20   # transfer time
   Cmnd_Transfer_Wpt = 21    # transfer waypoints
   Cmnd_Turn_Off_Pwr = 26    # turn off power

# Transfer Protocols -------------------------------------------

# Most of the following protocols transfer groups of records of a
# particular format. The exact format depends on the product in use.
# Some records may have sub-groups within the transfer (eg. routes)
# each with their own header.

class TransferProtocol:

   def __init__(self, link, cmdproto, datatype, hdrtype=None):
      self.link = link
      self.cmdproto = cmdproto
      self.datatype = datatype
      self.hdrtype = hdrtype

   def getData(self, cmd, data_pid):
      res = []
      self.link.sendPacket(self.link.Pid_Command_Data, cmd)
      data = self.link.expectPacket(self.link.Pid_Records)
      (numrecords,) = struct.unpack("<h", data)
      for i in range(numrecords):
         data = self.link.expectPacket(data_pid)
         p = self.datatype()
         p.unpack(data)
         # print p
         res.append(p)
      data = self.link.expectPacket(self.link.Pid_Xfer_Cmplt)
      return res

   def putData(self, cmd, data_pid, records):
      numrecords = len(records)
      self.link.sendPacket(self.link.Pid_Records, numrecords)
      for i in records:
         self.link.sendPacket(data_pid, i.pack())
      self.link.sendPacket(self.link.Pid_Xfer_Cmplt, cmd)

class A100(TransferProtocol):
   "Waypoint Transfer Protocol"
   def getData(self):
      return TransferProtocol.getData(self,
                               self.cmdproto.Cmnd_Transfer_Wpt,
                               self.link.Pid_Wpt_Data)
   def putData(self,data):
      return TransferProtocol.putData(self,
                               self.cmdproto.Cmnd_Transfer_Wpt,
                               self.link.Pid_Wpt_Data, data)
      

class A200(TransferProtocol):
   "Route Transfer Protocol"

   # Routes are unlike the other transfers, because the batch of
   # records also contains headers indicating the start of a new
   # route.
   
   def getData(self):
      res = []
      self.link.sendPacket(self.link.Pid_Command_Data,
                           self.cmdproto.Cmnd_Transfer_Rte)
      data = self.link.expectPacket(self.link.Pid_Records)
      (numrecords,) = struct.unpack("<h", data)
      routes = []
      route = None
      for i in range(numrecords):
         tp, data = self.link.readPacket()
         if tp == self.link.Pid_Rte_Hdr:
            # save any current route
            if route:
               routes.append(route)
            # and start a new one
            h = self.hdrtype()
            h.unpack(data)
            route = [h]
         elif tp == self.link.Pid_Rte_Wpt_Data:
            # add point to current route
            p = self.datatype()
            p.unpack(data)
            route.append(p)
         else:
            raise ProtocolException, "expected route header or point"
      if route:
         routes.append(route)
      data = self.link.expectPacket(self.link.Pid_Xfer_Cmplt)
      return routes

class A300(TransferProtocol):
   "Track Log Transfer Protocol"
   def getData(self):
      return TransferProtocol.getData(self,
                               self.cmdproto.Cmnd_Transfer_Trk,
                               self.link.Pid_Trk_Data)

class A400(TransferProtocol):
   "Proximity Waypoint Transfer Protocol"
   def getData(self):
      return TransferProtocol.getData(self,
                               self.cmdproto.Cmnd_Transfer_Prx,
                               self.link.Pid_Prx_Wpt_Data)

class A500(TransferProtocol):
   "Almanac Transfer Protocol"
   def getData(self):
      return TransferProtocol.getData(self,
                               self.cmdproto.Cmnd_Transfer_Alm,
                               self.link.Pid_Prx_Alm_Data)

class A600(TransferProtocol):
   "WaypointDate & Time Initialization Protocol"
   def getData(self):
      self.link.sendPacket(self.link.Pid_Command_Data,
                           self.cmdproto.Cmnd_Transfer_Time)
      data = self.link.expectPacket(self.link.Pid_Date_Time_Data)
      d = D600()
      d.unpack(data)
      return d

class A700(TransferProtocol):
   "Position Initialisation Protocol"
   pass

class A800(TransferProtocol):
   "PVT Data Protocol"
   # Live Position, Velocity and Time, similar to that provided by NMEA
   pass


# Most of the following subclasses have a fmt member which is a format
# string as understood by the struct module, detailing how the class
# is transmitted on the wire, and a 'parts' member, listing the
# atrributes that are serialized.

class DataPoint:
   parts = ()
   fmt = ""

   # Generic serialization stuff. If this looks complex, try it in
   # any other language!
   def pack(self):
      arg = (self.fmt,)
      for i in self.parts:
         try:
            # I imagine this is faster, but it only works
            # if attribute 'i' has been assigned to. Otherwise
            # it's only in the class, not in the instance.
            v = self.__dict__[i]
         except KeyError:
            v = eval('self.'+i)
         arg = arg + (v,) 
      return apply(struct.pack, arg)
   
   def unpack(self, bytes):
      # print struct.calcsize(self.fmt), self.fmt
      # print len(bytes), bytes
      bits = struct.unpack(self.fmt, bytes)
      for i in range(len(self.parts)):
         self.__dict__[self.parts[i]] = bits[i]
   

# Waypoints  ---------------------------------------------------

# Different products store different info in their waypoints
# Internally, waypoints store latitude and longitude in 'semicircle'
# coordinates. Here's the conversion:

def degrees(semi):
   return semi * 180.0 / (1L<<31)

def semi(deg):
   return long(deg * ((1L<<31) / 180))

class Waypoint(DataPoint):
   parts = ("ident", "slat", "slon", "unused", "cmnt")
   fmt = "< 6s l l L 40s"

   def __init__(self, ident="", slat=0L, slon=0L, cmnt=""):
      self.ident = ident         # text identidier (upper case)
      self.slat = slat           # lat & long in semicircle terms
      self.slon = slon       
      self.cmnt = cmnt           # comment (must be upper case)
      self.unused = 0L
      
   def __str__(self):
      return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.ident,
                                                 degrees(self.slat),
                                                 degrees(self.slon),
                                                 id(self))
   
class D100(Waypoint):
   pass

class D101(Waypoint):
   parts = Waypoint.parts + ("dst", "smbl")
   fmt = "< 6s l l L 40s f b"
   dst = 0.0                  # proximity distance (m)
   smbl = 0                   # symbol_type id (0-255)

class D102(Waypoint):
   parts = Waypoint.parts + ("dst", "smbl")
   fmt = "< 6s l l L 40s f i"
   dst = 0.0                  # proximity distance (m)
   smbl = 0                   # symbol_type id

class D103(Waypoint):
   parts = Waypoint.parts + ("smbl","dspl")
   fmt = "<6s l l L 40s b b"
   smbl = 0                   # D103 symbol id
   dspl = 0                   # D103 display option
   
class D104(Waypoint):
   parts = Waypoint.parts + ("dst", "smbl", "dspl")
   fmt = "<6s l l L 40s f i b"
   dst = 0.0                  # proximity distance (m)
   smbl = 0                   # symbol_type id
   dspl = 0                   # D104 display option

# XXX TODO: Fill in all of the following!

class D105(Waypoint):
   "Not yet implemented due to laziness of author"
   pass

class D106(Waypoint):
   "Not yet implemented due to laziness of author"
   pass

class D107(Waypoint):
   parts = Waypoint.parts + ("smbl", "dspl", "dst", "color")
   fmt = "<6s l l L 40s b b f b"
   smbl = 0                   # D103 symbol id
   dspl = 0                   # D103 display option
   dst = 0.0
   color = 0
   pass

class D150(Waypoint):
   parts = ("ident", "cc", "clss", "lat", "lon", "alt", "city", "state", "name", "cmnt")
   fmt = "<6s 2s b l l i 24s 2s 30s 40s"
   cc = "  "
   clss = 0
   alt = 0
   city = ""
   state = ""
   name = ""

class D151(Waypoint):
   "Not yet implemented due to laziness of author"
   pass

class D152(Waypoint):
   "Not yet implemented due to laziness of author"
   pass

class D154(Waypoint):
   "Not yet implemented due to laziness of author"
   pass

class D155(Waypoint):
   "Not yet implemented due to laziness of author"
   pass

# Route headers  ---------------------------------------------

class RouteHdr(DataPoint):
   pass

class D200(RouteHdr):
   parts = ("route_num",)
   fmt = "<b"

class D201(RouteHdr):
   parts = ("route_num", "cmnt")
   fmt = "<b 20s"
   cmnt = ""

class D202(RouteHdr):
   parts = ("ident",)
   fmt=""
   # XXX To be done. Tricky, this one. Uses a null-terminated string.

# Track points  ----------------------------------------------

class TrackPoint(DataPoint):
   slat = 0L
   slon = 0L
   time = 0L # secs since midnight 31/12/89?
   def __str__(self):
      return "<Trackpoint (%3.5f, %3.5f) %s (at %x)>" %\
             (degrees(self.slat), degrees(self.slon),
              time.asctime(time.gmtime(TimeEpoch+self.time)), id(self))

class D300(TrackPoint):
   parts = ("slat", "slon", "time", "newtrk")
   fmt = "<l l L B"
   newtrk = 0

# Proximity waypoints  ---------------------------------------

class ProxPoint(DataPoint):
   dst = 0.0

class D400(ProxPoint, D100):
   parts = D100.parts + ("dst",)
   fmt = D100.fmt + "f"
   
class D403(ProxPoint, D103):
   parts = D103.parts + ("dst",)
   fmt = D103.fmt + "f"
   
class D450(ProxPoint, D150):
   parts = ("idx",) + D150.parts + ("dst",)
   fmt = "i" + D150.fmt + "f"
   idx = 0


# Almanacs ---------------------------------------------------

class Almanac(DataPoint):
   pass

class D500(Almanac):
   parts = ("weeknum", "toa", "af0", "af1", "e",
            "sqrta", "m0", "w", "omg0", "odot", "i")
   fmt = "<i f f f f f f f f f f"

class D501(Almanac):
   parts = ("weeknum", "toa", "af0", "af1", "e",
            "sqrta", "m0", "w", "omg0", "odot", "i", "hlth")
   fmt = "<i f f f f f f f f f f b"

class D550(Almanac):
   parts = ("svid", "weeknum", "toa", "af0", "af1", "e",
            "sqrta", "m0", "w", "omg0", "odot", "i")
   fmt = "<c i f f f f f f f f f f"

class D551(Almanac):
   parts = ("svid", "weeknum", "toa", "af0", "af1", "e",
            "sqrta", "m0", "w", "omg0", "odot", "i", "hlth")
   fmt = "<c i f f f f f f f f f f b"

# Date & Time  ---------------------------------------------------

class D600(DataPoint):
   # Not sure what the last four bytes are. Not in docs. 
   parts = ("month", "day", "year", "hour", "min", "sec", "unknown")
   fmt = "<b b H h b b L"
   month = 0         # month (1-12)
   day = 0           # day (1-32)
   year = 0          # year
   hour = 0          # hour (0-23)
   min = 0           # min (0-59)
   sec = 0           # sec (0-59)

# Position   ---------------------------------------------------

class D700(DataPoint):
   parts = ("rlat", "rlon")
   fmt = "<d d"
   rlat = 0.0  # radians
   rlon = 0.0  # radians

# Pvt ---------------------------------------------------------

# Live position info

class D800(DataPoint):
   parts = ("alt", "epe", "eph", "epv", "fix", "tow", "rlat", "rlon,"
            "east", "north", "up", "msl_height", "leap_secs", "wn_days")
   fmt = "<f f f f i d d d f f f f i l"
   pass

# Garmin models ==============================================

# For reference, here are some of the product ID numbers used by
# different Garmin models. Notice that this is not a one-to-one
# mapping in either direction!

ModelIDs = (
   (52, "GNC 250"),
   (64, "GNC 250 XL"),
   (33, "GNC 300"),
   (98, "GNC 300 XL"),
   (77, "GPS 12"),
   (87, "GPS 12"),
   (96, "GPS 12"),
   (77, "GPS 12 XL"),
   (96, "GPS 12 XL"),
   (106, "GPS 12 XL Chinese"),
   (105, "GPS 12 XL Japanese"),
   (47, "GPS 120"),
   (55, "GPS 120 Chinese"),
   (74, "GPS 120 XL"),
   (61, "GPS 125 Sounder"),
   (95, "GPS 126"),
   (100, "GPS 126 Chinese"),
   (95, "GPS 128"),
   (100, "GPS 128 Chinese"),
   (20, "GPS 150"),
   (64, "GPS 150 XL"),
   (34, "GPS 155"),
   (98, "GPS 155 XL"),
   (34, "GPS 165"),
   (41, "GPS 38"),
   (56, "GPS 38 Chinese"),
   (62, "GPS 38 Japanese"),
   (31, "GPS 40"),
   (41, "GPS 40"),
   (56, "GPS 40 Chinese"),
   (62, "GPS 40 Japanese"),
   (31, "GPS 45"),
   (41, "GPS 45"),
   (56, "GPS 45 Chinese"),
   (41, "GPS 45 XL"),
   (96, "GPS 48"),
   (14, "GPS 55"),
   (15, "GPS 55 AVD"),
   (18, "GPS 65"),
   (13, "GPS 75"),
   (23, "GPS 75"),
   (42, "GPS 75"),
   (39, "GPS 89"),
   (45, "GPS 90"),
   (24, "GPS 95"),
   (35, "GPS 95"),
   (22, "GPS 95 AVD"),
   (36, "GPS 95 AVD"),
   (36, "GPS 95 XL"),
   (59, "GPS II"),
   (73, "GPS II Plus"),
   (97, "GPS II Plus"),
   (72, "GPS III"),
   (71, "GPS III Pilot"),
   (50, "GPSCOM 170"),
   (53, "GPSCOM 190"),
   (49, "GPSMAP 130"),
   (76, "GPSMAP 130 Chinese"),
   (49, "GPSMAP 135 Sounder"),
   (49, "GPSMAP 175"),
   (48, "GPSMAP 195"),
   (29, "GPSMAP 205"),
   (44, "GPSMAP 205"),
   (29, "GPSMAP 210"),
   (29, "GPSMAP 220"),
   (49, "GPSMAP 230"),
   (76, "GPSMAP 230 Chinese"),
   (49, "GPSMAP 235 Sounder")
)

# Make sure you've got a really wide window to view this one!
# This describes the protocol capabilities of products that do not
# support the Protocol Capabilities Protocol (most of them).  Some
# models differ in capabilities depending on the software version
# installed. So for each ID there is a tuple of entries. Each entry
# begins with either None, if it applies to all versions with that ID,
# or (minv, maxv), meaning that it applies if the software version
# >= minv and < maxv.

# All models implement A000, A600 and A700

MaxVer = 999.99

ModelProtocols = {
# ID    minver maxver    Link  Cmnd   Wpt,          Rte,                Trk,          Prx,          Alm
13:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
14:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
15:  ( (None,            L001, A010, (A100, D151), (A200, D200, D151), (A300, D300), (A400, D151), (A500, D500) ), ),
18:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
20:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D550) ), ),
22:  ( (None,            L001, A010, (A100, D152), (A200, D201, D152), (A300, D300), (A400, D152), (A500, D500) ), ),
23:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
24:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
29:  ( ((0.00, 4.00),    L001, A010, (A100, D101), (A200, D201, D101), (A300, D300), (A400, D101), (A500, D500) ),
       ((4.00, MaxVer),  L001, A010, (A100, D102), (A200, D201, D102), (A300, D300), (A400, D102), (A500, D500) ), ),
31:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
33:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D550) ), ),
34:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D550) ), ),
35:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
36:  ( ((0.00, 3.00),    L001, A010, (A100, D152), (A200, D201, D152), (A300, D300), (A400, D152), (A500, D500) ),
       ((3.00, MaxVer),  L001, A010, (A100, D152), (A200, D201, D152), (A300, D300), None,         (A500, D500) ), ),
39:  ( (None,            L001, A010, (A100, D151), (A200, D201, D151), (A300, D300), None,         (A500, D500) ), ),
41:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
42:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
44:  ( (None,            L001, A010, (A100, D101), (A200, D201, D101), (A300, D300), (A400, D101), (A500, D500) ), ),
45:  ( (None,            L001, A010, (A100, D152), (A200, D201, D152), (A300, D300), None,         (A500, D500) ), ),
47:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
48:  ( (None,            L001, A010, (A100, D154), (A200, D201, D154), (A300, D300), None,         (A500, D501) ), ),
49:  ( (None,            L001, A010, (A100, D102), (A200, D201, D102), (A300, D300), (A400, D102), (A500, D501) ), ),
50:  ( (None,            L001, A010, (A100, D152), (A200, D201, D152), (A300, D300), None,         (A500, D501) ), ),
52:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D550) ), ),
53:  ( (None,            L001, A010, (A100, D152), (A200, D201, D152), (A300, D300), None,         (A500, D501) ), ),
55:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
56:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
59:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
61:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
62:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
64:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D551) ), ),
71:  ( (None,            L001, A010, (A100, D155), (A200, D201, D155), (A300, D300), None,         (A500, D501) ), ),
72:  ( (None,            L001, A010, (A100, D104), (A200, D201, D104), (A300, D300), None,         (A500, D501) ), ),
73:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), None,         (A500, D501) ), ),
74:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
76:  ( (None,            L001, A010, (A100, D102), (A200, D201, D102), (A300, D300), (A400, D102), (A500, D501) ), ),
77:  ( ((0.00, 3.01),    L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), (A400, D400), (A500, D501) ),
       ((3.01, 3.50),    L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ),
       ((3.50, 3.61),    L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), None,         (A500, D501) ),
       ((3.61, MaxVer),  L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
87:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
95:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
96:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
97:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), None,         (A500, D501) ), ),
98:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D551) ), ),
100: ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
105: ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
106: ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), )
}

def GetProtocols(prod_id, soft_ver):
   bits = ModelProtocols[prod_id]
   for i in bits:
      vrange = i[0]
      if ( (vrange == None) or
           ((soft_ver >= vrange[0]) and (soft_ver < vrange[1]))):
         return i
   raise "No protocols known for this software version. Strange!"
   
# ====================================================================

# Now some practical implementations

class SerialLink(P000):

   def __init__(self, device):
      self.device = device
      self.fd = open(self.device,"w+", 0)

   def read(self, n):
      return self.fd.read(n)
   
   def write(self, data):
      self.fd.write(data)

   def __del__(self):
      self.fd.close()

         
class UnixSerialLink(SerialLink):

   def __init__(self, device):
      # The appropriate value here depends on the output from your stty
      # 
      STTY_MODE = "0:4:cbd:8a30:3:1c:7f:15:4:0:1:0:11:13:1a" +\
                  ":0:12:f:17:16:0:0:73:0:0:0:0:0:0:0:0:0:0:0:0:0"
      # Equivalent to raw -echo
      dummy = os.popen("/bin/stty %s < %s" % (STTY_MODE, device)
                       ).read()
      SerialLink.__init__(self, device)

class Garmin:
   def __init__(self, physicalLayer):
      self.link = L000(physicalLayer)      # at least initially
      print "Requesting product data"
      (prod_id, soft_ver, prod_descs) = A000(self.link).getProductData()
      print "GPS Product ID: %d Descriptions: %s Software version: %2.2f" % \
            (prod_id, prod_descs, soft_ver)
      try:
         protos = GetProtocols(prod_id, soft_ver)
      except KeyError:
         print "Sorry, this model is not yet known by the garmin package"
         print "Tell Quentin to implement the Protocol Capability Protocol!"
      (versions, self.linkProto, self.cmdProto, self.wptProtos, self.rteProtos,
       self.trkProtos, self.prxProtos, self.almProtos) = protos

      self.link = self.linkProto(physicalLayer)
      # What kind of waypoints will we get?
      self.wptType = self.wptProtos[1]
      # How will we get them?
      self.wptLink = self.wptProtos[0](self.link, self.cmdProto, self.wptType)

      # What kind of routes will we get?
      self.rteHdr  = self.rteProtos[1]
      self.rteType = self.rteProtos[2]
      # How will we get them?
      self.rteLink = self.rteProtos[0](self.link, self.cmdProto,
                                       self.rteType, self.rteHdr)

      if self.trkProtos != None:
         # What kind of track points will we get?
         self.trkType = self.trkProtos[1]
         # How will we get them?
         self.trkLink = self.trkProtos[0](self.link, self.cmdProto, self.trkType)

      if self.prxProtos != None:   
         # What kind of proximity waypoints will we get?
         self.prxType = self.prxProtos[1]
         # How will we get them?
         self.prxLink = self.prxProtos[0](self.link, self.cmdProto, self.prxType)

      if self.almProtos != None:         
         # What kind of almanacs will we get?
         self.almType = self.almProtos[1]
         # How will we get them?
         self.almLink = self.almProtos[0](self.link, self.cmdProto, self.almType)

      self.timeLink = A600(self.link, self.cmdProto, D600)
      
   def getWaypoints(self):
      return self.wptLink.getData()

   def putWaypoints(self, data):
      return self.wptLink.putData(data)

   def getRoutes(self):
      return self.rteLink.getData()

   def getTrack(self):
      return self.trkLink.getData()

   def getProxPoints(self):
      return self.prxLink.getData()

   def getAlmanac(self):
      return self.almLink.getData()

   def getTime(self):
      return self.timeLink.getData()

# =================================================================

def main():
   serialDevice =  "/dev/ttyS0"
   phys = UnixSerialLink(serialDevice)
   gps = Garmin(phys)

   if 0:
      # show waypoints
      wpts = gps.getWaypoints()
      for w in wpts:
         print w

   if 0:
      # show routes
      routes = gps.getRoutes()
      for r in routes:
         print r[0].route_num
         for p in r[1:]:
            print p
         
   if 0:
      # show proximity points
      print gps.getProxPoints()

   if 1:
      # show track
      pts = gps.getTrack()
      for p in pts:
         print p

   if 0:
      # show almanac
      print gps.getAlmanac()

   if 0:
      # show time
      d = gps.getTime()
      print d.year, d.month, d.day, d.hour, d.min, d.sec, d.unknown

   if 0:
      # upload a waypoint
      w = gps.wptType(
         ident="01TEST",
         cmnt="A TEST POINT",
         slat=624447295,
         slon=-2529985
         )
      gps.putWaypoints([w])
      
if __name__ == "__main__":
   main()
