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

import os
import sys
import time
import struct
import newstruct
import math
import logging


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


# The following is handy for debugging:

def hexdump(data):
    if isinstance(data, int):
        data = newstruct.pack('<H', data)
    return ''.join(["%02x" % x for x in data])


# Define Errors

class GarminException(Exception):

    def __init__(self, data):
        self.data = data


class LinkException(GarminException):
    """Link error."""

    def __str__(self):
        return "Link Error"


class ProtocolException(GarminException):
    """Protocol error."""

    def __str__(self):
        return "Protocol Error"



class P000:
    """Physical layer for communicating with Garmin."""

    def read(self):
        pass

    def write(self, data):
        pass

# Link protocols ===================================================

class L000:
    """Basic Link Protocol."""

    Pid_Protocol_Array = 253  # may not be implemented in all devices
    Pid_Product_Rqst = 254
    Pid_Product_Data = 255
    Pid_Ext_Product_Data = 248  # may not be implemented in all devices

    def __init__(self, physicalLayer):
        self.phys = physicalLayer

    def sendPacket(self, packet_id, data):
        """Send a packet."""
        self.phys.sendPacket(packet_id, data)
        log.debug("< packet %s: %s" % (packet_id, data))

    def readPacket(self):
        """Read a packet."""
        while True:
            packet = self.phys.readPacket()
            log.debug("> packet %3d: %s" % (packet['id'], hexdump(packet['data'])))
            if packet['id'] == self.Pid_Ext_Product_Data:
                # The Ext_Product_Data_Type contains zero or more null-terminated
                # strings that are used during manufacturing to identify other
                # properties of the device and are not formatted for display to the
                # end user. According to the specification the host should ignore
                # it.
                log.debug(f"Got packet type {self.Pid_Ext_Product_Data}, ignoring...")
            else:
                break

        return packet

    def expectPacket(self, packet_id):
        "Expect and read a particular packet type. Return data."
        packet = self.readPacket()
        if packet['id'] != packet_id:
            raise ProtocolException(f"Expected {packet_id}, got {packet['id']}")

        return packet


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
    Pid_FlightBook_Record = 134  # packet with FlightBook data
    Pid_Lap = 149  # part of Forerunner data
    Pid_Wpt_Cat = 152
    Pid_Run = 990
    Pid_Workout = 991
    Pid_Workout_Occurrence = 992
    Pid_Fitness_User_Profile = 993
    Pid_Workout_Limits = 994
    Pid_Course = 1061
    Pid_Course_Lap = 1062
    Pid_Course_Point = 1063
    Pid_Course_Trk_Hdr = 1064
    Pid_Course_Trk_Data = 1065
    Pid_Course_Limits = 1066
    Pid_External_Time_Sync_Data = 6724

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
        """
        Packet 0 (Pid_Product_Rqst) is a special product request packet that is sent
        to the device. Packet 1 (Pid_Product_Data) is returned to the host and
        contains data to identify the device, which is provided in the data type
        Product_Data_Type.

        """
        log.info("Request Product Data")
        self.link.sendPacket(self.link.Pid_Product_Rqst, None)
        log.info("Expect Product_Data packet")
        packet = self.link.expectPacket(self.link.Pid_Product_Data)
        # The format of the Product_Data_Type is:
        # - unsigned short: product_id
        # - signed short: software_version
        # - char[]: product_description; zero or more additional null-terminated strings
        size = len(packet['data']) - struct.calcsize('<Hh')
        fmt = f'<Hh{size}s'
        product_id, software_version, product_description = struct.unpack(fmt, packet['data'])

        product_description = [x.decode('ascii') for x in product_description.split(b'\x00')]
        product_description.pop()  # remove the last empty byte

        return {'id': product_id,
                'version': software_version / 100,
                'description': product_description}


class A001:
    """Protocol capabilities protocol."""
    Tag_Phys_Prot_Id = 'P'  # Physical protocol ID
    Tag_Link_Prot_Id = 'L'  # Link protocol ID
    Tag_Appl_Prot_Id = 'A'  # Application protocol ID
    Tag_Data_Type_Id = 'D'  # Data Type ID

    def __init__(self, linkLayer):
        self.link = linkLayer

    def getProtocols(self):

        log.info("Read protocols using Protocol Capability Protocol")

        packet = self.link.expectPacket(self.link.Pid_Protocol_Array)
        # The packet data contains an array of Protocol_Data_Type structures,
        # each of which contains tag-encoded protocol information. The
        # Protocol_Data_Type is comprised of a one-byte tag field and a two-byte
        # data field. The tag identifies which kind of ID is contained in the
        # data field, and the data field contains the actual ID.
        # The format of the Protocol_Data_Type is:
        # - unsigned char: tag
        # - unsigned short: data
        fmt = '<BH'
        size = struct.calcsize(fmt)
        count = len(packet['data']) // size
        fmt = '<' + count * 'BH'
        # Unpack data to a list of tag+number pairs
        records = struct.unpack(fmt, packet['data'])
        # The order of array elements is used to associate data types with
        # protocols. For example, a protocol that requires two data types <D0>
        # and <D1> is indicated by a tag-encoded protocol ID followed by two
        # tag-encoded data type IDs, where the first data type ID identifies
        # <D0> and the second data type ID identifies <D1>.
        protocols = []
        log.info(f"Parse supported protocols and datatypes...")
        for i in range(0, len(records), 2):
            tag = chr(records[i])
            number = records[i+1]
            # Format the record to a string consisting of the tag and 3-digit number
            protocol_datatype = f"{tag}{number:03}"
            # Create a list of lists with supported protocols and associated datatypes
            if tag == self.Tag_Phys_Prot_Id:
                # We ignore the physical protocol, because it is initialized
                # already
                log.info(f"Ignore physical protocol '{protocol_datatype}'.")
            elif tag == self.Tag_Link_Prot_Id:
                # Append new list with protocol.
                log.info(f"Add link protocol '{protocol_datatype}'.")
                protocols.append([protocol_datatype])
            elif tag == self.Tag_Appl_Prot_Id:
                # Append new list with protocol.
                log.info(f"Add application protocol '{protocol_datatype}'.")
                protocols.append([protocol_datatype])
            elif tag == self.Tag_Data_Type_Id:
                # Append datatype to list of previous protocol
                log.info(f"Add datatype '{protocol_datatype}'.")
                protocols[-1].append(protocol_datatype)
            else:
                log.info(f"Ignore unknown protocol or datatype '{protocol_datatype}'.")
        log.info(f"Supported protocols and data types: {protocols}")

        return protocols

    def getProtocolsNoPCP(self, product_id, software_version):
        try:
            model = ModelProtocols[product_id]
            log.info(f"Got product ID number {product_id}")
        except:
            raise ValueError(f"Unknown product ID number {product_id}")

        try:
            for capabilities in model:
                version = capabilities[0]
                if version is None:
                    break
                elif (software_version >= version[0] and software_version < version[1]):
                    break
        except:
            raise ValueError(f"Unknown software version number {software_version}")

        protocols = [protocol for protocol in capabilities[1:] if protocol]
        protocols.append(("A600", "D600"))
        protocols.append(("A700", "D700"))
        log.info(f"Supported protocols and data types: {protocols}")

        return protocols









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

    def __init__(self, link, cmdproto, datatypes=None):
        self.link = link
        self.cmdproto = cmdproto

        if isinstance(datatypes, list):
            self.datatypes = datatypes
        else:
            self.datatypes = (datatypes,)

    def putData(self, callback, cmd, sendData):

        numrecords = len(sendData)
        x = 0

        log.log(
            VERBOSE, "%s: Sending %d records" % (self.__doc__, numrecords))

        self.link.sendPacket(self.link.Pid_Records, numrecords)

        for packet_id, data in sendData:
            log.debug('packet_id: %s, data: %s' % (repr(packet_id), repr(data)))
            self.link.sendPacket(packet_id, data.pack())

            if callback:
                try:
                    x += 1
                    callback(data, x, numrecords, packet_id)
                except:
                    raise

        self.link.sendPacket(self.link.Pid_Xfer_Cmplt, cmd)

    def abortTransfer(self):
        self.link.sendPacket(
            self.link.Pid_Command_Data, self.cmdproto.Cmnd_Abort_Transfer)

    def turnPowerOff(self):
        self.link.sendPacket(
            self.link.Pid_Command_Data, self.cmdproto.Cmnd_Turn_Off_Pwr)


