#!/usr/bin/env python
"""Module for communicating with Garmin GPS devices.

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

   (c) 2007-2008 Bjorn Tillenius <bjorn.tillenius@gmail.com>
   (c) 2003 Quentin Stafford-Fraser <www.qandr.org/quentin>
   (c) 2000 James A. H. Skillen <jahs@jahs.net>
   (c) 2001 Raymond Penners <raymond@dotsphinx.com>
   (c) 2001 Tom Grydeland <Tom.Grydeland@phys.uit.no>

"""

import os, sys, time
import newstruct as struct
import math
import logging
import string


# Logging setup. If you want to see debug messages, add a logging
# handler for this logger.
log = logging.getLogger('pygarmin')
usb_log = logging.getLogger('pygarmin.usb')
usb_packet_log = logging.getLogger('pygarmin.usb.packet')
# Verbose debug.
VERBOSE = 5


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
    """Physical layer for communicating with Garmin."""

    def read(self, n):
        pass

    def write(self, n):
        pass


# The following is handy for debugging:

def hexdump(data):
    if isinstance(data, int):
        data = struct.pack('<H', data)
    return ''.join(["%02x" % ord(x) for x in data])


# Define Errors

class GarminException:

    def __init__(self,data):
        self.data = data


class LinkException(GarminException):
    """Link error."""

    def __str__(self):
        return "Link Error"


class ProtocolException(GarminException):
    """Protocol error."""

    def __str__(self):
        return "Protocol Error"


# Link protocols ===================================================

class L000:
    """Basic Link Protocol."""

    Pid_Protocol_Array = 253
    Pid_Product_Rqst = 254
    Pid_Product_Data = 255

    def __init__(self, physicalLayer):
        self.phys = physicalLayer

    def sendPacket(self, ptype, data):
        """Send a packet."""
        self.phys.sendPacket(ptype, data)
        log.debug("< packet %3d : %s" % (ptype, hexdump(data)))

    def readPacket(self):
        """Read a packet."""
        ptype, data = self.phys.readPacket()
        log.debug("> packet %3d : %s" % (ptype, hexdump(data)))
        return (ptype, data)

    def expectPacket(self, ptype):
        "Expect and read a particular msg type. Return data."
        tp, data = self.readPacket()
        if tp == 248 and ptype != 248:
            # No idea what packet type 248 is, it's not in the
            # specification. It seems safe to ignore it, though.
            log.debug("Got msg type 248, retrying...")
            tp, data = self.readPacket()

        if tp != ptype:
            raise LinkException, "Expected msg type %d, got %d" % (ptype, tp)

        return data


# L001 builds on L000

class L001(L000):
    """Link protocol 1."""

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
    Pid_FlightBook_Record = 134 # packet with FlightBook data
    Pid_Lap = 149 # part of Forerunner data
    Pid_Wpt_Cat = 152
    Pid_Run = 990

# L002 builds on L000

class L002(L000):
    """Link Protocol 2."""

    Pid_Almanac_Data = 4
    Pid_Command_Data = 11
    Pid_Xfer_Cmplt = 12
    Pid_Date_Time_Data = 20
    Pid_Position_Data = 24
    Pid_Prx_Wpt_Data = 27
    Pid_Records = 35
    Pid_Rte_Hdr = 37
    Pid_Rte_Wpt_Data = 39
    Pid_Wpt_Data = 43


# Application Protocols =======================================

# A000 and A001 are used to find out what is on the other end of the
# wire, and hence which other protocols we can use.

class A000:
    """Product data protocol."""

    def __init__(self, linkLayer):
        self.link = linkLayer

    def getProductData(self):
        fmt = "<hh"
        self.link.sendPacket(self.link.Pid_Product_Rqst,"")
        data = self.link.expectPacket(self.link.Pid_Product_Data)
        (prod_id, soft_ver)   = struct.unpack(fmt, data[:4])
        prod_descs = data[4:-1].split("\0")

        return (prod_id, soft_ver/100.0, prod_descs)


class A001:
    """Protocol capabilities protocol."""

    def __init__(self, linkLayer):
        self.link=linkLayer

    def getProtocols(self):
        log.log(VERBOSE, "Try reading protocols using PCP")

        data = self.link.expectPacket(self.link.Pid_Protocol_Array)
        num = len(data)/3
        fmt = "<"+num*"ch"
        tup = struct.unpack(fmt, data)
        self.protocols = []

        for i in range(0, 2*num, 2):
            self.protocols.append(tup[i]+"%03d"%tup[i+1])

        log.info("Protocols reported by A001: %s", self.protocols)

        return self.protocols

    def getProtocolsNoPCP(self,prod_id, soft_ver):
        try:
            search_protocols = ModelProtocols[prod_id]

            for search_protocol in search_protocols:
                vrange = search_protocol[0]

                if ((vrange == None) or
                    ((soft_ver >= vrange[0]) and (soft_ver < vrange[1]))):
                    break

        except:
            raise "No protocols known for this software version. Strange!"

        # Ok, now we have de protocol
        self.protocols = [x for x in search_protocol[1:] if x]

        self.protocols.append("A700")
        self.protocols.append("D700")
        self.protocols.append("A800")
        self.protocols.append("D800")

        return self.protocols

    def FormatA001(self):
        # This is here to get the list of strings returned by A001 into objects
        protos = {}
        protos_unknown = []
        known = None

        for x in self.protocols:

            if x == "P000":
                protos["phys"] = [eval(x)]
            elif x == "L001":
                protos["link"] = [eval(x)]
            elif x in ["A010","A011"]:
                protos["command"] = [eval(x)]
            elif x == "A100":
                known = True
                ap_prot = "waypoint" # Application Protocol
                protos[ap_prot] = [eval(x)]
            elif x in ["A200","A201"]:
                known = True
                ap_prot = "route"
                protos[ap_prot] = [eval(x)]
            elif x in ["A300","A301","A302"]:
                known = True
                ap_prot = "track"
                protos[ap_prot] = [eval(x)]
            elif x == "A400":
                known = True
                ap_prot = "proximity"
                protos[ap_prot] = [eval(x)]
            elif x == "A500":
                known = True
                ap_prot = "almanac"
                protos[ap_prot] = [eval(x)]
            elif x == "A600":
                known = True
                ap_prot = "data_time"
                protos[ap_prot] = [eval(x)]
            elif x == "A650":
                known = True
                ap_prot = "flightbook"
                protos[ap_prot] = [eval(x)]
            elif x == "A700":
                known = True
                ap_prot = "position"
                protos[ap_prot] = [eval(x)]
            elif x == "A800":
                known = True
                ap_prot = "pvt"
                protos[ap_prot] = [eval(x)]
            elif x == "A906":
                known = True
                ap_prot = "lap"
                protos[ap_prot] = [eval(x)]
            elif x == "A1000":
                known = True
                ap_prot = "run"
                protos[ap_prot] = [eval(x)]
            elif x[0] == "A":
                # No info about this Application Protocol
                known = False
                protos_unknown.append(x)

                log.info("Protocol %s not supported yet!" % x)

            elif (x[0] == "D"):
                if known:
                    protos[ap_prot].append(eval(x))
                else:
                    protos_unknown.append(x)

        log.info("Processing protocols")
        log.info(protos)

        return protos, protos_unknown


