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

   For documentation, see the source, and the included index.html file.

   This is released under the Gnu General Public Licence. A copy of
   this can be found at http://www.opensource.org/licenses/gpl-license.html

   For the latest information about PyGarmin, please see
   http://pygarmin.sourceforge.net/

   (c) 2003 Quentin Stafford-Fraser <www.qandr.org/quentin>
   (c) 2000 James A. H. Skillen <jahs@jahs.net>
   (c) 2001 Raymond Penners <raymond@dotsphinx.com>
   (c) 2001 Tom Grydeland <Tom.Grydeland@phys.uit.no>

"""

import os, select, string, sys, time
import newstruct as struct

# Set this value to > 0 for some debugging output, and the higher
# the number, the more you'll get.

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
   def read(self, n):
      pass
   def write(self, n):
      pass

# The following is handy for debugging:

def hexdump(data): return string.join(map(lambda x: "%02x" % ord(x), data))

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
      if debug > 5: print "< packet %3d : " % ptype, hexdump(data)
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
      if debug > 5: print "> packet %3d : " % ptype, hexdump(data)
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
      if debug > 5: print "(>ack)",
      tp, data = self.readPacket(0)
      if (tp & 0xff) != self.Pid_Ack_Byte or ord(data[0]) != ptype:
         raise LinkException, "Acknowledge error"

   def sendAcknowledge(self, ptype):
      if debug > 5: print "(<ack)",
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
   Pid_Rte_Link_Data = 98
   Pid_Trk_Hdr = 99

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

   def __init__(self, linkLayer):
      self.link=linkLayer

   def getProtocols(self):
      # may raise LinkException here
      if debug > 3: print "Try reading protocols using PCP"
      data = self.link.expectPacket(self.link.Pid_Protocol_Array)
      num = len(data)/3
      fmt = "<"+num*"ch"
      tup = struct.unpack(fmt, data)
      protocols = []
      for i in range(0, 2*num, 2):
         protocols.append(tup[i]+"%03d"%tup[i+1])
      if debug > 0:
         print "Protocols reported by A001:", protocols
      return protocols

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

   def __init__(self, link, cmdproto, datatypes):
      self.link = link
      self.cmdproto = cmdproto
      self.datatypes = datatypes

   def getData(self, cmd, *pids):
      pass

   def putData(self, cmd, data_pid, records):
      numrecords = len(records)
      if debug > 3: print self.__doc__, "Sending %d records" % numrecords
      self.link.sendPacket(self.link.Pid_Records, numrecords)
      for i in records:
         self.link.sendPacket(data_pid, i.pack())
      self.link.sendPacket(self.link.Pid_Xfer_Cmplt, cmd)

class SingleTransferProtocol(TransferProtocol):

   def getData(self, callback, cmd, pid):
      self.link.sendPacket(self.link.Pid_Command_Data, cmd)
      data = self.link.expectPacket(self.link.Pid_Records)
      (numrecords,) = struct.unpack("<h", data)
      if debug > 3: print self.__doc__, "Expecting %d records" % numrecords
      result = []
      for i in range(numrecords):
         data = self.link.expectPacket(pid)
         p = self.datatypes[0]()
         p.unpack(data)
         result.append(p)
         if callback:
            try:
               callback(p)
            except:
               pass
      self.link.expectPacket(self.link.Pid_Xfer_Cmplt)
      return result

class MultiTransferProtocol(TransferProtocol):

   def getData(self, callback, cmd, hdr_pid, *data_pids):
      self.link.sendPacket(self.link.Pid_Command_Data, cmd)
      data = self.link.expectPacket(self.link.Pid_Records)
      (numrecords,) = struct.unpack("<h", data)
      if debug > 3: print self.__doc__, "Expecting %d records" % numrecords
      data_pids = list(data_pids)
      result = []
      last = []
      for i in range(numrecords):
         tp, data = self.link.readPacket()
         if tp == hdr_pid:
            if last:
               result.append(last)
               last = []
            index = 0
         else:
            try:
               index = data_pids.index(tp) + 1
            except ValueError:
               raise ProtocolException, "Expected header or point"
         p = self.datatypes[index]()
         p.unpack(data)
         last.append(p)
         if callback:
            try:
               callback(p)
            except:
               pass

      self.link.expectPacket(self.link.Pid_Xfer_Cmplt)
      if last:
         result.append(last)
      return result

class A100(SingleTransferProtocol):
   "Waypoint Transfer Protocol"
   def getData(self, callback = None):
      return SingleTransferProtocol.getData(self, callback,
                                            self.cmdproto.Cmnd_Transfer_Wpt,
                                            self.link.Pid_Wpt_Data)
   def putData(self,data):
      return SingleTransferProtocol.putData(self,
                                            self.cmdproto.Cmnd_Transfer_Wpt,
                                            self.link.Pid_Wpt_Data,
                                            data)


class A200(MultiTransferProtocol):
   "Route Transfer Protocol"
   def getData(self, callback = None):
      return MultiTransferProtocol.getData(self, callback,
                                           self.cmdproto.Cmnd_Transfer_Rte,
                                           self.link.Pid_Rte_Hdr,
                                           self.link.Pid_Rte_Wpt_Data)

class A201(MultiTransferProtocol):
   "Route Transfer Protocol"
   def getData(self, callback = None):
      return MultiTransferProtocol.getData(self, callback,
                                           self.cmdproto.Cmnd_Transfer_Rte,
                                           self.link.Pid_Rte_Hdr,
                                           self.link.Pid_Rte_Wpt_Data,
                                           self.link.Pid_Rte_Link_Data)

class A300(SingleTransferProtocol):
   "Track Log Transfer Protocol"
   def getData(self, callback = None):
      return SingleTransferProtocol.getData(self, callback,
                                            self.cmdproto.Cmnd_Transfer_Trk,
                                            self.link.Pid_Trk_Data)

class A301(MultiTransferProtocol):
   "Track Log Transfer Protocol"
   def getData(self, callback = None):
      return MultiTransferProtocol.getData(self, callback,
                                           self.cmdproto.Cmnd_Transfer_Trk,
                                           self.link.Pid_Trk_Hdr,
                                           self.link.Pid_Trk_Data)

class A400(SingleTransferProtocol):
   "Proximity Waypoint Transfer Protocol"
   def getData(self, callback = None):
      return SingleTransferProtocol.getData(self, callback,
                                            self.cmdproto.Cmnd_Transfer_Prx,
                                            self.link.Pid_Prx_Wpt_Data)

class A500(SingleTransferProtocol):
   "Almanac Transfer Protocol"
   def getData(self, callback):
      return SingleTransferProtocol.getData(self, callback,
                                            self.cmdproto.Cmnd_Transfer_Alm,
                                            self.link.Pid_Prx_Alm_Data)

class A600(TransferProtocol):
   "Waypoint Date & Time Initialization Protocol"
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
   def dataOn(self):
      self.link.sendPacket(self.link.Pid_Command_Data,
                           self.cmdproto.Cmnd_Start_Pvt_Data)

   def dataOff(self):
      self.link.sendPacket(self.link.Pid_Command_Data,
                           self.cmdproto.Cmnd_Stop_Pvt_Data)

   def getData(self):
      data = self.link.expectPacket(self.link.Pid_Pvt_Data)
      d = D800()
      d.unpack(data)
      return d

class A900(TransferProtocol):
   "Used by GPS III+, no documentation as of 2000-09-18"
   pass

class A902(TransferProtocol):
   "Used by etrex, no documentation as of 2001-05-30"
   pass

class A903(TransferProtocol):
   "Used by etrex, no documentation as of 2001-05-30"
   pass

class A904(TransferProtocol):
   "Used by GPS V"
   pass

class A906(TransferProtocol):
   "Mentioned in 'Garmin GPS Interface Specification', 2004-02-24"
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
      # print len(bytes), repr(bytes)
      try:
         bits = struct.unpack(self.fmt, bytes)
         for i in range(len(self.parts)):
            self.__dict__[self.parts[i]] = bits[i]
      except Exception, e:
         print e
         print "Format: <" + self.fmt   + ">"
         print "Parts:  <" + string.join(self.parts, ", ") + ">"
         print "Input:  <" + string.join(bytes, "><") + ">"
	 raise Exception, e

# Waypoints  ---------------------------------------------------

# Different products store different info in their waypoints
# Internally, waypoints store latitude and longitude in 'semicircle'
# coordinates. Here's the conversion:

def degrees(semi):
   return semi * 180.0 / (1L<<31)

def semi(deg):
   return long(deg * ((1L<<31) / 180))

def radian(semi):
   return semi * math.pi / (1L<<31)

# Distance between two waypoints (in metres)
# Haversine Formula (from R.W. Sinnott, "Virtues of the Haversine",
# Sky and Telescope, vol. 68, no. 2, 1984, p. 159):
def distance(wp1, wp2):
   R = 63670000
   rlat1 = radian(wp1.slat)
   rlon1 = radian(wp1.slon)
   rlat2 = radian(wp2.slat)
   rlon2 = radian(wp2.slon)
   dlon = rlon2 - lon1
   dlat = rlat2 - lon1
   a =  math.pow(math.sin(dlat/2),2) + math.cos(rlat1)*math.cos(rlat2)*math.pow(sin(dlon/2),2)
   c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
   return R*c

class Waypoint(DataPoint):
   parts = ("ident", "slat", "slon", "unused", "cmnt")
   fmt = "< 6s l l L 40s"

   def __init__(self, ident="", slat=0L, slon=0L, cmnt=""):
      self.ident = ident         # text identidier (upper case)
      self.slat = slat           # lat & long in semicircle terms
      self.slon = slon
      self.cmnt = cmnt           # comment (must be upper case)
      self.unused = 0L

   def __repr__(self):
      return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.ident,
                                                       degrees(self.slat),
                                                       degrees(self.slon),
                                                       id(self))

   def __str__(self):
      return "%s (%3.5f, %3.5f)" % (self.ident,
                                    degrees(self.slat),
                                    degrees(self.slon))

   def getDict(self):
      self.data = {'name': self.ident,
                'comment': self.cmnt,
                'latitude': self.slat,
                'longitude': self.slon
                }
      return self.data


class D100(Waypoint):
   pass

class D101(Waypoint):
   parts = Waypoint.parts + ("dst", "smbl")
   fmt = "< 6s l l L 40s f b"
   dst = 0.0                  # proximity distance (m)
   smbl = 0                   # symbol_type id (0-255)

   def __init__(self, ident="", slat=0L, slon=0L, cmnt="", dst=0L, smbl=0L):
      self.ident = ident         # text identidier (upper case)
      self.slat = slat           # lat & long in semicircle terms
      self.slon = slon
      self.cmnt = cmnt           # comment (must be upper case)
      self.unused = 0L
      self.dst = dst
      self.smbl = smbl
      self.data = {}

   def __repr__(self):
      return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.ident,
                                                       degrees(self.slat),
                                                       degrees(self.slon),
                                                       id(self))

   def __str__(self):
      return "%s (%3.5f, %3.5f)" % (self.ident,
                                    degrees(self.slat),
                                    degrees(self.slon))

   def getDict(self):
      self.data = {'name': self.ident,
                   'comment': string.strip(self.cmnt),
                   'latitude': self.slat,
                   'longitude': self.slon,
                   'distance': self.dst,
                   'symbol': self.smbl,
                   }
      return self.data

class D102(Waypoint):
   parts = Waypoint.parts + ("dst", "smbl")
   fmt = "< 6s l l L 40s f h"
   dst = 0.0                  # proximity distance (m)
   smbl = 0                   # symbol_type id

   def __init__(self, ident="", slat=0L, slon=0L, cmnt="", dst=0L, smbl=0L):
      self.ident = ident         # text identidier (upper case)
      self.slat = slat           # lat & long in semicircle terms
      self.slon = slon
      self.cmnt = cmnt           # comment (must be upper case)
      self.unused = 0L
      self.dst = dst
      self.smbl = smbl
      self.data = {}

   def __repr__(self):
      return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.ident,
                                                       degrees(self.slat),
                                                       degrees(self.slon),
                                                       id(self))

   def __str__(self):
      return "%s (%3.5f, %3.5f)" % (self.ident,
                                    degrees(self.slat),
                                    degrees(self.slon))

   def getDict(self):
      self.data = {'name': self.ident,
                   'comment': string.strip(self.cmnt),
                   'latitude': self.slat,
                   'longitude': self.slon,
                   'distance': self.dst,
                   'symbol': self.smbl
                   }
      return self.data

class D103(Waypoint):
   parts = Waypoint.parts + ("smbl","dspl")
   fmt = "<6s l l L 40s b b"
   smbl = 0                   # D103 symbol id
   dspl = 0                   # D103 display option

   def __init__(self, ident="", slat=0L, slon=0L, cmnt="", dspl=0L, smbl=0L):
      self.ident = ident         # text identidier (upper case)
      self.slat = slat           # lat & long in semicircle terms
      self.slon = slon
      self.cmnt = cmnt           # comment (must be upper case)
      self.unused = 0L
      self.dspl = dspl
      self.smbl = smbl
      self.data = {}

   def __repr__(self):
      return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.ident,
                                                       degrees(self.slat),
                                                       degrees(self.slon),
                                                       id(self))

   def __str__(self):
      return "%s (%3.5f, %3.5f)" % (self.ident,
                                    degrees(self.slat),
                                    degrees(self.slon))

   def getDict(self):
      self.data = {'name': self.ident,
                   'comment': string.strip(self.cmnt),
                   'latitude': self.slat,
                   'longitude': self.slon,
                   'display': self.dspl,
                   'symbol': self.smbl
                   }
      return self.data

class D104(Waypoint):
   parts = Waypoint.parts + ("dst", "smbl", "dspl")
   fmt = "<6s l l L 40s f h b"
   dst = 0.0                  # proximity distance (m)
   smbl = 0                   # symbol_type id
   dspl = 0                   # D104 display option

   def __init__(self, ident="", slat=0L, slon=0L, cmnt="",
                dst=0L, smbl=0L, dspl=0L):
      self.ident = ident         # text identidier (upper case)
      self.slat = slat           # lat & long in semicircle terms
      self.slon = slon
      self.cmnt = cmnt           # comment (must be upper case)
      self.unused = 0L
      self.dst = dst             # proximity distance (m)
      self.smbl = smbl           # symbol_type id
      self.dspl = dspl           # D104 display option

   def __repr__(self):
      return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.ident,
                                                       degrees(self.slat),
                                                       degrees(self.slon),
                                                       id(self))

   def __str__(self):
      return "%s (%3.5f, %3.5f)" % (self.ident,
                                    degrees(self.slat),
                                    degrees(self.slon))

   def getDict(self):
      self.data = {'name': self.ident,
                   'comment': string.strip(self.cmnt),
                   'latitude': self.slat,
                   'longitude': self.slon,
                   'distance': self.dst,
                   'symbol': self.smbl,
                   'display': self.dspl
                   }
      return self.data

class D105(Waypoint):
   parts = ("slat", "slon", "smbl", "ident")
   fmt = "<l l h s"
   smbl = 0

   def __init__(self, ident="", slat=0L, slon=0L, smbl=0L):
      self.ident = ident         # text identidier (upper case)
      self.slat = slat           # lat & long in semicircle terms
      self.slon = slon
      self.unused = 0L
      self.smbl = smbl

   def __repr__(self):
      return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.ident,
                                                       degrees(self.slat),
                                                       degrees(self.slon),
                                                       id(self))

   def __str__(self):
      return "%s (%3.5f, %3.5f)" % (self.ident,
                                    degrees(self.slat),
                                    degrees(self.slon))

   def getDict(self):
      self.data = {'name': self.ident,
                   'latitude': self.slat,
                   'longitude': self.slon,
                   'symbol': self.smbl
                   }
      return self.data

class D106(Waypoint):
   parts = ("wpt_class", "subclass", "slat", "slon", "smbl", "ident", "lnk_ident")
   fmt = "<b 13s l l h s s"
   wpt_class = 0
   subclass = ""
   smbl = 0
   lnk_ident = ""

   def __init__(self, ident="", slat=0L, slon=0L, subclass="",
                wpt_class=0L, lnk_ident="", smbl=0L):
      self.ident = ident         # text identidier (upper case)
      self.slat = slat           # lat & long in semicircle terms
      self.slon = slon
      self.wpt_class = wpt_class
      self.unused = 0L
      self.subclass = subclass
      self.lnk_ident = lnk_ident
      self.smbl = smbl

   def __repr__(self):
      return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.ident,
                                                       degrees(self.slat),
                                                       degrees(self.slon),
                                                       id(self))

   def __str__(self):
      return "%s (%3.5f, %3.5f)" % (self.ident,
                                    degrees(self.slat),
                                    degrees(self.slon))

   def getDict(self):
      self.data = {'name': self.ident,
                   'class': self.wpt_class,
                   'subclass': self.subclass,
                   'latitude': self.slat,
                   'longitude': self.slon,
                   'link': self.lnk_ident,
                   'symbol': self.smbl
                   }
      return self.data

class D107(Waypoint):
   parts = Waypoint.parts + ("smbl", "dspl", "dst", "color")
   fmt = "<6s l l L 40s b b f b"
   smbl = 0                   # D103 symbol id
   dspl = 0                   # D103 display option
   dst = 0.0
   color = 0

   def __init__(self, ident="", slat=0L, slon=0L, cmnt="",
                dst=0L, smbl=0L, dspl=0L, color=0L):
      self.ident = ident         # text identidier (upper case)
      self.slat = slat           # lat & long in semicircle terms
      self.slon = slon
      self.cmnt = cmnt           # comment (must be upper case)
      self.unused = 0L
      self.dst = dst             # proximity distance (m)
      self.smbl = smbl           # symbol_type id
      self.dspl = dspl           # D107 display option
      self.color = color

   def __repr__(self):
      return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.ident,
                                                       degrees(self.slat),
                                                       degrees(self.slon),
                                                       id(self))

   def __str__(self):
      return "%s (%3.5f, %3.5f)" % (self.ident,
                                    degrees(self.slat),
                                    degrees(self.slon))

   def getDict(self):
      self.data = {'name': self.ident,
                   'comment': string.strip(self.cmnt),
                   'latitude': self.slat,
                   'longitude': self.slon,
                   'distance': self.dst,
                   'symbol': self.smbl,
                   'display': self.dspl,
                   'color': self.color
                   }
      return self.data

class D108(Waypoint):
   parts = ("wpt_class", "color", "dspl", "attr", "smbl",
            "subclass", "slat", "slon", "alt", "dpth", "dist",
            "state", "cc", "ident", "cmnt", "facility", "city",
            "addr", "cross_road")
   fmt = "<b b b b h 18s l l f f f 2s 2s s s s s s s"
   wpt_class = 0
   color = 0
   dspl = 0
   attr = 0x60
   smbl = 0
   subclass = ""
   alt = 1.0e25
   dpth = 1.0e25
   dist = 0.0
   state = ""
   cc = ""
   facility = ""
   city = ""
   addr = ""
   cross_road = ""

   def __init__(self, ident="", slat=0L, slon=0L, alt=1.0e25, dpth=1.0e25,
                cmnt="", subclass="", wpt_class=0L, lnk_ident="", smbl=18L):
      self.ident = ident         # text identifier (upper case)
      self.slat = slat           # lat & long in semicircle terms
      self.slon = slon
      self.wpt_class = wpt_class
      self.unused = 0L
      self.subclass = subclass
      self.lnk_ident = lnk_ident
      self.smbl = smbl
      self.cmnt = cmnt

   def __repr__(self):
      return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.ident,
                                                       degrees(self.slat),
                                                       degrees(self.slon),
                                                       id(self))

   def __str__(self):
      return "%s (%3.5f, %3.5f, %3f) '%s' class %d symbl %d" % (
         self.ident,
         degrees(self.slat), degrees(self.slon),
         self.alt, string.strip(self.cmnt),
         self.wpt_class, self.smbl)

class D109(Waypoint):
   parts = ("dtyp", "wpt_class", "dspl_color", "attr", "smbl",
            "subclass", "slat", "slon", "alt", "dpth", "dist",
            "state", "cc", "ete", "ident", "cmnt", "facility", "city",
            "addr", "cross_road")
   fmt = "<b b b b h 18s l l f f f 2s 2s l s s s s s s"
   dtyp = 0x01
   wpt_class = 0
   dspl_color = 0
   attr = 0x70
   smbl = 0
   subclass = ""
   alt = 1.0e25
   dpth = 1.0e25
   dist = 0.0
   state = ""
   cc = ""
   ete = -1   # Estimated time en route in seconds to next waypoint
   facility = ""
   city = ""
   addr = ""
   cross_road = ""

   def __init__(self, ident="", slat=0L, slon=0L, alt=1.0e25, dpth=1.0e25,
                cmnt="", subclass="", wpt_class=0L, lnk_ident="", smbl=18L):
      self.ident = ident
      self.slat = slat
      self.slon = slon
      self.wpt_class = wpt_class
      self.unused = 0L
      self.subclass = subclass
      self.lnk_ident = lnk_ident
      self.smbl = smbl
      self.cmnt = cmnt

   def __repr__(self):
      return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.ident,
                                                       degrees(self.slat),
                                                       degrees(self.slon),
                                                       id(self))

   def __str__(self):
      return "%s (%3.5f, %3.5f, %3f) '%s' class %d symbl %d" % (
         self.ident,
         degrees(self.slat), degrees(self.slon),
         self.alt, string.strip(self.cmnt),
         self.wpt_class, self.smbl)

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
   parts = Waypoint.parts + ("dst", "name", "city", "state",
                             "alt", "cc", "unused2", "wpt_class")
   fmt = "< 6s l l L 40s f 30s 24s 2s i 2s c b"
   dst = 0.0
   name = ""
   city = ""
   state = ""
   alt = 0
   cc = ""
   unused2 = ""
   wpt_cass = 0

class D152(Waypoint):
   parts = Waypoint.parts + ("dst", "name", "city", "state",
                             "alt", "cc", "unused2", "wpt_class")
   fmt = "< 6s l l L 40s f 30s 24s 2s i 2s c b"
   dst = 0.0
   name = ""
   city = ""
   state = ""
   alt = 0
   cc = ""
   unused2 = ""
   wpt_cass = 0

class D154(Waypoint):
   parts = Waypoint.parts + ("dst", "name", "city", "state", "alt",
                             "cc", "unused2", "wpt_class", "smbl")
   fmt = "< 6s l l L 40s f 30s 24s 2s i 2s c b i"
   dst = 0.0
   name = ""
   city = ""
   state = ""
   alt = 0
   cc = ""
   unused2 = ""
   wpt_cass = 0
   smbl = 0

class D155(Waypoint):
   parts = Waypoint.parts + ("dst", "name", "city", "state", "alt",
                             "cc", "unused2", "wpt_class", "smbl", "dspl")
   fmt = "< 6s l l L 40s f 30s 24s 2s i 2s c b i b"
   dst = 0.0
   name = ""
   city = ""
   state = ""
   alt = 0
   cc = ""
   unused2 = ""
   wpt_cass = 0
   smbl = 0
   dspl = 0

# Route headers  ---------------------------------------------

class RouteHdr(DataPoint):

   def __repr__(self):
      return "<RouteHdr (at %s)>" % id(self)

class D200(RouteHdr):
   parts = ("route_num",)
   fmt = "<b"

class D201(RouteHdr):
   parts = ("route_num", "cmnt")
   fmt = "<b 20s"
   cmnt = ""

class D202(RouteHdr):
   parts = ("ident",)
   fmt="<s"

# Route links  -----------------------------------------------

class RouteLink(DataPoint):

   def __repr__(self):
      return "<RouteLink (at %s)" % id(self)

class D210(RouteLink):
   parts = ("clazz", "subclass", "ident")
   fmt = "<h 18s s"

# Track points  ----------------------------------------------

class TrackPoint(DataPoint):
   slat = 0L
   slon = 0L
   time = 0L # secs since midnight 31/12/89?

   def __repr__(self):
      return "<Trackpoint (%3.5f, %3.5f) %s (at %x)>" %\
             (degrees(self.slat), degrees(self.slon),
              time.asctime(time.gmtime(TimeEpoch+self.time)), id(self))

class D300(TrackPoint):
   parts = ("slat", "slon", "time", "newtrk")
   fmt = "<l l L B"
   newtrk = 0

class D301(TrackPoint):
   parts = ("slat", "slon", "time", "alt", "depth", "new_trk")
   fmt = "<l l L f f b"
   alt = 0.0
   depth = 0.0
   new_trk = 0

# Track headers ----------------------------------------------

class TrackHdr(DataPoint):
   trk_ident = ""

   def __repr__(self):
      return "<TrackHdr %s (at %x)>" % (self.trk_ident,
                                        id(self))

class D310(TrackHdr):
   parts = ("dspl", "color", "trk_ident")
   fmt = "<b b s"
   dspl = 0
   color = 0

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

class TimePoint(DataPoint):
   # Not sure what the last four bytes are. Not in docs.
   # hmm... eTrex just sends 8 bytes, no trailing 4 bytes
   parts = ("month", "day", "year", "hour", "min", "sec") #,"unknown")
   fmt = "<b b H h b b" #L"
   month = 0         # month (1-12)
   day = 0           # day (1-32)
   year = 0          # year
   hour = 0          # hour (0-23)
   min = 0           # min (0-59)
   sec = 0           # sec (0-59)

   def __str__(self):
      return "%d-%.2d-%.2d %.2d:%.2d:%.2d UTC" % (
         self.year, self.month, self.day,
         self.hour, self.min, self.sec)

class D600(TimePoint):
   pass

# Position   ---------------------------------------------------

class D700(DataPoint):
   parts = ("rlat", "rlon")
   fmt = "<d d"
   rlat = 0.0  # radians
   rlon = 0.0  # radians

# Pvt ---------------------------------------------------------

# Live position info

class D800(DataPoint):
   parts = ("alt", "epe", "eph", "epv", "fix", "tow", "rlat", "rlon",
            "east", "north", "up", "msl_height", "leap_secs", "wn_days")
   fmt = "<f f f f h d d d f f f f h l"

   def __str__(self):
      return "tow: %g rlat: %g rlon: %g east: %g north %g" \
      % (self.tow, self.rlat, self.rlon, self.east, self.north)

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
   (7,  "GPS 50"),
   (14, "GPS 55"),
   (15, "GPS 55 AVD"),
   (18, "GPS 65"),
   (13, "GPS 75"),
   (23, "GPS 75"),
   (42, "GPS 75"),
   (25, "GPS 85"),
   (39, "GPS 89"),
   (45, "GPS 90"),
   (112, "GPS 92"),
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
   (88, "GPSMAP 215"),
   (29, "GPSMAP 220"),
   (88, "GPSMAP 225"),
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
#                        Use a wide window for best viewing!
#
# ID    minver maxver    Link  Cmnd   Wpt,          Rte,                Trk,          Prx,          Alm
7:   ( (None,            L001, A010, (A100, D100), (A200, D200, D100), None,         None,         (A500, D500) ), ),
13:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
14:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), None,         (A400, D400), (A500, D500) ), ),
15:  ( (None,            L001, A010, (A100, D151), (A200, D200, D151), None,         (A400, D151), (A500, D500) ), ),
18:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
20:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D550) ), ),
22:  ( (None,            L001, A010, (A100, D152), (A200, D200, D152), (A300, D300), (A400, D152), (A500, D500) ), ),
23:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
24:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
25:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
29:  ( ((0.00, 4.00),    L001, A010, (A100, D101), (A200, D201, D101), (A300, D300), (A400, D101), (A500, D500) ),
       ((4.00, MaxVer),  L001, A010, (A100, D102), (A200, D201, D102), (A300, D300), (A400, D102), (A500, D500) ), ),
31:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
33:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D550) ), ),
34:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D550) ), ),
35:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
36:  ( ((0.00, 3.00),    L001, A010, (A100, D152), (A200, D200, D152), (A300, D300), (A400, D152), (A500, D500) ),
       ((3.00, MaxVer),  L001, A010, (A100, D152), (A200, D200, D152), (A300, D300), None,         (A500, D500) ), ),
39:  ( (None,            L001, A010, (A100, D151), (A200, D201, D151), (A300, D300), None,         (A500, D500) ), ),
41:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
42:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
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
88:  ( (None,            L001, A010, (A100, D102), (A200, D201, D102), (A300, D300), (A400, D102), (A500, D501) ), ),
95:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
96:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
97:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), None,         (A500, D501) ), ),
98:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D551) ), ),
100: ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
105: ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
106: ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
112: ( (None,            L001, A010, (A100, D152), (A200, D201, D152), (A300, D300), None,         (A500, D501) ), )
}

def GetProtocols(prod_id, soft_ver):
   bits = ModelProtocols[prod_id]
   for i in bits:
      vrange = i[0]
      if ( (vrange == None) or
           ((soft_ver >= vrange[0]) and (soft_ver < vrange[1]))):
         return i
   raise "No protocols known for this software version. Strange!"

def FormatA001(protocols):
   """This is here to get the list of strings returned by A001 into
    the same format as used in the ModelProtocols dictionary"""

   try:
      phys = eval(protocols[0])
      link = eval(protocols[1])
      cmnd = eval(protocols[2])

      tuples = {"1" : None, "2" : None, "3" : None, "4" : None,
                "5" : None, "6" : None, "7" : None, "8" : None,
                "9" : None}
      last_seen = None
      for i in range(3, len(protocols)):
         p = protocols[i]
         if p[0] == "A":
            pclass = p[1]
            if tuples[pclass] == None:
               tuples[pclass] = []
            last_seen = tuples[pclass]
         elif p[0] == "D":
            pass
         else:
            continue
         last_seen.append(eval(p))
   except NameError:
      print sys.exc_info()[2]
      raise NameError, "Protocol %s not supported yet!" % sys.exc_info()[1]
   return (None, link, cmnd, tuples["1"], tuples["2"], tuples["3"],
           tuples["4"], tuples["5"])

# ====================================================================

# Now some practical implementations

class SerialLink(P000):
   """
     A serial link will look something like this, though real
     implementations will probably override most of it.
   """
   def __init__(self, f, timeout = 5):
      self.f = f
      self.initserial()
      self.settimeout(timeout)

   def initserial(self):
      "Set up baud rate, handshaking, etc"
      pass

   def read(self, n):
      """
      Read n bytes and return them. Real implementations should
      raise a LinkException if there is a timeout > self.timeout
      """
      return self.f.read(n)

   def write(self, data):
      self.f.write(data)

   def settimeout(self, secs):
      self.timeout = secs

   def __del__(self):
      """Should close down any opened resources"""
      pass

# Unix Serial Link ===================================================

if os.name == "posix":
   import tty

class UnixSerialLink(SerialLink):

   def __init__(self, device):
      f = open(device, "w+", 0)
      SerialLink.__init__(self, f)

   def initserial(self):
      fd = self.f.fileno()
      tty.setraw(fd)
      mode = tty.tcgetattr(fd)
      mode[tty.ISPEED] = mode[tty.OSPEED] = tty.B9600
      # mode[tty.LFLAG] = mode[tty.LFLAG] | tty.ECHO
      tty.tcsetattr(fd, tty.TCSAFLUSH, mode)

   def read(self, n):
      i = 0
      data = []
      while i < n:
         iset,oset,eset = select.select([self.f.fileno()], [], [],
                                        self.timeout)
         if iset == []:
           raise LinkException, "time out"
         b = self.f.read(1)
         data.append(b)
         i = i + 1
      return string.join(data,'')

   def __del__(self):
      if self.__dict__.has_key("f"):
         self.f.close()

# Win32 Serial Link ==================================================

if os.name == 'nt':
   import win32file, win32con

class Win32SerialLink(SerialLink):
   def __init__(self, device):
      self.device = device
      handle = win32file.CreateFile(device,
         win32con.GENERIC_READ | win32con.GENERIC_WRITE,
         0, # exclusive access
         None, # no security
         win32con.OPEN_EXISTING,
         0,
         None)
      SerialLink.__init__(self, handle)

   def initserial(self):
      # Remove anything that was there
      win32file.PurgeComm(self.f, win32file.PURGE_TXABORT |
                                  win32file.PURGE_RXABORT |
                                  win32file.PURGE_TXCLEAR |
                                  win32file.PURGE_RXCLEAR )

      # Setup the connection info.
      dcb = win32file.GetCommState( self.f )
      dcb.BaudRate = win32file.CBR_9600
      dcb.ByteSize = 8
      dcb.Parity = win32file.NOPARITY
      dcb.StopBits = win32file.ONESTOPBIT
      win32file.SetCommState(self.f, dcb)

   def read(self, n):
      buffer = win32file.AllocateReadBuffer(n)
      rc, data = win32file.ReadFile(self.f, buffer)
      if len(data) != n:
         raise LinkException, "time out";
      return data

   def write(self, n):
      rc,n = win32file.WriteFile(self.f, n)
      if rc:
         raise LinkException, "WriteFile error";

   def settimeout(self, secs):
      SerialLink.settimeout(self, secs)
      # Setup time-outs
      timeouts = -1, 0, 1000*secs, 0, 1000*secs
      win32file.SetCommTimeouts(self.f, timeouts)

   def __del__(self):
      win32file.CloseHandle(self.f)

class Garmin:
   """
   A representation of the GPS device, which is connected
   via some physical connection, typically a SerialLink of some sort.
   """
   def __init__(self, physicalLayer):
      self.link = L000(physicalLayer)      # at least initially
      (self.prod_id, self.soft_ver,
       self.prod_descs) = A000(self.link).getProductData()

      if debug > 1: print "Get supported protocols"
      # Wait for the unit to announce its capabilities using A001.  If
      # that doesn't happen, try reading the protocols supported by the
      # unit from the Big Table.
      physicalLayer.settimeout(2)
      try:
         self.protocols = A001(self.link).getProtocols()
         protos = FormatA001(self.protocols)
      except LinkException, e:
         if debug > 2: print "PCP not supported"
         try:
            protos = GetProtocols(self.prod_id, self.soft_ver)
         except KeyError:
            raise Exception, "Couldn't determine product capabilities"
      physicalLayer.settimeout(5)

      (versions, self.linkProto, self.cmdProto, wptProtos, rteProtos,
       trkProtos, prxProtos, almProtos) = protos

      self.link = self.linkProto(physicalLayer)

      # The datatypes we expect to receive

      self.wptType = wptProtos[1]
      self.rteTypes = rteProtos[1:]
      self.trkTypes = trkProtos[1:]

      # Now we set up 'links' through which we can get data of the
      # appropriate types

      self.wptLink = wptProtos[0](self.link, self.cmdProto, (self.wptType,))
      self.rteLink = rteProtos[0](self.link, self.cmdProto, self.rteTypes)
      self.trkLink = trkProtos[0](self.link, self.cmdProto, self.trkTypes)

      if prxProtos != None:
         self.prxType = prxProtos[1]
         self.prxLink = prxProtos[0](self.link, self.cmdProto, (self.prxType,))

      if almProtos != None:
         self.almType = almProtos[1]
         self.almLink = almProtos[0](self.link, self.cmdProto, (self.almType,))

      self.timeLink = A600(self.link, self.cmdProto, D600)
      self.pvtLink  = A800(self.link, self.cmdProto, D800)

   def getWaypoints(self, callback = None):
      return self.wptLink.getData(callback)

   def putWaypoints(self, data):
      return self.wptLink.putData(data)

   def getRoutes(self, callback = None):
      return self.rteLink.getData(callback)

   def getTracks(self, callback = None):
      data = self.trkLink.getData(callback)
      if isinstance(self.trkLink, SingleTransferProtocol):
         return [data] # for consistency- compare A300 with A301
      else:
         return data

   def getProxPoints(self, callback = None):
      return self.prxLink.getData(callback)

   def getAlmanac(self, callback = None):
      return self.almLink.getData(callback)

   def getTime(self):
      return self.timeLink.getData()

   def pvtOn(self):
      return self.pvtLink.dataOn()

   def pvtOff(self):
      return self.pvtLink.dataOff()

   def getPvt(self):
      return self.pvtLink.getData()

# =================================================================
# The following is test code. See other included files for more
# useful applications.

def main():
   if os.name == 'nt':
      serialDevice =  "com1"
      phys = Win32SerialLink(serialDevice)
   else:
      serialDevice =  "/dev/ttyS0"
      phys = UnixSerialLink(serialDevice)

   gps = Garmin(phys)

   print "GPS Product ID: %d Descriptions: %s Software version: %2.2f" % \
         (gps.prod_id, gps.prod_descs, gps.soft_ver)

   if 1:
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

   if 0:
      # show track
      tracks = gps.getTracks()
      for t in tracks:
         for p in t:
            print p

   if 0:
      # show almanac
      print gps.getAlmanac()

   if 0:
      # show time
      d = gps.getTime()
      print d.year, d.month, d.day, d.hour, d.min, d.sec

   if 0:
      # upload a waypoint
      w = gps.wptType(
         ident="01TEST",
         cmnt="A TEST POINT",
         slat=624447295,
         slon=-2529985
         )
      gps.putWaypoints([w])
      print "Uploaded", w

   if 0:
      # show some real-time data
      print "Starting pvt"
      gps.pvtOn()
      try:
         for i in range(10):
            p = gps.getPvt()
            print p
      finally:
         print "Stopping pvt"
         gps.pvtOff()



if __name__ == "__main__":
   main()