class SingleTransferProtocol(TransferProtocol):

    def getData(self, callback, cmd, pid):
        self.link.sendPacket(self.link.Pid_Command_Data, cmd)

        log.log(
            VERBOSE, "%s: Expecting %d records" % (self.__doc__, numrecords))
        packet = self.link.expectPacket(self.link.Pid_Records)
        numrecords = int.from_bytes(packet['data'], byteorder='little')

        result = []

        for i in range(numrecords):
            packet = self.link.expectPacket(pid)
            p = self.datatypes[0]()
            p.unpack(packet['data'])
            result.append(p)

            if callback:
                try:
                    callback(p, i+1, numrecords, pid)
                except:
                    raise

        self.link.expectPacket(self.link.Pid_Xfer_Cmplt)
        return result


class MultiTransferProtocol(TransferProtocol):

    def getData(self, callback, cmd, hdr_pid, *data_pids):

        self.link.sendPacket(self.link.Pid_Command_Data, cmd)

        packet = self.link.expectPacket(self.link.Pid_Records)
        numrecords = int.from_bytes(packet['data'], byteorder='little')

        log.log(
            VERBOSE, "%s: Expecting %d records" % (self.__doc__, numrecords))

        data_pids = list(data_pids)
        result = []
        last = []

        for i in range(numrecords):
            packet = self.link.readPacket()

            if packet['id'] == hdr_pid:

                if last:
                    result.append(last)
                    last = []

                index = 0
            else:
                try:
                    index = data_pids.index(packet['id']) + 1
                except ValueError:
                    raise ProtocolException("Expected header or point")

            p = self.datatypes[index]()
            p.unpack(packet['data'])
            last.append(p)

            if callback:
                try:
                    callback(p, i + 1, numrecords, packet['id'])
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

    def getData(self, callback=None):
        return SingleTransferProtocol.getData(self, callback,
                                              self.cmdproto.Cmnd_Transfer_Wpt,
                                              self.link.Pid_Wpt_Data)

    def putData(self, data, callback):
        sendData = []

        log.debug('self.datatypes: %s' % repr(self.datatypes))
        for waypoint in data:
            waypointInstance = self.datatypes[0](**waypoint)
            sendData.append((self.link.Pid_Wpt_Data, waypointInstance))

        return SingleTransferProtocol.putData(
            self, callback, self.cmdproto.Cmnd_Transfer_Wpt, sendData)


class A101(SingleTransferProtocol):
    """Waypoint transfer protocol."""

    def getData(self, callback=None):
        return SingleTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Wpt_Cats,
            self.link.Pid_Wpt_Cat)


class A200(MultiTransferProtocol):
    """Route transfer protocol."""

    def getData(self, callback=None):
        return MultiTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Rte,
            self.link.Pid_Rte_Hdr, self.link.Pid_Rte_Wpt_Data)

    def putData(self, data, callback):
        sendData = []
        header = {}
        routenr = 0

        for route in data:
            routenr += 1

            # Copy the header fields
            header = {}
            for head in list(route[0].keys()):
                header[head] = route[0][head]

            # Give a routenr
            if 'nmbr' not in header:
                header['nmbr'] = routenr

            # Check route names
            # if no name, give it a name
            if 'ident' not in header or 'cmnt' not in header:

                if 'ident' in header:
                    header['cmnt'] = header['ident']
                elif 'cmnt' in header:
                    header['ident'] = header['cmnt']
                else:
                    header['ident'] = header['cmnt'] = "ROUTE " + str(routenr)

            headerInstance = self.datatypes[0](header)
            sendData.append((self.link.Pid_Rte_Hdr, headerInstance))

            for waypoint in route[1:]:
                waypointInstance = self.datatypes[1](waypoint)
                sendData.append((self.link.Pid_Rte_Wpt_Data, waypointInstance))

        return MultiTransferProtocol.putData(
            self, callback, self.cmdproto.Cmnd_Transfer_Rte, sendData)


class A201(MultiTransferProtocol):
    """Route transfer protocol."""

    def getData(self, callback=None):
        return MultiTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Rte,
            self.link.Pid_Rte_Hdr, self.link.Pid_Rte_Wpt_Data,
            self.link.Pid_Rte_Link_Data)

    def putData(self, data, callback):
        sendData = []
        header = {}
        routenr = 0

        for route in data:
            routenr += 1

            # Copy the header fields
            header = {}
            for head in list(route[0].keys()):
                header[head] = route[0][head]

            # Give a routenr
            if 'nmbr' not in header:
                header['nmbr'] = routenr

            headerInstance = self.datatypes[0]()

            # Check route names
            # if no name, give it a name
            if 'ident' not in header or 'cmnt' not in header:
                if 'ident' in header:
                    headerInstance.ident = header['ident']
                elif 'cmnt' in header:
                    headerInstance.cmnt = header['cmnt']
                else:
                    headerInstance.ident = f"Route {routenr}"

            sendData.append((self.link.Pid_Rte_Hdr, headerInstance))

            for waypoint in route[1:]:
                waypointInstance = self.datatypes[1]()
                waypointInstance.ident = waypoint['ident']
                waypointInstance.slon = waypoint['slon']
                waypointInstance.slat = waypoint['slat']
                linkInstance = self.datatypes[2]()
                sendData.append((self.link.Pid_Rte_Wpt_Data, waypointInstance))
                # sendData.append((self.link.Pid_Rte_Link_Data, linkInstance))

        return MultiTransferProtocol.putData(
            self, callback, self.cmdproto.Cmnd_Transfer_Rte, sendData)


class A300(SingleTransferProtocol):
    """Track log transfer protocol."""

    def getData(self, callback=None):
        return SingleTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Trk,
            self.link.Pid_Trk_Data)

    def putData(self, data, callback):
        sendData = []

        for waypoint in data:
            waypointInstance = self.datatypes[0](waypoint)
            sendData.append((self.link.Pid_Trk_Data, waypointInstance))

        return SingleTransferProtocol.putData(
            self, callback, self.cmdproto.Cmnd_Transfer_Trk, sendData)


class A301(MultiTransferProtocol):
    """Track log transfer protocol."""

    def getData(self, callback=None):
        return MultiTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Trk,
            self.link.Pid_Trk_Hdr, self.link.Pid_Trk_Data)

    def putData(self, data, callback):
        sendData = []
        header = {}

        for tracknr, track in enumerate(data, start=1):

            # Copy the header fields
            header = {}
            for head in list(track[0].keys()):
                header[head] = track[0][head]

            headerInstance = self.datatypes[0]()
            # Check track names
            # if no name, give it a name
            headerInstance.trk_ident = track[0].get('ident', f'TRACK{tracknr}')
            sendData.append((self.link.Pid_Trk_Hdr, headerInstance))

            firstSegment = True

            for waypoint in track[1:]:
                trackPointInstance = self.datatypes[1]()
                trackPointInstance.slat = waypoint['slat']
                trackPointInstance.slon = waypoint['slon']

                # First point in a track is always a new track segment
                if firstSegment:
                    trackPointInstance.new_trk = True
                    firstSegment = False

                sendData.append((self.link.Pid_Trk_Data, trackPointInstance))

        return MultiTransferProtocol.putData(
            self, callback, self.cmdproto.Cmnd_Transfer_Trk, sendData)


class A302(A301):
    """Track log transfer protocol."""


class A400(SingleTransferProtocol):
    """Proximity waypoint transfer protocol."""

    def getData(self, callback=None):
        return SingleTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Prx,
            self.link.Pid_Prx_Wpt_Data)

    def putData(self, data, callback):
        sendData = []

        for waypoint in data:
            waypointInstance = self.datatypes[0](waypoint)
            sendData.append((self.link.Pid_Prx_Wpt_Data, waypointInstance))

        return SingleTransferProtocol.putData(
            self, callback, self.cmdproto.Cmnd_Transfer_Prx, sendData)


class A500(SingleTransferProtocol):
    """Almanac transfer protocol."""

    def getData(self, callback):
        return SingleTransferProtocol.getData(
            self, callback, self.cmdproto.Cmnd_Transfer_Alm,
            self.link.Pid_Almanac_Data)


class A600(TransferProtocol):
    """Waypoint date & time initialization protocol."""

    def getData(self, callback):
        self.link.sendPacket(
            self.link.Pid_Command_Data, self.cmdproto.Cmnd_Transfer_Time)
        packet = self.link.expectPacket(self.link.Pid_Date_Time_Data)
        p = self.datatypes[0]()
        p.unpack(packet['data'])

        if callback:
            try:
                callback(p, 1, 1, self.link.Pid_Command_Data)
            except:
                raise

        return p