# Commands  ---------------------------------------------------

class A010:
    """Device command protocol 1."""
    Cmnd_Abort_Transfer = 0        # abort current transfer
    Cmnd_Transfer_Alm = 1          # transfer almanac
    Cmnd_Transfer_Posn = 2         # transfer position
    Cmnd_Transfer_Prx = 3          # transfer proximity waypoints
    Cmnd_Transfer_Rte = 4          # transfer routes
    Cmnd_Transfer_Time = 5         # transfer time
    Cmnd_Transfer_Trk = 6          # transfer track log
    Cmnd_Transfer_Wpt = 7          # transfer waypoints
    Cmnd_Turn_Off_Pwr = 8          # turn off power
    Cmnd_Start_Pvt_Data = 49       # start transmitting PVT data
    Cmnd_Stop_Pvt_Data = 50        # stop transmitting PVT data
    Cmnd_FlightBook_Transfer = 92  # transfer flight records
    Cmnd_Transfer_Laps = 117       # transfer laps
    Cmnd_Transfer_Runs = 450       # transfer runs
    Cmnd_Transfer_Wpt_Cats = 121   # transfer waypoint categories


class A011:
    """Device command protocol 2."""

    Cmnd_Abort_Transfer = 0   # abort current transfer
    Cmnd_Transfer_Alm = 4     # transfer almanac
    Cmnd_Transfer_Rte = 8     # transfer routes
    Cmnd_Transfer_Prx = 17    # transfer proximity waypoints
    Cmnd_Transfer_Time = 20   # transfer time
    Cmnd_Transfer_Wpt = 21    # transfer waypoints
    Cmnd_Turn_Off_Pwr = 26    # turn off power


# Transfer Protocols -------------------------------------------

# Most of the following protocols transfer groups of records of a
# particular format. The exact format depends on the product in use.
# Some records may have sub-groups within the transfer (eg. routes)
# each with their own header.

class TransferProtocol:

    def __init__(self, link, cmdproto, datatypes = None):
        self.link = link
        self.cmdproto = cmdproto

        if type(datatypes) == list:
            self.datatypes = datatypes
        else:
            self.datatypes = (datatypes,)

    def putData(self,callback,cmd,sendData):

        numrecords = len(sendData)
        x = 0

        log.log(
            VERBOSE, "%s: Sending %d records" % (self.__doc__, numrecords))

        self.link.sendPacket(self.link.Pid_Records, numrecords)

        for tp,data in sendData:
            self.link.sendPacket(tp, data.pack())

            if callback:

                try:
                    x += 1
                    callback(data,x,numrecords,tp)
                except:
                    raise

        self.link.sendPacket(self.link.Pid_Xfer_Cmplt,cmd)

    def abortTransfer(self):
        self.link.sendPacket(
            self.link.Pid_Command_Data,self.cmdproto.Cmnd_Abort_Transfer)

    def turnPowerOff(self):
        self.link.sendPacket(
            self.link.Pid_Command_Data,self.cmdproto.Cmnd_Turn_Off_Pwr)


class SingleTransferProtocol(TransferProtocol):

    def getData(self, callback, cmd, pid):
        self.link.sendPacket(self.link.Pid_Command_Data, cmd)
        data = self.link.expectPacket(self.link.Pid_Records)
        (numrecords,) = struct.unpack("<h", data)

        log.log(
            VERBOSE, "%s: Expecting %d records" % (self.__doc__, numrecords))

        result = []

        for i in range(numrecords):
            data = self.link.expectPacket(pid)
            p = self.datatypes[0]()
            p.unpack(data)
            result.append(str(p))

            if callback:

                try:
                    callback(p,i + 1,numrecords,pid)
                except:
                    raise

        self.link.expectPacket(self.link.Pid_Xfer_Cmplt)

        return result


class MultiTransferProtocol(TransferProtocol):

    def getData(self, callback, cmd, hdr_pid, *data_pids):

        self.link.sendPacket(self.link.Pid_Command_Data, cmd)

        data = self.link.expectPacket(self.link.Pid_Records)
        (numrecords,) = struct.unpack("<h", data)

        log.log(
            VERBOSE, "%s: Expecting %d records" % (self.__doc__, numrecords))

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
                    callback(p,i + 1,numrecords,tp)
                except:
                    raise

        self.link.expectPacket(self.link.Pid_Xfer_Cmplt)

        if last:
            result.append(last)

        return result


class T001:
    """T001 implementation.

    No documentation as of 2004-02-24."""


class A100(SingleTransferProtocol):
    """Waypoint transfer protocol."""

    def getData(self, callback = None):
        return SingleTransferProtocol.getData(self, callback,
                                                                                                                                                                self.cmdproto.Cmnd_Transfer_Wpt,
                                                                                                                                                                self.link.Pid_Wpt_Data)

    def putData(self,data,callback):
        sendData = []

        for waypoint in data:
            waypointInstance = self.datatypes[0](waypoint)
            sendData.append((self.link.Pid_Wpt_Data,waypointInstance))

        return SingleTransferProtocol.putData(
            self,callback,self.cmdproto.Cmnd_Transfer_Wpt,sendData)


class A101(SingleTransferProtocol):
    """Waypoint transfer protocol."""

    def getData(self, callback = None):
        return SingleTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Wpt_Cats,
            self.link.Pid_Wpt_Cat)


class A200(MultiTransferProtocol):
    """Route transfer protocol."""

    def getData(self, callback = None):
        return MultiTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Rte,
            self.link.Pid_Rte_Hdr, self.link.Pid_Rte_Wpt_Data)

    def putData(self,data,callback):
        sendData = []
        header = {}
        routenr = 0

        for route in data:
            routenr += 1

            # Copy the header fields
            header = {}
            for head in route[0].keys():
                header[head] = route[0][head]

            # Give a routenr
            if not header.has_key('nmbr'): header['nmbr'] = routenr

            # Check route names
            # if no name, give it a name
            if not header.has_key('ident') or not header.has_key('cmnt'):

                if header.has_key('ident'):
                    header['cmnt'] = header['ident']
                elif header.has_key('cmnt'):
                    header['ident'] = header['cmnt']
                else:
                    header['ident'] = header['cmnt'] = "ROUTE " + str(routenr)

            headerInstance = self.datatypes[0](header)
            sendData.append((self.link.Pid_Rte_Hdr,headerInstance))

            for waypoint in route[1:]:
                waypointInstance = self.datatypes[1](waypoint)
                sendData.append((self.link.Pid_Rte_Wpt_Data,waypointInstance))

        return MultiTransferProtocol.putData(
            self, callback,self.cmdproto.Cmnd_Transfer_Rte,sendData)