class A601(TransferProtocol):
    """A601 implementaion.

    Used by GPSmap 60cs, no specifications as of 2004-09-26."""


class A650(SingleTransferProtocol):
    """FlightBook transfer protocol."""

    def getData(self, callback):
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

    def getData(self, callback):
        packet = self.link.readPacket()

        p = self.datatypes[0]()
        p.unpack(packet['data'])

        if callback:

            try:
                callback(p, 1, 1, packet['id'])
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

    def getData(self, callback):
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

class Data_Type:

    parts = ()
    fmt = ""

    # Generic serialization stuff. If this looks complex, try it in
    # any other language!
    def pack(self):
        arg = (self.fmt,)
        log.debug('self.parts: %s' % repr(self.parts))
        for i in self.parts:
            log.debug('checking part %s' % repr(i))
            try:
                # I imagine this is faster, but it only works
                # if attribute 'i' has been assigned to. Otherwise
                # it's only in the class, not in the instance.
                v = self.__dict__[i]
            except KeyError:
                v = eval('self.'+i)
            arg = arg + (v,)
            log.debug('got value %s' % repr(v))
        log.debug('arg: %s' % repr(arg))
        return newstruct.pack(*arg)

    def unpack(self, bytes):
        # print newstruct.calcsize(self.fmt), self.fmt
        # print len(bytes), repr(bytes)
        try:
            bits = newstruct.unpack(self.fmt, bytes)
            for i in range(len(self.parts)):
                self.__dict__[self.parts[i]] = bits[i]
        except Exception as e:
            print(e)
            print("Format: <" + self.fmt + ">")
            print("Parts:  <" + ", ".join(self.parts) + ">")
            print("Input:  <" + "><".join(bytes) + ">")
            raise


# Waypoints  ---------------------------------------------------

# Different products store different info in their waypoints
# Internally, waypoints store latitude and longitude in 'semicircle'
# coordinates. Here's the conversion:

def degrees(semi):
    return semi * 180.0 / (1 << 31)


def semi(deg):
    return int(deg * ((1 << 31) / 180))