class A201(MultiTransferProtocol):
    """Route transfer protocol."""

    def getData(self, callback = None):
        return MultiTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Rte,
            self.link.Pid_Rte_Hdr, self.link.Pid_Rte_Wpt_Data,
            self.link.Pid_Rte_Link_Data)

    def putData(self,data,callback):
        sendData = []
        header = {}
        routenr = 0

        for route in data:
            routenr += 1

            # Copy the header fields
            header = {}
            for head in route[0].keys():
                header[head] = route[0][head]

            # Give a routenr
            if not header.has_key('nmbr'): header['nmbr'] = routenr

            # Check route names
            # if no name, give it a name
            if not header.has_key('ident') or not header.has_key('cmnt'):

                if header.has_key('ident'):
                    header['cmnt'] = header['ident']
                elif header.has_key('cmnt'):
                    header['ident'] = header['cmnt']
                else:
                    header['ident'] = header['cmnt'] = "Route " + str(routenr)

            headerInstance = self.datatypes[0](header)
            sendData.append((self.link.Pid_Rte_Hdr,headerInstance))

            for waypoint in route[1:]:
                waypointInstance = self.datatypes[1](waypoint)
                linkInstance = self.datatypes[2]()
                sendData.append((self.link.Pid_Rte_Wpt_Data,waypointInstance))
                sendData.append((self.link.Pid_Rte_Link_Data,linkInstance))

        return MultiTransferProtocol.putData(
            self, callback,self.cmdproto.Cmnd_Transfer_Rte, sendData)


class A300(SingleTransferProtocol):
    """Track log transfer protocol."""

    def getData(self, callback = None):
        return SingleTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Trk,
            self.link.Pid_Trk_Data)

    def putData(self,data,callback):
        sendData = []

        for waypoint in data:
            waypointInstance = self.datatypes[0](waypoint)
            sendData.append((self.link.Pid_Trk_Data,waypointInstance))

        return SingleTransferProtocol.putData(
            self,callback,self.cmdproto.Cmnd_Transfer_Trk,sendData)


class A301(MultiTransferProtocol):
    """Track log transfer protocol."""

    def getData(self, callback = None):
        return MultiTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Trk,
            self.link.Pid_Trk_Hdr, self.link.Pid_Trk_Data)

    def putData (self,data,callback):
        sendData = []
        header = {}
        tracknr = 0

        for track in data:
            tracknr += 1

            # Copy the header fields
            header = {}
            for head in track[0].keys():
                header[head] = track[0][head]

            # Check track names
            # if no name, give it a name
            if not header.has_key('ident'):
                header['ident'] = "TRACK" + str(tracknr)

            headerInstance = self.datatypes[0](header)
            sendData.append((self.link.Pid_Trk_Hdr,headerInstance))

            firstSegment = True

            for waypoint in track[1:]:
                trackPointInstance = self.datatypes[1](waypoint)

                # First point in a track is always a new track segment
                if firstSegment:
                    trackPointInstance.dataDict['new_trk'] = True
                    firstSegment = False

                sendData.append((self.link.Pid_Trk_Data,trackPointInstance))

        return MultiTransferProtocol.putData(
            self,callback,self.cmdproto.Cmnd_Transfer_Trk,sendData)


class A302(A301):
    """Track log transfer protocol."""


class A400(SingleTransferProtocol):
    """Proximity waypoint transfer protocol."""

    def getData(self, callback = None):
        return SingleTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Prx,
            self.link.Pid_Prx_Wpt_Data)

    def putData(self,data,callback):
        sendData = []

        for waypoint in data:
            waypointInstance = self.datatypes[0](waypoint)
            sendData.append((self.link.Pid_Prx_Wpt_Data,waypointInstance))

        return SingleTransferProtocol.putData(
            self,callback,self.cmdproto.Cmnd_Transfer_Prx,sendData)


class A500(SingleTransferProtocol):
    """Almanac transfer protocol."""

    def getData(self, callback):
        return SingleTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Alm,
            self.link.Pid_Almanac_Data)


class A600(TransferProtocol):
    """Waypoint date & time initialization protocol."""

    def getData(self,callback):
        self.link.sendPacket(
            self.link.Pid_Command_Data, self.cmdproto.Cmnd_Transfer_Time)
        data = self.link.expectPacket(self.link.Pid_Date_Time_Data)
        p = self.datatypes[0]()
        p.unpack(data)

        if callback:
            try:
                callback(p,1,1,self.link.Pid_Command_Data)
            except:
                raise

        return p


class A601(TransferProtocol):
    """A601 implementaion.

    Used by GPSmap 60cs, no specifications as of 2004-09-26."""


class A650(SingleTransferProtocol):
    """FlightBook transfer protocol."""

    def getData(self,callback):
        return SingleTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_FlightBook_Transfer,
            self.link.Pid_FlightBook_Record)


class A700(TransferProtocol):
    """Position initialisation protocol."""


class A800(TransferProtocol):
    """PVT data protocol.

    Live Position, Velocity and Time, similar to that provided by NMEA.
    """

    def dataOn(self):
        self.link.sendPacket(
            self.link.Pid_Command_Data, self.cmdproto.Cmnd_Start_Pvt_Data)

    def dataOff(self):
        self.link.sendPacket(
            self.link.Pid_Command_Data, self.cmdproto.Cmnd_Stop_Pvt_Data)

    def getData(self,callback):
        tp, data = self.link.readPacket()

        p = self.datatypes[0]()
        p.unpack(data)

        if callback:

            try:
                callback(p,1,1,tp)
            except:
                raise

        return p


class A801:
    """A801 implementation.

    Used by ?, no documentation as of 2001-05-30.
    """


class A802:
    """A802 implementation.

    Used by ?, no documentation as of 2001-05-30.
    """


class A900:
    """A900 implementation.

    Used by GPS III+, no documentation as of 2000-09-18.
    """


class A902:
    """A902 implementation.

    Used by etrex, no documentation as of 2001-05-30.
    """


class A903:
    """A903 implementation.

    Used by etrex, no documentation as of 2001-05-30.
    """


class A904:
    """A904 implementation.

    No documentation as of 2004-02-24.
    """


class A906(MultiTransferProtocol):
    """Lap transfer protocol."""

    def getData(self,callback):
        return MultiTransferProtocol.getData(
            self, callback,
            self.cmdproto.Cmnd_Transfer_Laps, self.link.Pid_Lap)


class A1000(MultiTransferProtocol):
    """Run Transfer Protocol."""

    def getData(self, callback):
        return MultiTransferProtocol.getData(
            self, callback,
            self.cmdproto.Cmnd_Transfer_Runs, self.link.Pid_Run)