def radian(semi):
    return semi * math.pi / (1 << 31)


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
    a = (math.pow(math.sin(dlat/2), 2)
         + math.cos(rlat1)
         * math.cos(rlat2)
         * math.pow(math.sin(dlon/2), 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R*c


class Wpt_Type(Data_Type):

    parts = ("ident", "slat", "slon", "unused", "cmnt")
    fmt = "< 6s l l L 40s"

    def __init__(self, ident="", slat=0, slon=0, cmnt=""):
        self.ident = ident         # text identidier (upper case)
        self.slat = slat           # lat & long in semicircle terms
        self.slon = slon
        self.cmnt = cmnt           # comment (must be upper case)
        self.unused = 0

    def __repr__(self):
        return "<Wpt_Type %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
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


class D100(Wpt_Type):
    pass


class D101(Wpt_Type):

    parts = Wpt_Type.parts + ("dst", "smbl")
    fmt = "< 6s l l L 40s f b"
    dst = 0.0                  # proximity distance (m)
    smbl = 0                   # symbol_type id (0-255)

    def __init__(self, ident="", slat=0, slon=0, cmnt="", dst=0, smbl=0):
        self.ident = ident         # text identidier (upper case)
        self.slat = slat           # lat & long in semicircle terms
        self.slon = slon
        self.cmnt = cmnt           # comment (must be upper case)
        self.unused = 0
        self.dst = dst
        self.smbl = smbl
        self.data = {}

    def __repr__(self):
        return "<Wpt_Type %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
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


class D102(Wpt_Type):

    parts = Wpt_Type.parts + ("dst", "smbl")
    fmt = "< 6s l l L 40s f h"
    dst = 0.0                  # proximity distance (m)
    smbl = 0                   # symbol_type id

    def __init__(self, ident="", slat=0, slon=0, cmnt="", dst=0, smbl=0):
        self.ident = ident         # text identidier (upper case)
        self.slat = slat           # lat & long in semicircle terms
        self.slon = slon
        self.cmnt = cmnt           # comment (must be upper case)
        self.unused = 0
        self.dst = dst
        self.smbl = smbl
        self.data = {}

    def __repr__(self):
        return "<Wpt_Type %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
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


class D103(Wpt_Type):

    parts = Wpt_Type.parts + ("smbl", "dspl")
    fmt = "<6s l l L 40s b b"
    smbl = 0                   # D103 symbol id
    dspl = 0                   # D103 display option

    def __init__(self, ident="", slat=0, slon=0, cmnt="", dspl=0, smbl=0):
        self.ident = ident         # text identidier (upper case)
        self.slat = slat           # lat & long in semicircle terms
        self.slon = slon
        self.cmnt = cmnt           # comment (must be upper case)
        self.unused = 0
        self.dspl = dspl
        self.smbl = smbl
        self.data = {}

    def __repr__(self):
        return "<Wpt_Type %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
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


class D104(Wpt_Type):

    parts = Wpt_Type.parts + ("dst", "smbl", "dspl")
    fmt = "<6s l l L 40s f h b"
    dst = 0.0                  # proximity distance (m)
    smbl = 0                   # symbol_type id
    dspl = 0                   # D104 display option

    def __init__(self, ident="", slat=0, slon=0, cmnt="",
                 dst=0, smbl=0, dspl=0):
        self.ident = ident         # text identidier (upper case)
        self.slat = slat           # lat & long in semicircle terms
        self.slon = slon
        self.cmnt = cmnt           # comment (must be upper case)
        self.unused = 0
        self.dst = dst             # proximity distance (m)
        self.smbl = smbl           # symbol_type id
        self.dspl = dspl           # D104 display option

    def __repr__(self):
        return "<Wpt_Type %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
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


class D105(Wpt_Type):

    parts = ("slat", "slon", "smbl", "ident")
    fmt = "<l l h s"
    smbl = 0

    def __init__(self, ident="", slat=0, slon=0, smbl=0):
        self.ident = ident         # text identidier (upper case)
        self.slat = slat           # lat & long in semicircle terms
        self.slon = slon
        self.unused = 0
        self.smbl = smbl

    def __repr__(self):
        return "<Wpt_Type %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
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


class D106(Wpt_Type):

    parts = ("wpt_class", "subclass", "slat", "slon", "smbl",
             "ident", "lnk_ident")
    fmt = "<b 13s l l h s s"
    wpt_class = 0
    subclass = ""
    smbl = 0
    lnk_ident = ""

    def __init__(self, ident="", slat=0, slon=0, subclass="",
                 wpt_class=0, lnk_ident="", smbl=0):
        self.ident = ident         # text identidier (upper case)
        self.slat = slat           # lat & long in semicircle terms
        self.slon = slon
        self.wpt_class = wpt_class
        self.unused = 0
        self.subclass = subclass
        self.lnk_ident = lnk_ident
        self.smbl = smbl

    def __repr__(self):
        return "<Wpt_Type %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
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


class D107(Wpt_Type):

    parts = Wpt_Type.parts + ("smbl", "dspl", "dst", "color")
    fmt = "<6s l l L 40s b b f b"
    smbl = 0                   # D103 symbol id
    dspl = 0                   # D103 display option
    dst = 0.0
    color = 0

    def __init__(self, ident="", slat=0, slon=0, cmnt="",
                 dst=0, smbl=0, dspl=0, color=0):
        self.ident = ident         # text identidier (upper case)
        self.slat = slat           # lat & long in semicircle terms
        self.slon = slon
        self.cmnt = cmnt           # comment (must be upper case)
        self.unused = 0
        self.dst = dst             # proximity distance (m)
        self.smbl = smbl           # symbol_type id
        self.dspl = dspl           # D107 display option
        self.color = color

    def __repr__(self):
        return "<Wpt_Type %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
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


class D108(Wpt_Type):

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

    def __init__(self, ident="", slat=0, slon=0, alt=1.0e25, dpth=1.0e25,
                 cmnt="", subclass="", wpt_class=0, lnk_ident="", smbl=18):
        self.ident = ident         # text identifier (upper case)
        self.slat = slat           # lat & long in semicircle terms
        self.slon = slon
        self.wpt_class = wpt_class
        self.unused = 0
        self.subclass = subclass
        self.lnk_ident = lnk_ident
        self.smbl = smbl
        self.cmnt = cmnt

    def __repr__(self):
        return "<Wpt_Type %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
                                                         degrees(self.slat),
                                                         degrees(self.slon),
                                                         id(self))

    def __str__(self):
        return "%s (%3.5f, %3.5f, %3f) '%s' class %d symbl %d" % (
            self.ident,
            degrees(self.slat), degrees(self.slon),
            self.alt, self.cmnt.strip(),
            self.wpt_class, self.smbl)


class D109(Wpt_Type):

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

    def __init__(self, ident="", slat=0, slon=0, alt=1.0e25, dpth=1.0e25,
                 cmnt="", subclass="", wpt_class=0, lnk_ident="", smbl=18):
        self.ident = ident
        self.slat = slat
        self.slon = slon
        self.wpt_class = wpt_class
        self.unused = 0
        self.subclass = subclass
        self.lnk_ident = lnk_ident
        self.smbl = smbl
        self.cmnt = cmnt

    def __repr__(self):
        return "<Wpt_Type %s (%3.5f, %3.5f) (at %i)>" % (self.ident,
                                                         degrees(self.slat),
                                                         degrees(self.slon),
                                                         id(self))

    def __str__(self):
        return "%s (%3.5f, %3.5f, %3f) '%s' class %d symbl %d" % (
            self.ident,
            degrees(self.slat), degrees(self.slon),
            self.alt, self.cmnt.strip(),
            self.wpt_class, self.smbl)


class D110(Wpt_Type):

    parts = ("dtyp", "wpt_class", "dspl_color", "attr", "smbl",
             "subclass", "slat", "slon", "alt", "dpth", "dist",
             "state", "cc", "ete", "temp", "time", "wpt_cat",
             "ident", "cmnt", "facility", "city", "addr", "cross_road")
    fmt = "<b b b b h 18s l l f f f 2s 2s l f l i s s s s s s"


class D120(Data_Type):

    parts = ("name",)
    fmt = "<17s"


class D150(Wpt_Type):

    parts = ("ident", "cc", "clss", "lat", "lon", "alt",
             "city", "state", "name", "cmnt")
    fmt = "<6s 2s b l l i 24s 2s 30s 40s"
    cc = "  "
    clss = 0
    alt = 0
    city = ""
    state = ""
    name = ""


class D151(Wpt_Type):

    parts = Wpt_Type.parts + ("dst", "name", "city", "state",
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


class D152(Wpt_Type):

    parts = Wpt_Type.parts + ("dst", "name", "city", "state",
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


class D154(Wpt_Type):

    parts = Wpt_Type.parts + ("dst", "name", "city", "state", "alt",
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


class D155(Wpt_Type):

    parts = Wpt_Type.parts + ("dst", "name", "city", "state", "alt",
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

class Rte_Hdr_Type(Data_Type):

    def __repr__(self):
        return "<Rte_Hdr_Type (at %s)>" % id(self)


class D200(Rte_Hdr_Type):

    parts = ("route_num",)
    fmt = "<b"


class D201(Rte_Hdr_Type):

    parts = ("route_num", "cmnt")
    fmt = "<b 20s"
    cmnt = ""


class D202(Rte_Hdr_Type):

    parts = ("ident",)
    fmt = "<s"


# Route links  -----------------------------------------------

class Rte_Link_Type(Data_Type):

    def __repr__(self):
        return "<Rte_Link_Type (at %s)" % id(self)


class D210(Rte_Link_Type):
    parts = ("class", "subclass", "ident")
    fmt = "<h 18s s"


# Track points  ----------------------------------------------

class TrkPoint_Type(Data_Type):

    slat = 0
    slon = 0
    time = 0  # secs since midnight 31/12/89?

    def __repr__(self):
        return "<Trackpoint (%3.5f, %3.5f) %s (at %i)>" % (
            degrees(self.slat), degrees(self.slon),
            time.asctime(time.gmtime(TimeEpoch+self.time)), id(self))


class D300(TrkPoint_Type):

    parts = ("slat", "slon", "time", "newtrk")
    fmt = "<l l L B"
    newtrk = 0


class D301(TrkPoint_Type):

    parts = ("slat", "slon", "time", "alt", "depth", "new_trk")
    fmt = "<l l L f f b"
    alt = 0.0
    depth = 0.0
    new_trk = 0


class D302(TrkPoint_Type):

    parts = ("slat", "slon", "time", "alt", "depth", "temp", "new_trk")
    fmt = "<l l L f f f b"


class D304(TrkPoint_Type):

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

class Trk_Hdr_Type(Data_Type):

    trk_ident = ""

    def __repr__(self):
        return "<Trk_Hdr_Type %s (at %i)>" % (self.trk_ident,
                                          id(self))


class D310(Trk_Hdr_Type):

    parts = ("dspl", "color", "trk_ident")
    fmt = "<b b s"
    dspl = 0
    color = 0


class D311(Trk_Hdr_Type):

    parts = ("index",)
    fmt = "<H"


class D312(Trk_Hdr_Type):

    parts = ("dspl", "color", "trk_ident")
    fmt = "<b b s"


# Proximity waypoints  ---------------------------------------

class Prx_Wpt_Type(Data_Type):

    dst = 0.0


class D400(Prx_Wpt_Type, D100):

    parts = D100.parts + ("dst",)
    fmt = D100.fmt + " f"


class D403(Prx_Wpt_Type, D103):

    parts = D103.parts + ("dst",)
    fmt = D103.fmt + " f"


class D450(Prx_Wpt_Type, D150):

    parts = ("idx",) + D150.parts + ("dst",)
    fmt = "<i " + D150.fmt[1:] + " f"
    idx = 0


# Almanacs ---------------------------------------------------

class Almanac_Type(Data_Type):
    pass


class D500(Almanac_Type):

    parts = ("weeknum", "toa", "af0", "af1", "e",
             "sqrta", "m0", "w", "omg0", "odot", "i")
    fmt = "<i f f f f f f f f f f"


class D501(Almanac_Type):

    parts = ("weeknum", "toa", "af0", "af1", "e",
             "sqrta", "m0", "w", "omg0", "odot", "i", "hlth")
    fmt = "<i f f f f f f f f f f b"


class D550(Almanac_Type):

    parts = ("svid", "weeknum", "toa", "af0", "af1", "e",
             "sqrta", "m0", "w", "omg0", "odot", "i")
    fmt = "<c i f f f f f f f f f f"


class D551(Almanac_Type):

    parts = ("svid", "weeknum", "toa", "af0", "af1", "e",
             "sqrta", "m0", "w", "omg0", "odot", "i", "hlth")
    fmt = "<c i f f f f f f f f f f b"


# Date & Time  ---------------------------------------------------

class Date_Time_Type(Data_Type):

    # Not sure what the last four bytes are. Not in docs.
    # hmm... eTrex just sends 8 bytes, no trailing 4 bytes
    parts = ("month", "day", "year", "hour", "min", "sec")  # , "unknown")
    fmt = "<b b H h b b"  # L"
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


class D600(Date_Time_Type):
    pass


class D601(Date_Time_Type):
    """D601 time point.

    Used by GPSmap 60cs, no documentation as of 2004-09-26.
    """


class D650(Data_Type):

    parts = ("takeoff_time", "landing_time", "takeoff_slat", "takeoff_slon",
             "landing_slat", "landing_slon", "night_time", "num_landings",
             "max_speed", "max_alt", "distance", "cross_country_flag",
             "departure_name", "departure_ident", "arrival_name",
             "arrival_ident", "ac_id")
    fmt = "<L L l l l l L L f f f B s s s s s"


# Position   ---------------------------------------------------

class D700(Data_Type):

    parts = ("rlat", "rlon")
    fmt = "<d d"
    rlat = 0.0  # radians
    rlon = 0.0  # radians


# Pvt ---------------------------------------------------------

# Live position info

class D800(Data_Type):

    parts = ("alt", "epe", "eph", "epv", "fix", "tow", "rlat", "rlon",
             "east", "north", "up", "msl_height", "leap_secs", "wn_days")
    fmt = "<f f f f h d d d f f f f h l"

    def __str__(self):
        return "tow: %g rlat: %g rlon: %g east: %g north %g" \
            % (self.tow, self.rlat, self.rlon, self.east, self.north)


class D906(Data_Type):

    parts = ("start_time", "total_time", "total_distance", "begin_slat",
             "begin_slon", "end_slat", "end_slon", "calories",
             "track_index", "unused")
    fmt = "<l l f l l l l i b b"


class D907(Data_Type):
    """D907 data point.

    Used by GPSmap 60cs, no documentation as of 2004-09-26.
    """


class D908(Data_Type):
    """D908 data point.

    Used by GPSmap 60cs, no documentation as of 2004-09-26.
    """


class D909(Data_Type):
    """D909 data point.

    Used by GPSmap 60cs, no documentation as of 2004-09-26.
    """


class D910(Data_Type):
    """D910 data point.

    Used by GPSmap 60cs, no documentation as of 2004-09-26.
    """


class D1011(Data_Type):
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


class D1009(Data_Type):
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
    (52,  "GNC 250"),
    (64,  "GNC 250 XL"),
    (33,  "GNC 300"),
    (98,  "GNC 300 XL"),
    (77,  "GPS 12"),
    (87,  "GPS 12"),
    (96,  "GPS 12"),
    (77,  "GPS 12 XL"),
    (96,  "GPS 12 XL"),
    (106, "GPS 12 XL Chinese"),
    (105, "GPS 12 XL Japanese"),
    (47,  "GPS 120"),
    (55,  "GPS 120 Chinese"),
    (74,  "GPS 120 XL"),
    (61,  "GPS 125 Sounder"),
    (95,  "GPS 126"),
    (100, "GPS 126 Chinese"),
    (95,  "GPS 128"),
    (100, "GPS 128 Chinese"),
    (20,  "GPS 150"),
    (64,  "GPS 150 XL"),
    (34,  "GPS 155"),
    (98,  "GPS 155 XL"),
    (34,  "GPS 165"),
    (41,  "GPS 38"),
    (56,  "GPS 38 Chinese"),
    (62,  "GPS 38 Japanese"),
    (31,  "GPS 40"),
    (41,  "GPS 40"),
    (56,  "GPS 40 Chinese"),
    (62,  "GPS 40 Japanese"),
    (31,  "GPS 45"),
    (41,  "GPS 45"),
    (56,  "GPS 45 Chinese"),
    (41,  "GPS 45 XL"),
    (96,  "GPS 48"),
    (7,   "GPS 50"),
    (14,  "GPS 55"),
    (15,  "GPS 55 AVD"),
    (18,  "GPS 65"),
    (13,  "GPS 75"),
    (23,  "GPS 75"),
    (42,  "GPS 75"),
    (25,  "GPS 85"),
    (39,  "GPS 89"),
    (45,  "GPS 90"),
    (112, "GPS 92"),
    (24,  "GPS 95"),
    (35,  "GPS 95"),
    (22,  "GPS 95 AVD"),
    (36,  "GPS 95 AVD"),
    (36,  "GPS 95 XL"),
    (59,  "GPS II"),
    (73,  "GPS II Plus"),
    (97,  "GPS II Plus"),
    (72,  "GPS III"),
    (71,  "GPS III Pilot"),
    (291, "GPSMAP 60cs"),
    (50,  "GPSCOM 170"),
    (53,  "GPSCOM 190"),
    (49,  "GPSMAP 130"),
    (76,  "GPSMAP 130 Chinese"),
    (49,  "GPSMAP 135 Sounder"),
    (49,  "GPSMAP 175"),
    (48,  "GPSMAP 195"),
    (29,  "GPSMAP 205"),
    (44,  "GPSMAP 205"),
    (29,  "GPSMAP 210"),
    (88,  "GPSMAP 215"),
    (29,  "GPSMAP 220"),
    (88,  "GPSMAP 225"),
    (49,  "GPSMAP 230"),
    (76,  "GPSMAP 230 Chinese"),
    (49,  "GPSMAP 235 Sounder"),
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
    # Use a wide window for best viewing!
    #
    # ID   minver maxver    Link      Command   Waypoint          Route                     Track             Proximity         Almanac
    7:   ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), None,             None,             ("A500", "D500")),),
    13:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500")),),
    14:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), None,             ("A400", "D400"), ("A500", "D500")),),
    15:  ((None,            ("L001"), ("A010"), ("A100", "D151"), ("A200", "D200", "D151"), None,             ("A400", "D151"), ("A500", "D500")),),
    18:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500")),),
    20:  ((None,            ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D550")),),
    22:  ((None,            ("L001"), ("A010"), ("A100", "D152"), ("A200", "D200", "D152"), ("A300", "D300"), ("A400", "D152"), ("A500", "D500")),),
    23:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500")),),
    24:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500")),),
    25:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500")),),
    29:  (((0.00, 4.00),    ("L001"), ("A010"), ("A100", "D101"), ("A200", "D201", "D101"), ("A300", "D300"), ("A400", "D101"), ("A500", "D500")),
          ((4.00, MaxVer),  ("L001"), ("A010"), ("A100", "D102"), ("A200", "D201", "D102"), ("A300", "D300"), ("A400", "D102"), ("A500", "D500")),),
    31:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500")),),
    33:  ((None,            ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D550")),),
    34:  ((None,            ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D550")),),
    35:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500")),),
    36:  (((0.00, 3.00),    ("L001"), ("A010"), ("A100", "D152"), ("A200", "D200", "D152"), ("A300", "D300"), ("A400", "D152"), ("A500", "D500")),
          ((3.00, MaxVer),  ("L001"), ("A010"), ("A100", "D152"), ("A200", "D200", "D152"), ("A300", "D300"), None,             ("A500", "D500")),),
    39:  ((None,            ("L001"), ("A010"), ("A100", "D151"), ("A200", "D201", "D151"), ("A300", "D300"), None,             ("A500", "D500")),),
    41:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500")),),
    42:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500")),),
    44:  ((None,            ("L001"), ("A010"), ("A100", "D101"), ("A200", "D201", "D101"), ("A300", "D300"), ("A400", "D101"), ("A500", "D500")),),
    45:  ((None,            ("L001"), ("A010"), ("A100", "D152"), ("A200", "D201", "D152"), ("A300", "D300"), None,             ("A500", "D500")),),
    47:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500")),),
    48:  ((None,            ("L001"), ("A010"), ("A100", "D154"), ("A200", "D201", "D154"), ("A300", "D300"), None,             ("A500", "D501")),),
    49:  ((None,            ("L001"), ("A010"), ("A100", "D102"), ("A200", "D201", "D102"), ("A300", "D300"), ("A400", "D102"), ("A500", "D501")),),
    50:  ((None,            ("L001"), ("A010"), ("A100", "D152"), ("A200", "D201", "D152"), ("A300", "D300"), None,             ("A500", "D501")),),
    52:  ((None,            ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D550")),),
    53:  ((None,            ("L001"), ("A010"), ("A100", "D152"), ("A200", "D201", "D152"), ("A300", "D300"), None,             ("A500", "D501")),),
    55:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500")),),
    56:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500")),),
    59:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500")),),
    61:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500")),),
    62:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500")),),
    64:  ((None,            ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D551")),),
    71:  ((None,            ("L001"), ("A010"), ("A100", "D155"), ("A200", "D201", "D155"), ("A300", "D300"), None,             ("A500", "D501")),),
    72:  ((None,            ("L001"), ("A010"), ("A100", "D104"), ("A200", "D201", "D104"), ("A300", "D300"), None,             ("A500", "D501")),),
    73:  ((None,            ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), None,             ("A500", "D501")),),
    74:  ((None,            ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500")),),
    76:  ((None,            ("L001"), ("A010"), ("A100", "D102"), ("A200", "D201", "D102"), ("A300", "D300"), ("A400", "D102"), ("A500", "D501")),),
    77:  (((0.00, 3.01),    ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D501")),
          ((3.01, 3.50),    ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501")),
          ((3.50, 3.61),    ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), None,             ("A500", "D501")),
          ((3.61, MaxVer),  ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501")),),
    87:  ((None,            ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501")),),
    88:  ((None,            ("L001"), ("A010"), ("A100", "D102"), ("A200", "D201", "D102"), ("A300", "D300"), ("A400", "D102"), ("A500", "D501")),),
    95:  ((None,            ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501")),),
    96:  ((None,            ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501")),),
    97:  ((None,            ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), None,             ("A500", "D501")),),
    98:  ((None,            ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D551")),),
    100: ((None,            ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501")),),
    105: ((None,            ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501")),),
    106: ((None,            ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501")),),
    112: ((None,            ("L001"), ("A010"), ("A100", "D152"), ("A200", "D201", "D152"), ("A300", "D300"), None,             ("A500", "D501")),)
}

# ====================================================================


# Now some practical implementations


class SerialLink(P000):
    """Protocol to communicate over a serial link."""

    # Control characters
    DLE = 16  # Data Link Escape
    ETX = 3  # End of Text
    Pid_Ack_Byte = 6  # Acknowledge
    Pid_Nak_Byte = 21  # Negative Acknowledge

    def __init__(self, port):
        # Import serial here, so that you don't have to have that module
        # installed, if you're not using a serial link.
        import serial
        self.timeout = 1
        self.baudrate = 9600
        self.ser = serial.Serial(port,
                                 timeout=self.timeout,
                                 baudrate=self.baudrate)
        self.unit_id = None

    def set_timeout(self, seconds):
        self.ser.timeout = self.timeout = seconds

    def get_timeout(self):
        return self.ser.timeout

    def set_baudrate(self, value):
        self.ser.baudrate = value

    def get_baudrate(self):
        return self.ser.baudrate

    def escape(self, data):
        """Escape any DLE characters, aka "DLE Stuffing".

        If any byte in the Size, Data, or Checksum fields is equal to
        DLE, then a second DLE is inserted immediately following the byte. This
        extra DLE is not included in the size or checksum calculation. This
        procedure allows the DLE character to be used to delimit the boundaries
        of a packet."""
        return data.replace(bytes([self.DLE]), bytes([self.DLE, self.DLE]))

    def unescape(self, data):
        """Unescape any DLE characters, aka "DLE unstuffing"."""
        return data.replace(bytes([self.DLE, self.DLE]), bytes([self.DLE]))

    def checksum(self, data):
        sum = 0
        for i in data:
            sum = sum + i
        sum %= 256
        checksum = (256 - sum) % 256
        return checksum

    def unpack(self, buffer):
        header = self.DLE
        trailer = [self.DLE, self.ETX]
        # Only the size, data, and checksum fields have to be unescaped, but
        # unescaping the whole packet doesn't hurt
        packet = self.unescape(buffer)
        packet_start = packet[0]
        packet_end = list(packet[-2:])

        if packet_start != header:
            log.debug("Invalid packet: doesn't start with DLE character")
        elif packet_end != trailer:
            log.debug("Invalid packet: doesn't end with DLE and ETX character")
        else:
            id = packet[1]
            size = packet[2]
            data = packet[3:-3]
            checksum = packet[-3]

            if size != len(data):
                raise ProtocolException("Invalid packet: wrong size of packet data")
            # 2's complement of the sum of all bytes from byte 1 to byte n-3
            if checksum != self.checksum(packet[1:-3]):
                raise ProtocolException("Invalid packet: checksum failed")

            return {'id': id, 'data': data}

    def pack(self, packet_id, data):
        log.info("Pack packet")
        if isinstance(data, bytes):
            pass
        elif isinstance(data, int):
            # The packet data contains a 16-bit unsigned integer that indicates
            # a particular command.
            data = data.to_bytes(2, byteorder='little')
        elif data is None:
             # The packet data is not used and may have a zero size
            data = bytes()
        else:
            data_type = type(data).__name__
            raise ProtocolException(f"Invalid data type: should be 'bytes' or 'int', but is {data_type}")
        size = len(data)
        log.debug(f"size: {size}")
        checksum = self.checksum(bytes([packet_id])
                                 + bytes([size])
                                 + data)
        log.debug(f"checksum: {checksum}")
        packet = bytes([self.DLE]) \
            + bytes([packet_id]) \
            + self.escape(bytes([size])) \
            + self.escape(data) \
            + self.escape(bytes([checksum])) \
            + bytes([self.DLE]) \
            + bytes([self.ETX])

        return packet

    def read(self):
        DLE = bytes([self.DLE])
        ETX = bytes([self.ETX])
        buffer = bytearray()
        packet = bytearray()

        while True:
            # Buffer two bytes, because all DLEs occur in pairs except at packet
            # boundaries
            buffer += self.ser.read(2-len(buffer))
            if len(buffer) != 2:
                raise LinkException("Invalid packet: unexpected end")
            elif len(packet) == 0:
                # Packet header
                if buffer.startswith(DLE):
                    packet += bytes([buffer.pop(0)])
                else:
                    raise LinkException("Invalid packet: doesn't start with DLE")
            elif buffer.startswith(DLE):
                # Escape DLE
                if buffer == DLE + DLE:
                    packet += buffer
                    buffer.clear()
                # Packet trailer
                elif buffer == DLE + ETX:
                    packet += buffer
                    break
                else:
                    raise LinkException("Invalid packet: doesn't end with DLE + ETX")
            else:
                packet += bytes([buffer.pop(0)])

        return bytes(packet)

    def write(self, buffer):
        self.ser.write(buffer)

    def readPacket(self, sendAck=True):
        buffer = self.read()
        packet = self.unpack(buffer)
        if sendAck:
            self.sendAcknowledge(packet['id'])

        return packet

    def sendPacket(self, packet_id, data, readAck=True):

        buffer = self.pack(packet_id, data)
        self.write(buffer)

        if readAck:
            self.readAcknowledge(packet_id)

    def readAcknowledge(self, packet_id):
        "Read an ack msg in response to a particular sent msg"
        log.info("Read ACK")
        packet = self.readPacket(sendAck=False)
        expected_pid = packet_id
        received_pid = int.from_bytes(packet['data'], byteorder='little')

        if packet['id'] == self.Pid_Nak_Byte:
            log.info("Received NAK packet")
            raise LinkException("Transmission error in the previous received packet")
        elif packet['id'] == self.Pid_Ack_Byte:
            log.info("Received ACK packet")
            if expected_pid != received_pid:
                raise ProtocolException(f"Device expected {expected_pid}, got {received_pid}")
        else:
            raise GarminException("Neither ACK nor NAK packet received")

    def sendAcknowledge(self, packet_id):
        log.info("Send ACK")
        data = packet_id.to_bytes(1, byteorder='little')
        self.sendPacket(self.Pid_Ack_Byte, data, readAck=False)

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
        except usb.USBError as error:
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

        [self.unit_id] = newstruct.unpack("<L", unit_id_data)

    def constructPacket(self, layer, packet_id, data=None):
        """Construct an USB package to be sent."""
        if data:
            if isinstance(data, int):
                data = newstruct.pack("<h", data)

            data_part = list(newstruct.pack("<l", len(data)))
            data_part += list(data)
        else:
            data_part = [chr(0)]*4

        package = [chr(layer)]
        package += [chr(0)]*3
        package += list(newstruct.pack("<h", packet_id))
        package += [chr(0)]*2
        package += data_part
        return package

    def sendPacket(self, packet_id, data):
        """Send a packet."""
        packet = self.constructPacket(20, packet_id, data)
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
            newstruct.unpack("<b h b h h l", header))
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
        packet = ''.join(newstruct.pack("<B", byte) for byte in packet)
        usb_packet_log.debug("> usb: %s" % (hexdump(packet)))
        usb_log.debug("Read %s bytes" % len(packet))
        return packet

    def settimeout(self, timeout):
        pass

    def close(self):
        self.handle.releaseInterface()







        except LinkException as e:

            log.log(VERBOSE, "PCP not supported")


        self.link = self.protos["link"][0](physicalLayer)
        self.cmdProto = self.protos["command"][0]

        # Now we set up 'links' through which we can get data of the
        # appropriate types


        self.command = TransferProtocol(self.link, self.cmdProto)




            return unit_id


class Garmin:
    """A representation of the GPS device.

    It is connected via some physical connection, typically a SerialLink
    of some sort.
    """
    protocol_keys = {
        'L000': 'link_protocol',
        'L001': 'link_protocol',
        'L002': 'link_protocol',
        'A000': 'product_data_protocol',
        'A001': 'protocol_capability_protocol',
        'A010': 'device_command_protocol',
        'A011': 'device_command_protocol',
        'A100': 'waypoint_transfer_protocol',
        'A101': 'waypoint_category_transfer_protocol',
        'A200': 'route_transfer_protocol',
        'A201': 'route_transfer_protocol',
        'A300': 'track_log_transfer_protocol',
        'A301': 'track_log_transfer_protocol',
        'A302': 'track_log_transfer_protocol',
        'A400': 'proximity_waypoint_transfer_protocol',
        'A500': 'almanac_transfer_protocol',
        'A600': 'date_and_time_initialization_protocol',
        'A650': 'flightbook_transfer_protocol',
        'A700': 'position_initialization_protocol',
        'A800': 'pvt_protocol',
        'A906': 'lap_transfer_protocol',
        'A1000': 'run_transfer_protocol',
        'A1002': 'workout_transfer_protocol',
        'A1004': 'fitness_user_profile_transfer_protocol',
        'A1005': 'workout_limits_transfer_protocol',
        'A1006': 'course_transfer_protocol',
        'A1009': 'course_limits_transfer_protocol',
        'A1051': 'external_time_data_sync_protocol',
    }


    def __init__(self, physicalLayer):
        self.phys = physicalLayer
        self.unit_id = self.phys.unit_id
        self.link = L000(self.phys)
        self.product_data_protocol = A000(self.link)
        self.product_data = self.product_data_protocol.getProductData()
        self.product_id = self.product_data['id']
        self.software_version = self.product_data['version']
        self.product_description = self.product_data['description']
        self.protocol_capability = A001(self.link)
        self.supported_protocols = self.get_protocols(self.protocol_capability, self.product_id, self.software_version)
        self.registered_protocols = self.register_protocols(self.supported_protocols)
        self.link = self.create_protocol('link_protocol', self.phys)
        self.device_command = self.create_protocol('device_command_protocol', self.link)
        self.waypoint_transfer = self.create_protocol('waypoint_transfer_protocol', self.link, self.device_command)
        self.route_transfer = self.create_protocol('route_transfer_protocol', self.link, self.device_command)
        self.track_log_transfer = self.create_protocol('track_log_transfer_protocol', self.link, self.device_command)
        self.proximity_waypoint_transfer = self.create_protocol('proximity_waypoint_transfer_protocol', self.link, self.device_command)
        self.almanac_transfer = self.create_protocol('almanac_transfer_protocol', self.link, self.device_command)
        self.date_and_time_initialization = self.create_protocol('date_and_time_initialization_protocol', self.link, self.device_command)
        self.flightbook_transfer = self.create_protocol('flightbook_transfer_protocol', self.link, self.device_command)
        # Sorry, no link for A700
        self.pvt = self.create_protocol('pvt_protocol', self.link, self.device_command)
        self.lap_transfer = self.create_protocol('lap_transfer_protocol', self.link, self.device_command)
        self.run_transfer = self.create_protocol('run_transfer_protocol', self.link, self.device_command)

    def get_protocols(self, link, product_id, software_version):
        # Wait for the unit to announce its capabilities using A001.  If
        # that doesn't happen, try reading the protocols supported by the
        # unit from the Big Table.
        try:
            log.info("Get supported protocols")
            protocols = link.getProtocols()
        except LinkException:
            log.info("Protocol Capability Protocol not supported by the device")
            try:
                protocols = link.getProtocolsNoPCP(product_id, software_version)
            except KeyError:
                raise Exception("Couldn't determine product capabilities")
        return protocols

    def class_by_name(self, name):
        return globals()[name]

    def register_protocols(self, supported_protocols):
        """Register the supported protocols."""
        protocols = {}
        for protocol_datatypes in supported_protocols:
            protocol = protocol_datatypes[0]
            datatypes = protocol_datatypes[1:]
            if protocol in self.protocol_keys:
                key = self.protocol_keys[protocol]
                protocol_class = self.class_by_name(protocol)
                protocols[key] = [protocol_class]
                log.info(f"Register protocol {protocol}.")
                if datatypes:
                    datatype_classes = [self.class_by_name(datatype) for datatype in datatypes]
                    protocols[key].extend(datatype_classes)
                    log.info(f"Register datatypes {*datatypes, }.")
            else:
                log.info(f"Ignore undocumented protocol {protocol}.")
        log.info(f"Registered protocols and data types: {protocols}")
        return protocols

    def create_protocol(self, key, *args):
        protocol_datatypes = self.registered_protocols.get(key)
        if protocol_datatypes:
            protocol = protocol_datatypes[0]
            datatypes = protocol_datatypes[1:]
            if datatypes:
                return protocol(*args, datatypes=datatypes)
            else:
                return protocol(*args)
        else:
            log.info(f"Protocol {key} is not supported.")

    def getWaypoints(self, callback=None):
        return self.waypoint_transfer.getData(callback)

    def putWaypoints(self, data, callback=None):
        return self.waypoint_transfer.putData(data, callback)

    def getRoutes(self, callback=None):
        return self.route_transfer.getData(callback)

    def putRoutes(self, data, callback=None):
        return self.route_transfer.putData(data, callback)

    def getTracks(self, callback=None):
        return self.track_log_transfer.getData(callback)

    def putTracks(self, data, callback=None):
        return self.track_log_transfer.putData(data, callback)

    def getLaps(self, callback=None):
        assert self.lap_transfer is not None, (
            "No lap protocol specified for this GPS.")
        return self.lap_transfer.getData(callback)

    def getRuns(self, callback=None):
        assert self.run_transfer is not None, (
            "No run protocol supported for this GPS.")
        return self.run_transfer.getData(callback)

    def getProxPoints(self, callback=None):
        return self.proximity_waypoint_transfer.getData(callback)

    def putProxPoints(self, data, callback=None):
        return self.proximity_waypoint_transfer.putData(data, callback)

    def getAlmanac(self, callback=None):
        return self.almanac_transfer.getData(callback)

    def getTime(self, callback=None):
        return self.date_and_time_initialization.getData(callback)

    def getFlightBook(self, callback=None):
        return self.flightbook_transfer.getData(callback)

    def pvtOn(self):
        return self.pvt.dataOn()

    def pvtOff(self):
        return self.pvt.dataOff()

    def getPvt(self, callback=None):
        return self.pvt.getData(callback)

    def abortTransfer(self):
        return self.command.abortTransfer()

    def turnPowerOff(self):
        return self.command.turnPowerOff()


# Callback examples functions

def MyCallbackgetWaypoints(waypoint, recordnumber, totalWaypointsToGet, packet_id):
    # We get a tuple back (waypoint, recordnumber, totalWaypointsToGet)
    # packet_id is the command to send/get from the gps, look at the docs (Garmin GPS Interface Specification)
    # pag 9, 10 or 4.2 L001 and L002 link Protocol

    print("---  waypoint ", " %s / %s " % (recordnumber, totalWaypointsToGet), "---")

    print("str output --> ", waypoint)  # or repr(waypoint)
    print()

    if recordnumber != totalWaypointsToGet:
        print("directory output: --> ", waypoint.getDict())
    else:
        print()
        print("This is the last waypoint:")
        print()

        for x in waypoint.getDict():
            print(x, " --> ", waypoint.getDict()[x])

    print("Command: ", packet_id)
    print()


def MyCallbackputWaypoints(waypoint, recordnumber, totalWaypointsToSend, packet_id):
    # we get a tuple waypoint, recordnumber, totalWaypointsToSend, packet_id

    print("waypoint %s added to gps (total waypoint(s): %s/%s) waypoint command: %s" % (waypoint.ident, recordnumber, totalWaypointsToSend, packet_id))


def MyCallbackgetRoutes(point, recordnumber, totalpointsToGet, packet_id):

    # print point.__class__

    if isinstance(point, (Rte_Hdr_Type)):
        print("Route: ", point)

    # I really don't want the D210_Rte_Link_Type

    elif not isinstance(point, Rte_Link_Type):

        if recordnumber != totalpointsToGet:
            print("   ", point)
        else:
            print()
            print("This is the last waypoint of a route:")

            for x in point.getDict():
                print(x, " --> ", point.getDict()[x])


def MyCallbackputRoutes(point, recordnumber, totalPointsToSend, packet_id):

    if isinstance(point, Rte_Hdr_Type):
        print()
        print("Adding route:", point)
    elif not isinstance(point, Rte_Link_Type):
        print("   waypoint added", point.ident)


def MyCallbackgetTracks(point, recordnumber, totalPointsToGet, packet_id):

    if isinstance(point, Trk_Hdr_Type):
        print("Track: ", point)
    else:

        if recordnumber != totalPointsToGet:

            print("   ", point, end=' ')

            if point.new_trk:
                print("(New track segment)", end=' ')

            print()

        else:
            print()
            print("This is the last waypoint of a track:")

            print(point)

            print("Time are the seconds since midnight 31/12/89 and are only correct for the ACTIVE LOG !! (hmmm...)")


def MyCallbackputTracks(point, recordnumber, totalPointsToSend, packet_id):

    if isinstance(point, Trk_Hdr_Type):
        print("Track: ", point)
    else:
        print("   ", point)


def MyCallbackgetAlmanac(satellite, recordnumber, totalPointsToGet, packet_id):

    print()

    for x in satellite.dataDict:
        print("%7s --> %s" % (x, satellite.getDict()[x]))


# =================================================================
# The following is test code. See other included files for more
# useful applications.

def main():

    if os.name == 'nt':
        # 0 is com1, 1 is com2 etc
        serialDevice = 0
    else:
        serialDevice = "/dev/ttyUSB0"

        if sys.platform[:-1] == "freebsd":
            serialDevice = "/dev/cuaa0"  # For FreeBsd

    phys = SerialLink(serialDevice)

    gps = Garmin(phys)

    print("GPS Product ID: %d Descriptions: %s Software version: %2.2f\n" %
          (gps.product_id, gps.product_description, gps.software_version))

    # Show gps information

    if 1:
        print(f'''
        GPS Product ID: {gps.product_id}
        GPS version   : {gps.software_version}
        GPS           : {gps.product_description[0]}
        MapSource info: {gps.product_description[1:]}

        Product protocols:
        ------------------
        ''')

        # Some code from pygarmin, small but smart

        for i in range(len(gps.protocols)):
            p = gps.protocols[i]

            if p[0] == 'D':
                print(p, end=' ')
            else:
                if i == 0:
                    print(p, end=' ')
                else:
                    print()
                    print(p, end=' ')

        print()

        # print unknown protocols

        if len(gps.protocols_unknown):
            print("\nProduct protocols which are not supported yet:")
            print("----------------------------------------------")

            for i in range(len(gps.protocols_unknown)):
                p = gps.protocols_unknown[i]

                if p[0] == 'D':
                    print(p, end=' ')
                else:
                    if i == 0:
                        print(p, end=' ')
                    else:
                        print()
                        print(p, end=' ')

            print('\n')

    # Show waypoints

    if 0:

        # First method, just get the waypoints in a list (look at class A100, function __str__)

        waypoints = gps.getWaypoints()

        print("Waypoints:")
        print("----------")

        for x in waypoints:
            print(x)

        print("\nSame waypoints called by a callback function:")
        print("---------------------------------------------\n")

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
        data2['cmnt'] = "A TEST POINT"
        data2['slat'] = 624447295
        data2['slon'] = -2529985

        data3 = {'ident': "CLUB91", 'cmnt': "DRINKING", 'slat': 606532864, 'slon': 57654672, 'smbl': 13}

        print("Send waypoints to gps:")
        print("---------------------")

        gps.putWaypoints([data1, data2, data3], MyCallbackputWaypoints)

        # or gps.putWaypoints([data1, data2]) without a callback function

        print()
        print("Are there 3 waypoints added to your gps ??")

    # Show Routes

    if 0:

        routes = gps.getRoutes()

        print("Routes:")
        print("-------")

        for route in routes:
            print("\nRoute name:", route[0].ident.decode())

            for point in route[1:]:

                # Ok, Bad way to remove D210_Rte_Link_Type entrys

                if len(route) > 23:
                    print("   ", point)

        # Now with a callback function

        print("\nSame routes but now with a callback function:")
        print("---------------------------------------------\n")

        gps.getRoutes(MyCallbackgetRoutes)

    # Put Routes

    if 0:

        # Test Route 1

        header1 = {'nmbr': 1, 'ident': 'DRINKING'}

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

        header2 = {'nmbr': 2, 'ident': "TEST ROUTE 2"}

        data1_2 = {}
        data1_2['ident'] = "TEST01"
        data1_2['slat'] = 608466698
        data1_2['slon'] = 46580036

        data2_2 = {'ident': "TEST02", 'slat': 608479774, 'slon': 46650547}
        data3_2 = {'ident': "TEST03", 'slat': 608451909, 'slon': 46665535}
        data4_2 = {'ident': "TEST04", 'slat': 608440119, 'slon': 46644415}

        print("Send two routes to the gps")
        gps.putRoutes([(header1, data1_1, data2_1),
                       (header2, data1_2, data2_2, data3_2, data4_2)])
        print("Routes added")

        # Now with a callback function

        print()
        print("Same routes but now with a callback function:")
        print("---------------------------------------------")
        print("If you leave the header empty, the computer will generate one for you (ROUTE1, ROUTE2,....)")

        header1 = header2 = {}

        gps.putRoutes([(header1, data1_1, data2_1), (header2, data1_2, data2_2, data3_2, data4_2)], MyCallbackputRoutes)

        print()
        print("Four routes are added to your gps, two of them are generated !")
        print("and a few waypoints")

    # Show Tracks

    if 0:
        print("Tracks")
        print("------")

        tracks = gps.getTracks()

        for track in tracks:

            # Check for multiple tracks

            if isinstance(track, list):
                print()
                print("Track name:", track[0])

                for point in track[1:]:
                    print("   ", point)
            else:
                print(track)

        # Now with a callback function

        print()
        print("Same tracks but now with a callback function:")
        print("---------------------------------------------")

        gps.getTracks(MyCallbackgetTracks)

    # Send tracks

    if 0:
        print("Sending tracks with a callback function:")
        print("----------------------------------------")
        print("If you leave the header empty, the computer will generate one for you (TRACK1, TRACK2,....)")
        print("It's possible to send track to the ACTIVE LOG.but you can't send time to tracks")

        header1 = {'ident': 'TEST TRACK'}
        # header1 = {'ident':'ACTIVE LOG'}  # for sending track's to the ACTIVE LOG
        data1_1 = {'slat': 608528384, 'slon': 46271488}
        data2_1 = {'slat': 608531200, 'slon': 46260224}
        data3_1 = {'slat': 608529664, 'slon': 46262272}

        header2 = {}
        data1_2 = {'slat': 608529718, 'slon': 46262291}
        data2_2 = {'slat': 608529718, 'slon': 46262291}
        data3_2 = {'slat': 608532699, 'slon': 46250150, 'new_trk': True}
        data4_2 = {'slat': 608526491, 'slon': 46257149}
        data5_2 = {'slat': 608520439, 'slon': 46264816}
        data6_2 = {'slat': 608521779, 'slon': 46262842}

        # Check if we can store multiple tracklogs

        if isinstance(gps.trkLink, A300):
            gps.putTracks([(data1_1, data2_1, data3_1),
                           (data1_2, data2_2, data3_2, data4_2, data5_2, data6_2)], MyCallbackputTracks)

            print("Track added?")

        else:
            gps.putTracks([(header1, data1_1, data2_1, data3_1),
                           (header2, data1_2, data2_2, data3_2,
                            data4_2, data5_2, data6_2)], MyCallbackputTracks)

            print("Two track logs added?")

    # Show proximity points

    if 0:
        print("Proximity waypoints:")
        print("-------------------")

        for proxi in gps.getProxPoints():
            print(proxi)

    # Send  proximity points

    if 0:
        print("Sending 2 proximity waypoints:")
        print("------------------------------")

        data1 = {'ident': 'WATER', 'slat': 608688816, 'slon': 45891108, 'dist': 300}
        data2 = {'ident': 'AERPRT', 'slat': 607132209, 'slon': 53673984, 'dist': 400}
        gps.putProxPoints([data1, data2])

        print("Check your waypoint and proximity waypoint menu on your gps!")

    # Show almanac

    if 0:
        print("Almanac information:")
        print("--------------------")

        gps.getAlmanac(MyCallbackgetAlmanac)

    # Show FlightBook

    if 0:
        print("FlightBook information:")
        print("-----------------------")

        flightbook = gps.getFlightBook()

        for x in flightbook:
            print(x)

    # Show date and time

    if 0:
        print("Date and time:")
        print("--------------")

        def MyCallbackgetTime(timeInfo, recordnumber, totalPointsToGet, packet_id):
            print(timeInfo)

        print(gps.getTime(MyCallbackgetTime))

    # Show some real-time data

    if 0:
        print("Starting pvt")
        print("-----------")

        gps.pvtOn()

        def MyCallbackgetPvt(pvt, recordnumber, totalPointsToGet, packet_id):
            print(pvt.getDict())

        try:
            for i in range(10):
                p = gps.getPvt(MyCallbackgetPvt)
                print(p)

        finally:
            print("Stopping pvt")
            gps.pvtOff()

    # Show Lap type info

    if 0:
        print("Lap info")
        print("--------")

        laps = gps.getLaps()

        for x in laps:
            print(x)


if __name__ == "__main__":
    main()