class A907(TransferProtocol):
    """A907 implementation.

    Used by GPSmap 60cs, no documentation as of 2004-09-26.
    """


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
            print "Parts:  <" + ", ".join(self.parts) + ">"
            print "Input:  <" + "><".join(bytes) + ">"
            raise


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
    R = 6367000
    rlat1 = radian(wp1.slat)
    rlon1 = radian(wp1.slon)
    rlat2 = radian(wp2.slat)
    rlon2 = radian(wp2.slon)
    dlon = rlon2 - rlon1
    dlat = rlat2 - rlat1
    a =  (
        math.pow(math.sin(dlat/2),2) +
        math.cos(rlat1)*math.cos(rlat2)*math.pow(math.sin(dlon/2),2))
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
        return "<Waypoint %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
                                                         degrees(self.slat),
                                                         degrees(self.slon),
                                                         id(self))

    def __str__(self):
        return "%s (%3.5f, %3.5f)" % (self.ident,
                                      degrees(self.slat),
                                      degrees(self.slon))

    def getDict(self):
        self.data = {
            'name': self.ident,
            'comment': self.cmnt,
            'latitude': self.slat,
            'longitude': self.slon,
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
        return "<Waypoint %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
                                                         degrees(self.slat),
                                                         degrees(self.slon),
                                                         id(self))

    def __str__(self):
        return "%s (%3.5f, %3.5f)" % (self.ident,
                                      degrees(self.slat),
                                      degrees(self.slon))

    def getDict(self):
        self.data = {'name': self.ident,
                     'comment': self.cmnt.strip(),
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
        return "<Waypoint %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
                                                         degrees(self.slat),
                                                         degrees(self.slon),
                                                         id(self))

    def __str__(self):
        return "%s (%3.5f, %3.5f)" % (self.ident,
                                      degrees(self.slat),
                                      degrees(self.slon))

    def getDict(self):
        self.data = {'name': self.ident,
                     'comment': self.cmnt.strip(),
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
        return "<Waypoint %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
                                                         degrees(self.slat),
                                                         degrees(self.slon),
                                                         id(self))

    def __str__(self):
        return "%s (%3.5f, %3.5f)" % (self.ident,
                                      degrees(self.slat),
                                      degrees(self.slon))

    def getDict(self):
        self.data = {'name': self.ident,
                     'comment': self.cmnt.strip(),
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
        return "<Waypoint %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
                                                         degrees(self.slat),
                                                         degrees(self.slon),
                                                         id(self))

    def __str__(self):
        return "%s (%3.5f, %3.5f)" % (self.ident,
                                      degrees(self.slat),
                                      degrees(self.slon))

    def getDict(self):
        self.data = {'name': self.ident,
                     'comment': self.cmnt.strip(),
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
        return "<Waypoint %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
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

    parts = ("wpt_class", "subclass", "slat", "slon", "smbl",
             "ident", "lnk_ident")
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
        return "<Waypoint %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
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
        return "<Waypoint %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
                                                         degrees(self.slat),
                                                         degrees(self.slon),
                                                         id(self))

    def __str__(self):
        return "%s (%3.5f, %3.5f)" % (self.ident,
                                      degrees(self.slat),
                                      degrees(self.slon))

    def getDict(self):
        self.data = {'name': self.ident,
                     'comment': self.cmnt.strip(),
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
        return "<Waypoint %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
                                                         degrees(self.slat),
                                                         degrees(self.slon),
                                                         id(self))

    def __str__(self):
        return "%s (%3.5f, %3.5f, %3f) '%s' class %d symbl %d" % (
           self.ident,
           degrees(self.slat), degrees(self.slon),
           self.alt, self.cmnt.strip(),
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
        return "<Waypoint %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
                                                         degrees(self.slat),
                                                         degrees(self.slon),
                                                         id(self))

    def __str__(self):
        return "%s (%3.5f, %3.5f, %3f) '%s' class %d symbl %d" % (
           self.ident,
           degrees(self.slat), degrees(self.slon),
           self.alt, self.cmnt.strip(),
           self.wpt_class, self.smbl)


class D110(Waypoint):

    parts = ("dtyp", "wpt_class", "dspl_color", "attr", "smbl",
             "subclass", "slat", "slon", "alt", "dpth", "dist",
             "state", "cc", "ete", "temp", "time", "wpt_cat",
             "ident", "cmnt", "facility", "city", "addr", "cross_road")
    fmt = "<b b b b h 18s l l f f f 2s 2s l f l i s s s s s s"


class D120(DataPoint):

    parts = ("name",)
    fmt = "<17s"


class D150(Waypoint):

    parts = ("ident", "cc", "clss", "lat", "lon", "alt",
             "city", "state", "name", "cmnt")
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

# I don't think this should be here. D210 is a RouteLink, and 
# is defined below.
#
# class D210(DataPoint):
#     parts = ("class", "subclass", "ident")
#     fmt = "<i 18s s"


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
        return "<Trackpoint (%3.5f, %3.5f) %s (at %i)>" % (
            degrees(self.slat), degrees(self.slon),
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


class D302(TrackPoint):

    parts = ("slat", "slon", "time", "alt", "depth", "temp", "new_trk")
    fmt = "<l l L f f f b"


class D304(TrackPoint):

    parts = (
        "slat", "slon", "time", "alt", "distance", "heart_rate", "cadence",
        "sensor")
    fmt = "<l l L f f B B B"
    alt = 0.0
    distance = 0.0
    heart_rate = 0
    cadence = 0
    sensor = False


# Track headers ----------------------------------------------

class TrackHdr(DataPoint):

    trk_ident = ""

    def __repr__(self):
        return "<TrackHdr %s (at %i)>" % (self.trk_ident,
                                          id(self))

class D310(TrackHdr):

    parts = ("dspl", "color", "trk_ident")
    fmt = "<b b s"
    dspl = 0
    color = 0


class D311(TrackHdr):

    parts = ("index",)
    fmt = "<H"


class D312(TrackHdr):

    parts = ("dspl", "color", "trk_ident")
    fmt = "<b b s"


# Proximity waypoints  ---------------------------------------

class ProxPoint(DataPoint):

    dst = 0.0


class D400(ProxPoint, D100):

    parts = D100.parts + ("dst",)
    fmt = D100.fmt + " f"


class D403(ProxPoint, D103):

    parts = D103.parts + ("dst",)
    fmt = D103.fmt + " f"


class D450(ProxPoint, D150):

    parts = ("idx",) + D150.parts + ("dst",)
    fmt = "<i " + D150.fmt[1:] + " f"
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


class D601(TimePoint):
    """D601 time point.

    Used by GPSmap 60cs, no documentation as of 2004-09-26.
    """


class D650(DataPoint):

    parts = ("takeoff_time", "landing_time", "takeoff_slat", "takeoff_slon",
             "landing_slat", "landing_slon", "night_time", "num_landings",
             "max_speed", "max_alt", "distance", "cross_country_flag",
             "departure_name", "departure_ident", "arrival_name",
             "arrival_ident", "ac_id")
    fmt = "<L L l l l l L L f f f B s s s s s"


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


class D906(DataPoint):

    parts = ("start_time", "total_time", "total_distance", "begin_slat",
             "begin_slon", "end_slat", "end_slon", "calories",
             "track_index", "unused")
    fmt = "<l l f l l l l i b b"


class D907(DataPoint):
    """D907 data point.

    Used by GPSmap 60cs, no documentation as of 2004-09-26.
    """


class D908(DataPoint):
    """D908 data point.

    Used by GPSmap 60cs, no documentation as of 2004-09-26.
    """


class D909(DataPoint):
    """D909 data point.

    Used by GPSmap 60cs, no documentation as of 2004-09-26.
    """


class D910(DataPoint):
    """D910 data point.

    Used by GPSmap 60cs, no documentation as of 2004-09-26.
    """


class D1011(DataPoint):
    """A lap point.

    Used by Edge 305.
    """

    parts = ("index", "unused", "start_time", "total_time", "total_dist",
             "max_speed", "begin_lat", "begin_lon", "end_lat", "end_lon",
             "calories", "avg_heart_rate", "max_heart_rate",
             "intensity", "avg_cadence", "trigger_method")
    fmt = "<H H L L f f l l l l H B B B B B"

    def __repr__(self):
        return "<Lap %i (%3.5f, %3.5f) %s (duration %i seconds)>" % (
            self.index, degrees(self.begin_lat), degrees(self.begin_lon),
            time.asctime(time.gmtime(TimeEpoch+self.start_time)),
            int(self.total_time/100))


class D1015(D1011):
    """A lap point.

    Used by Forerunner 305. This data type is not documented in the
    specification, but there has been reports that this works.
    """


class D1009(DataPoint):
    """A run data point."""

    parts = ("track_index", "first_lap_index", "last_lap_index",
             "sport_type", "program_type",
             "multisport", "unused1", "unused2",
             "quick_workout_time", "quick_workout_distance")
    fmt = "<H H H B B B B H L f"

    def __repr__(self):
        return "<Run %i, lap %i to %i>" % (
            self.track_index, self.first_lap_index, self.last_lap_index)


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
   (291, "GPSMAP 60cs"),
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
# ID    minver maxver    Link     Cmnd   Wpt,            Rte,                    Trk,             Prx,           Alm
7:   ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", None,           None,           "A500", "D500" ), ),
13:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
14:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", None,           "A400", "D400", "A500", "D500" ), ),
15:  ( (None,            "L001", "A010", "A100", "D151", "A200", "D200", "D151", None,           "A400", "D151", "A500", "D500" ), ),
18:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
20:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D550" ), ),
22:  ( (None,            "L001", "A010", "A100", "D152", "A200", "D200", "D152", "A300", "D300", "A400", "D152", "A500", "D500" ), ),
23:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
24:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
25:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
29:  ( ((0.00, 4.00),    "L001", "A010", "A100", "D101", "A200", "D201", "D101", "A300", "D300", "A400", "D101", "A500", "D500" ),
       ((4.00, MaxVer),  "L001", "A010", "A100", "D102", "A200", "D201", "D102", "A300", "D300", "A400", "D102", "A500", "D500" ), ),
31:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None    ,       "A500", "D500" ), ),
33:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D550" ), ),
34:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D550" ), ),
35:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
36:  ( ((0.00, 3.00),    "L001", "A010", "A100", "D152", "A200", "D200", "D152", "A300", "D300", "A400", "D152", "A500", "D500" ),
       ((3.00, MaxVer),  "L001", "A010", "A100", "D152", "A200", "D200", "D152", "A300", "D300", None,           "A500", "D500" ), ),
39:  ( (None,            "L001", "A010", "A100", "D151", "A200", "D201", "D151", "A300", "D300", None,           "A500", "D500" ), ),
41:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
42:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
44:  ( (None,            "L001", "A010", "A100", "D101", "A200", "D201", "D101", "A300", "D300", "A400", "D101", "A500", "D500" ), ),
45:  ( (None,            "L001", "A010", "A100", "D152", "A200", "D201", "D152", "A300", "D300", None,           "A500", "D500" ), ),
47:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
48:  ( (None,            "L001", "A010", "A100", "D154", "A200", "D201", "D154", "A300", "D300", None,           "A500", "D501" ), ),
49:  ( (None,            "L001", "A010", "A100", "D102", "A200", "D201", "D102", "A300", "D300", "A400", "D102", "A500", "D501" ), ),
50:  ( (None,            "L001", "A010", "A100", "D152", "A200", "D201", "D152", "A300", "D300", None,           "A500", "D501" ), ),
52:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D550" ), ),
53:  ( (None,            "L001", "A010", "A100", "D152", "A200", "D201", "D152", "A300", "D300", None,           "A500", "D501" ), ),
55:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
56:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
59:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
61:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
62:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
64:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D551" ), ),
71:  ( (None,            "L001", "A010", "A100", "D155", "A200", "D201", "D155", "A300", "D300", None,           "A500", "D501" ), ),
72:  ( (None,            "L001", "A010", "A100", "D104", "A200", "D201", "D104", "A300", "D300", None,           "A500", "D501" ), ),
73:  ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", None,           "A500", "D501" ), ),
74:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
76:  ( (None,            "L001", "A010", "A100", "D102", "A200", "D201", "D102", "A300", "D300", "A400", "D102", "A500", "D501" ), ),
77:  ( ((0.00, 3.01),    "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", "A400", "D400", "A500", "D501" ),
       ((3.01, 3.50),    "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ),
       ((3.50, 3.61),    "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", None,           "A500", "D501" ),
       ((3.61, MaxVer),  "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
87:  ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
88:  ( (None,            "L001", "A010", "A100", "D102", "A200", "D201", "D102", "A300", "D300", "A400", "D102", "A500", "D501" ), ),
95:  ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
96:  ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
97:  ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", None,           "A500", "D501" ), ),
98:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D551" ), ),
100: ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
105: ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
106: ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
112: ( (None,            "L001", "A010", "A100", "D152", "A200", "D201", "D152", "A300", "D300", None,           "A500", "D501" ), )
}

# ====================================================================


# Now some practical implementations


class SerialLink(P000):
    """Protocol to communicate over a serial link."""

    Pid_Ack_Byte = 6
    Pid_Nak_Byte = 21

    # DataLinkEscape etc
    DLE                  = "\x10"
    ETX                  = "\x03"
    EOM                  = DLE+ETX

    unit_id = None

    def __init__(self, device, timeout = 5):
        # Import serial here, so that you don't have to have that module
        # installed, if you're not using a serial link.
        import serial
        self.timeout = timeout
        self.ser = serial.Serial(device, timeout=self.timeout, baudrate=9600)

    def initserial(self):
        """Set up baud rate, handshaking, etc."""
        pass

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
        self.write(bytes)
        if readAck:
            self.readAcknowledge(ptype)

    def readPacket(self, sendAck=1):
        " Read a message. By default this will also send the ack."
        dle = self.read(1)
        # Find the start of a message
        while dle != self.DLE:
            print "resync - expected DLE and got something else: %r" % dle
            dle = self.read(1)
        # We've now found either the start or the end of a msg
        # Try reading the type.
        tp = self.read(1)
        if tp == self.ETX:
            # It was the end!
            dle = self.read(1)
            tp = self.read(1)
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
        eom = self.read(2)
        assert eom==self.EOM, "Invalid EOM seen"
        if sendAck:
            self.sendAcknowledge(ptype)
        return (ptype, data)

    def readAcknowledge(self, ptype):
        "Read an ack msg in response to a particular sent msg"
        log.debug("(>ack)")
        tp, data = self.readPacket(0)
        if (tp & 0xff) != self.Pid_Ack_Byte or ord(data[0]) != ptype:
            raise LinkException, "Acknowledge error"

    def sendAcknowledge(self, ptype):
        log.debug("(<ack)")
        self.sendPacket(self.Pid_Ack_Byte, struct.pack("<h", ptype), 0)

    def readEscapedByte(self):
        c = self.read(1)
        if c == self.DLE:
            c = self.read(1)
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

    def read(self, n):
        """Read n bytes and return them.

        Real implementations should raise a LinkException if there is a
        timeout > self.timeout
        """
        return self.ser.read(n)

    def write(self, data):
        self.ser.write(data)

    def settimeout(self, secs):
        self.timeout = secs

    def __del__(self):
        """Should close down any opened resources."""
        self.close()

    def close(self):
        """Close the serial port."""
        if "ser" in self.__dict__:
            self.ser.close()


class USBLink:
    """Implementation of the Garmin USB protocol.

    It will talk to the first Garmin GPS device it finds.
    """

    Pid_Data_Available = 2
    Pid_Start_Session = 5
    Pid_Session_Started = 6
    # These arent in the specification, but this is what Edge 305
    # uses.
    Pid_Start_Session2 = 16
    Pid_Session_Started2 = 17

    def __init__(self):
        # Import usb here, so that you don't have to have that module
        # installed, if you're not using a usb link.
        import usb
        self.garmin_dev = None
        for bus in usb.busses():
            for dev in bus.devices:
                if dev.idVendor == 2334:
                    self.garmin_dev = dev
                    break
            if self.garmin_dev:
                break
        else:
            raise LinkException("No Garmin device found!")
        self.handle = self.garmin_dev.open()
        self.handle.claimInterface(0)

        try:
            self.startSession()
        except usb.USBError, error:
            if error.message == "No error":
                # I'm not sure why we get a "No error" error something,
                # but I suspect the device wasn't in a good state.
                # Simply restarting the session once seems to solve it.
                self.startSession()
            else:
                raise

    def startSession(self):
        """Start the USB session."""
        start_packet = self.constructPacket(0, self.Pid_Start_Session)
        self.sendUSBPacket(start_packet)
        # Some devices use another start packet.
        start_packet2 = self.constructPacket(0, self.Pid_Session_Started2)
        self.sendUSBPacket(start_packet2)
        self.unit_id = self.readSessionStartedPacket()

    def readSessionStartedPacket(self):
        """Read from the USB bus until session started packet is received."""
        session_started = False
        unit_id_data = None
        while not session_started:
            packet = self.readUSBPacket(16)
            if len(packet) != 16:
                continue
            # We have something that could be the right packet.
            packet_id, unit_id_data = self.unpack(packet)
            if packet_id in [self.Pid_Session_Started,
                             self.Pid_Session_Started2]:
                session_started = True
        [self.unit_id] = struct.unpack("<L", unit_id_data)

    def constructPacket(self, layer, packet_id, data=None):
        """Construct an USB package to be sent."""
        if data:
            if isinstance(data, int):
                data = struct.pack("<h", data)
            data_part = list(struct.pack("<l", len(data)))
            data_part += list(data)
        else:
            data_part = [chr(0)]*4

        package = [chr(layer)]
        package += [chr(0)]*3
        package += list(struct.pack("<h", packet_id))
        package += [chr(0)]*2
        package += data_part
        return package

    def sendPacket(self, tp, data):
        """Send a packet."""
        packet = self.constructPacket(20, tp, data)
        self.sendUSBPacket(packet)

    def sendUSBPacket(self, packet):
        """Send a packet over the USB bus."""
        usb_log.debug("Sending %s bytes..." % len(packet))
        usb_packet_log.debug("< usb: %s" % (hexdump(packet)))
        sent = self.handle.bulkWrite(0x02, packet)
        usb_log.debug("Sent %s bytes" % sent)

    def unpack(self, packet):
        """Unpack a raw USB package, which is a list of bytes.

        Return a tuple: (packet_id, data)"""
        header = packet[:12]
        data = packet[12:]
        packet_type, unused1, unused2, packet_id, reserved, data_size = (
            struct.unpack("<b h b h h l", header))
        return packet_id, data

    def readPacket(self, size=1024):
        """Read a packet."""
        packet = self.readUSBPacket(size)
        packet_id, data = self.unpack(packet)
        return packet_id, data

    def readUSBPacket(self, size):
        """Read a packet over USB bus."""
        usb_log.debug("Reading %s bytes..." % size)
        packet = self.handle.interruptRead(0x81, size)
        packet = ''.join(struct.pack("<B", byte) for byte in packet)
        usb_packet_log.debug("> usb: %s" % (hexdump(packet)))
        usb_log.debug("Read %s bytes" % len(packet))
        return packet

    def settimeout(self, timeout):
        pass

    def close(self):
        self.handle.releaseInterface()


class Garmin:
    """A representation of the GPS device.

    It is connected via some physical connection, typically a SerialLink
    of some sort.
    """

    def __init__(self, physicalLayer):
        self.unit_id = physicalLayer.unit_id
        self.link = L000(physicalLayer)      # at least initially
        product_data = A000(self.link).getProductData()
        (self.prod_id, self.soft_ver,self.prod_descs) = product_data

        log.info("Getting supported protocols")

        # Wait for the unit to announce its capabilities using A001.  If
        # that doesn't happen, try reading the protocols supported by the
        # unit from the Big Table.
        physicalLayer.settimeout(2)
        try:
            protocol = A001(self.link)
            self.protocols = protocol.getProtocols()
            self.protos , self.protocols_unknown = protocol.FormatA001()

        except LinkException, e:

            log.log(VERBOSE, "PCP not supported")

            try:
                self.protocols = protocol.getProtocolsNoPCP(
                    self.prod_id, self.soft_ver)
                self.protos , self.protocols_unknown = protocol.FormatA001()
            except KeyError:
                raise Exception, "Couldn't determine product capabilities"

        physicalLayer.settimeout(5)

        self.link = self.protos["link"][0](physicalLayer)
        self.cmdProto = self.protos["command"][0]

        # Now we set up 'links' through which we can get data of the
        # appropriate types

        # ex. self.commando = TransferProtocol(A010,L001)
        # This is for sending simple commando's
        # Like aborting the transfer, turn gps out, ..

        self.command = TransferProtocol(self.link, self.cmdProto )

        # ex. self.wptLink = A100(L001,A010,D109)
        if self.protos.has_key("waypoint"):
            self.wptLink = self.protos["waypoint"][0](
                self.link, self.cmdProto,self.protos["waypoint"][1])

        # ex. self.rteLink = A201(LOO1,AO10,(D202,D109,D210)
        if self.protos.has_key("route"):
            self.rteLink = self.protos["route"][0](
                self.link, self.cmdProto,self.protos["route"][1:])

        # ex. self.trkLink = A301(LOO1,AO10,(D310,D301))
        if self.protos.has_key("track"):
            self.trkLink = self.protos["track"][0](
                self.link, self.cmdProto,self.protos["track"][1:])

        # ex. self.prxLink = A400(LOO1,A010,D109)
        if self.protos.has_key("proximity"):
            self.prxLink = self.protos["proximity"][0](
                self.link, self.cmdProto,self.protos["proximity"][1])

        # self.timeLink = A500(L001,A010,D501)
        if self.protos.has_key("almanac"):
            self.almLink = self.protos["almanac"][0](
                self.link, self.cmdProto,self.protos["almanac"][1])

        # self.timeLink = A600(LOO1,A010,D600)
        if self.protos.has_key("data_time"):
            self.timeLink = self.protos["data_time"][0](
                self.link, self.cmdProto,self.protos["data_time"][1])

        # self.flightBook = A650(L001,A010,D650)
        if self.protos.has_key("flightbook"):
            self.flightBook = self.protos["flightbook"][0](
                self.link, self.cmdProto,self.protos["flightbook"][1])

        # Sorry, no link for A700

        # self.pvtLink = A800(self.link, self.cmdProto, D800)
        if self.protos.has_key("pvt"):
            self.pvtLink  = self.protos["pvt"][0](
                self.link, self.cmdProto,self.protos["pvt"][1])

        # self lapLink = A906(self.link, self.cmdProto,D906)
        if self.protos.has_key("lap"):
            self.lapLink = self.protos["lap"][0](
                self.link, self.cmdProto,self.protos["lap"][1])

        runProtos = self.protos.get("run", [])
        self.runTypes = runProtos[1:]
        if runProtos:
            self.runLink = runProtos[0](
                self.link, self.cmdProto, self.runTypes)
        else:
            self.runLink = None

    def getWaypoints(self,callback = None):
        return self.wptLink.getData(callback)

    def putWaypoints(self,data,callback = None):
        return self.wptLink.putData(data,callback)

    def getRoutes(self,callback = None):
        return self.rteLink.getData(callback)

    def putRoutes(self,data,callback = None):
        return self.rteLink.putData(data,callback)

    def getTracks(self,callback = None):
        return self.trkLink.getData(callback)

    def putTracks(self,data,callback = None):
        return self.trkLink.putData(data,callback)

    def getLaps(self, callback=None):
        assert self.lapLink is not None, (
            "No lap protocol specified for this GPS.")
        return self.lapLink.getData(callback)

    def getRuns(self, callback=None):
        assert self.runLink is not None, (
            "No run protocol supported for this GPS.")
        return self.runLink.getData(callback)

    def getProxPoints(self, callback = None):
        return self.prxLink.getData(callback)

    def putProxPoints(self,data,callback = None):
        return self.prxLink.putData(data,callback)

    def getAlmanac(self,callback = None):
        return self.almLink.getData(callback)

    def getTime(self,callback = None):
        return self.timeLink.getData(callback)

    def getFlightBook(self,callback = None):
        return self.flightBook.getData(callback)

    def pvtOn(self):
        return self.pvtLink.dataOn()

    def pvtOff(self):
        return self.pvtLink.dataOff()

    def getPvt(self,callback = None):
        return self.pvtLink.getData(callback)

    def abortTransfer(self):
        return self.command.abortTransfer()

    def turnPowerOff(self):
        return self.command.turnPowerOff()


# Callback examples functions

def MyCallbackgetWaypoints(waypoint,recordnumber,totalWaypointsToGet,tp):
    # We get a tuple back (waypoint,recordnumber,totalWaypointsToGet)
    # tp is the commando to send/get from the gps, look at the docs (Garmin GPS Interface Specification)
    # pag 9,10 or 4.2 L001 and L002 link Protocol

    print "---  waypoint ", " %s / %s " % (recordnumber,totalWaypointsToGet), "---"

    print "str output --> ",waypoint # or repr(waypoint)
    print

    if recordnumber != totalWaypointsToGet:
        print "directory output : --> ", waypoint.getDict() # or waypoint.dataDict
    else:
        print
        print "This is the last waypoint :"
        print

        for x in waypoint.dataDict:
            print x, " --> ",waypoint.dataDict[x]

    print "Commando :",tp
    print


def MyCallbackputWaypoints(waypoint,recordnumber,totalWaypointsToSend,tp):
    # we get a tuple waypoint,recordnumber,totalWaypointsToSend,tp

    print "waypoint %s added to gps (total waypoint(s) : %s/%s) waypoint command : %s" % (waypoint.dataDict['ident'],recordnumber,totalWaypointsToSend,tp)


def MyCallbackgetRoutes(point,recordnumber,totalpointsToGet,tp):

    #print point.__class__

    if isinstance(point,(RouteHdr)):
        print "Route : ", point

    # I really don't want the D210_Rte_Link_Type

    elif not isinstance(point,RouteLink):

        if recordnumber != totalpointsToGet:
            print "   ", point
        else:
            print
            print "This is the last waypoint of a route:"

            for x in point.dataDict: # or point.getDict()
                print x, " --> ",point.dataDict[x]


def MyCallbackputRoutes(point,recordnumber,totalPointsToSend,tp):

    if isinstance(point,RouteHdr):
        print
        print "Adding route :",point
    elif not isinstance(point,RouteLink):
        print "   waypoint added",point.dataDict['ident']


def MyCallbackgetTracks(point,recordnumber,totalPointsToGet,tp):

    if isinstance(point,TrackHdr):
        print "Track :",point
    else:

        if recordnumber != totalPointsToGet:

            print "   ",point,

            if point.dataDict['new_trk'] == True:
                print "(New track segment)",

            print

        else:
            print
            print "This is the last waypoint of a track:"

            for x in point.dataDict:
                print x, " --> ",point.dataDict[x]

            print "Time are the seconds since midnight 31/12/89 and are only correct for the ACTIVE LOG !! (hmmm...)"


def MyCallbackputTracks(point,recordnumber,totalPointsToSend,tp):

    if isinstance(point,TrackHdr):
        print "Track :", point
    else:
        print "   ", point.dataDict


def MyCallbackgetAlmanac(satellite,recordnumber,totalPointsToGet,tp):

    print

    for x in satellite.dataDict:
        print "%7s --> %s" % (x,satellite.dataDict[x])


# =================================================================
# The following is test code. See other included files for more
# useful applications.

def main():

    if os.name == 'nt':
        #0 is com1, 1 is com2 etc
        serialDevice =  0
    else:
        serialDevice =  "/dev/ttyS0"

        if sys.platform[:-1] == "freebsd":
            serialDevice =  "/dev/cuaa0" # For FreeBsd

    phys = SerialLink(serialDevice)

    gps = Garmin(phys)

    print "GPS Product ID: %d Descriptions: %s Software version: %2.2f" % \
                             (gps.prod_id, gps.prod_descs, gps.soft_ver)
    print

    # Show gps information

    if 1:
        print
        print "GPS Product ID :",gps.prod_id
        print "GPS version    :",gps.soft_ver
        print "GPS            :",gps.prod_descs[0]
        print "MapSource info :",gps.prod_descs[1:]
        print
        print "Product protocols:"
        print "------------------"

        # Some code from pygarmin, small but smart

        for i in range(len(gps.protocols)):
            p = gps.protocols[i]

            if  p[0] == 'D':
                print p,
            else:
                if i == 0:
                    print p,
                else:
                    print
                    print p,

        print

        # print unknown protocols

        if len(gps.protocols_unknown):
            print
            print "Product protocols who are not supported yet:"
            print "--------------------------------------------"

            for i in range(len(gps.protocols_unknown)):
                p = gps.protocols_unknown[i]

                if  p[0] == 'D':
                    print p,
                else:
                    if i == 0:
                        print p,
                    else:
                        print
                        print p,

            print

    # Show waypoints

    if 0:

        # First method, just get the waypoints in a list (look at class A100, function __str__)

        waypoints = gps.getWaypoints()

        print "Waypoints :"
        print "-----------"

        for x in waypoints:
            print x

        print
        print   "Same waypoints called by a callback function:"
        print "---------------------------------------------"
        print

        # Same but now with a Callback function
        # Everytime we get a waypoint from the gps the function MyCallbackWaypoints is called

        gps.getWaypoints(MyCallbackgetWaypoints)

        # or waypoints = gps.getWaypoints(MyCallbackgetWaypoints)

    # Send waypoints

    if 0:
        data1 = {}
        data1['ident'] = "01TEST"
        data1['cmnt'] = "A TEST POINT"
        data1['slat'] = 624447295
        data1['slon'] = -2529985

        data2 = {}
        data2['ident'] = "02TEST"
        data2['cmnt'] ="A TEST POINT"
        data2['slat'] = 624447295
        data2['slon']= -2529985

        data3 = {'ident':"CLUB91",'cmnt':"DRINKING",'slat':606532864,'slon':57654672,'smbl':13}

        print "Send waypoints to gps :"
        print "----------------------"

        gps.putWaypoints([data1,data2,data3],MyCallbackputWaypoints)

        # or gps.putWaypoints([data1,data2]) without a callback function

        print
        print "Are there 3 waypoints added to your gps ??"


    # Show Routes

    if 0:

        routes = gps.getRoutes()

        print "Routes"
        print "------"

        for route in routes:
            print
            print "Route name :", route[0]

            for point in route[1:]:

                # Ok, Bad way to remove D210_Rte_Link_Type entrys

                if len(point) > 23:
                    print "   ",point

        # Now with a callback function

        print
        print "Same routes but now with a callback function :"
        print "---------------------------------------------"
        print

        gps.getRoutes(MyCallbackgetRoutes)

    # Put Routes

    if 0:

        # Test Route 1

        header1 = {'nmbr':1,'ident':"DRINKING"}

        data1_1 = {}
        data1_1['ident'] = "SOCCER"
        data1_1['cmnt'] = "MY SOCCER"
        data1_1['slat'] = 606476436
        data1_1['slon'] = 57972861

        data2_1 = {}
        data2_1['ident'] = "CLUB91"
        data2_1['cmnt'] = "DRINKING"
        data2_1['slat'] = 606532864
        data2_1['slon'] = 57654672

        # Test Route 2

        header2 = {'nmbr':2,'ident':"TEST ROUTE 2"}

        data1_2 = {}
        data1_2['ident'] = "TEST01"
        data1_2['slat'] = 608466698
        data1_2['slon'] = 46580036

        data2_2 = {'ident': "TEST02",'slat': 608479774,'slon':46650547}
        data3_2 = {'ident': "TEST03",'slat': 608451909,'slon':46665535}
        data4_2 = {'ident': "TEST04",'slat': 608440119,'slon':46644415}

        print "Send two routes to the gps"
        gps.putRoutes([(header1,data1_1,data2_1),(header2,data1_2,data2_2,data3_2,data4_2)])
        print "Routes added"

        # Now with a callback function

        print
        print "Same routes but now with a callback function :"
        print "---------------------------------------------"
        print "If you leave the header empty, the computer will generate one for you (ROUTE1,ROUTE2,....)"

        header1 = header2 = {}

        gps.putRoutes([(header1,data1_1,data2_1),(header2,data1_2,data2_2,data3_2,data4_2)],MyCallbackputRoutes)

        print
        print "Four routes are added to your gps, two of them are generated !"
        print "and a few waypoints"

    # Show Tracks

    if 0:
        print "Tracks"
        print "------"

        tracks = gps.getTracks()

        for track in tracks:

            # Check for multiple tracks

            if type(track) == list:
                print
                print "Track name :",track[0]

                for point in track[1:]:
                    print "   ",point
            else:
                print track

        # Now with a callback function

        print
        print "Same tracks but now with a callback function :"
        print "---------------------------------------------"

        gps.getTracks(MyCallbackgetTracks)

    # Send tracks

    if 0:
        print "Sending tracks with a callback function :"
        print "-----------------------------------------"
        print "If you leave the header empty, the computer will generate one for you (TRACK1,TRACK2,....)"
        print "It's possible to send track to the ACTIVE LOG.but you can't send time to tracks"


        header1 = {'ident':'TEST TRACK'}
        #header1 = {'ident':'ACTIVE LOG'}  # for sending track's to the ACTIVE LOG
        data1_1 = {'slat': 608528384,'slon': 46271488}
        data2_1 = {'slat': 608531200,'slon': 46260224}
        data3_1 = {'slat': 608529664, 'slon': 46262272}

        header2 = {}
        data1_2 = {'slat': 608529718,'slon': 46262291}
        data2_2 = {'slat': 608529718,'slon': 46262291}
        data3_2 = {'slat': 608532699,'slon': 46250150, 'new_trk': True}
        data4_2 = {'slat': 608526491,'slon': 46257149}
        data5_2 = {'slat': 608520439,'slon': 46264816}
        data6_2 = {'slat': 608521779,'slon': 46262842}

        # Check if we can store multiple tracklogs

        if isinstance(gps.trkLink,A300):
            gps.putTracks([(data1_1,data2_1,data3_1),
                                                                     (data1_2,data2_2,data3_2,data4_2,data5_2,data6_2)],MyCallbackputTracks)

            print "Track added ?"

        else:
            gps.putTracks([(header1,data1_1,data2_1,data3_1),
                                                                     (header2,data1_2,data2_2,data3_2,
                                                                      data4_2,data5_2,data6_2)],MyCallbackputTracks)

            print "Two track logs added ?"

    # Show proximity points

    if 0:
        print "Proximity waypoints:"
        print "-------------------"

        for proxi in gps.getProxPoints():
            print proxi

    # Send  proximity points

    if 0:
        print "Sending 2 proximity waypoints :"
        print "-------------------------------"

        data1 = {'ident':'WATER','slat': 608688816,'slon': 45891108,'dist':300}
        data2 = {'ident':'AERPRT','slat': 607132209,'slon': 53673984,'dist':400}
        gps.putProxPoints([data1,data2])

        print "Check your waypoint and proximity waypoint menu on your gps!"

    # Show almanac

    if 0:
        print "Almanac information:"
        print "--------------------"

        gps.getAlmanac(MyCallbackgetAlmanac)

    # Show FlightBook

    if 0:
        print "FlightBook information:"
        print "-----------------------"

        flightbook = gps.getFlightBook()

        for x in flightbook:
            print x

    # Show date and time

    if 0:
        print "Date and time:"
        print "--------------"

        def MyCallbackgetTime(timeInfo,recordnumber,totalPointsToGet,tp):
            print timeInfo.getDict() # or timeInfo.dataDict

        print gps.getTime(MyCallbackgetTime)

    # Show some real-time data

    if 0:
        print "Starting pvt"
        print "-----------"

        gps.pvtOn()

        def MyCallbackgetPvt(pvt,recordnumber,totalPointsToGet,tp):
            print pvt.getDict()

        try:
            for i in range(10):
                p = gps.getPvt(MyCallbackgetPvt)
                print p

        finally:
            print "Stopping pvt"
            gps.pvtOff()

    # Show Lap type info

    if 0:
        print "Lap info"
        print "--------"

        laps = gps.getLaps()

        for x in laps:
            print x


if __name__ == "__main__":
    main()
