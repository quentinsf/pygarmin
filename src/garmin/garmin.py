"""Module for communicating with Garmin GPS devices.

   This module implements the protocol used for communication by the Garmin GPS
   receivers. It is based on the official description available from Garmin at

   https://www8.garmin.com/support/commProtocol.html

   The protocols used in the Garmin Device Interface are arranged in the
   following three layers:

   ============= ===========
    Application   (highest)
    Link
    Physical      (lowest)
   ============= ===========

   The Physical link protocol for serial is based on RS-232 and uses DLE/ETX
   framing. The Physical protocol for USB uses packetization intrinsic
   to USB bulk pipes.

   There are several link protocols. All devices implement the L000 Basic Link
   Protocol. Of the product-specific protocols, most devices implement the L001
   Link Protocol 1, and some panel-mounted aviation devices implement L002 Link
   Protocol 2. The link protocols are carried over either Physical protocol.

   At the Application layer, there are several protocols used to implement data
   transfers between a host and a device. They are carried over Link protocols.

   The Physical, Transmission, Link, and Application protocol IDs are 3-digit
   numbers prefixed with P, T, L, and A respectively, and data type IDs are
   prefixed with D.

   This file is part of the pygarmin distribution
   (https://github.com/quentinsf/pygarmin).

   Copyright 2022 Folkert van der Beek <folkertvanderbeek@gmail.com>
   Copyright 2007-2008 Bjorn Tillenius <bjorn.tillenius@gmail.com>
   Copyright 2003 Quentin Stafford-Fraser <www.qandr.org/quentin>
   Copyright 2000 James A. H. Skillen <jahs@jahs.net>
   Copyright 2001 Raymond Penners <raymond@dotsphinx.com>
   Copyright 2001 Tom Grydeland <Tom.Grydeland@phys.uit.no>

   This program is free software: you can redistribute it and/or modify it under
   the terms of the GNU General Public License as published by the Free Software
   Foundation, version 3.

   This program is distributed in the hope that it will be useful, but WITHOUT
   ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
   details.

   You should have received a copy of the GNU General Public License along with
   this program. If not, see <http://www.gnu.org/licenses/>.

   This is released under the Gnu General Public Licence. A copy of this can be
   found at https://opensource.org/licenses/gpl-license.html

"""

from array import array
from datetime import datetime, timedelta
from functools import cached_property
import io
import json
import logging
import math
import os
import PIL.Image
import rawutil
import re
import serial
import sys
import usb

# Set default logging handler to avoid "No handler found" warnings.
log = logging.getLogger('garmin')
log.addHandler(logging.NullHandler())


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


class P000:
    """Physical layer for communicating with Garmin."""

    def set_baudrate(self, value):
        pass

    def get_baudrate(self):
        pass


class SerialLink(P000):
    """Protocol to communicate over a serial link.

    The port is opened on object creation.

    The ``port`` value is a device name depending on operating system, e.g.
    /dev/ttyUSB0 on GNU/Linux, /dev/cu.serial on macOS or COM1 on Windows.

    Support for the Garmin USB-serial protocol on GNU/Linux needs the
    ``garmin_gps`` kernel module which is part of the official kernels since
    version 2.6.11.

    """
    # Control characters
    dle = 16  # Data Link Escape
    etx = 3  # End of Text
    pid_ack_byte = 6  # Acknowledge
    pid_nak_byte = 21  # Negative Acknowledge

    def __init__(self, port):
        self.port = port
        self.timeout = 1
        self.baudrate = 9600
        self.max_retries = 5

    @cached_property
    def ser(self):
        try:
            return serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        except serial.SerialException as e:
            raise LinkError(e.strerror)

    def set_timeout(self, seconds):
        self.ser.timeout = self.timeout = seconds

    def get_timeout(self):
        return self.ser.timeout

    def set_baudrate(self, value):
        self.ser.baudrate = value

    def get_baudrate(self):
        return self.ser.baudrate

    def escape(self, data):
        """Escape any DLE characters, aka "DLE stuffing".

        If any byte in the Size, Data, or Checksum fields is equal to
        DLE, then a second DLE is inserted immediately following the byte. This
        extra DLE is not included in the size or checksum calculation. This
        procedure allows the DLE character to be used to delimit the boundaries
        of a packet."""
        return data.replace(bytes([self.dle]), bytes([self.dle, self.dle]))

    def unescape(self, data):
        """Unescape any DLE characters, aka "DLE unstuffing"."""
        return data.replace(bytes([self.dle, self.dle]), bytes([self.dle]))

    def checksum(self, data):
        """The checksum value contains the two's complement of the modulo 256 sum of
        all bytes in the data. Taking a two's complement of a number converts it
        to binary, flips 1 bits to 0 bits and 0 bits to 1 bits, and adds one to
        it.

        """
        sum = 0
        for i in data:
            sum = sum + i
            sum %= 256
            checksum = (256 - sum) % 256
        return checksum

    def unpack(self, buffer):
        """All data is transferred in byte-oriented packets. A packet contains a
        three-byte header (DLE, ID, and Size), followed by a variable number of
        data bytes, followed by a three-byte trailer (Checksum, DLE, and ETX).

        """
        log.debug("Unpack packet...")
        # Only the size, data, and checksum fields have to be unescaped, but
        # unescaping the whole packet doesn't hurt
        packet = self.unescape(buffer)
        id = packet[1]
        size = packet[2]
        data = packet[3:-3]
        checksum = packet[-3]
        if size != len(data):
            raise LinkError("Invalid packet: wrong size of packet data")
        # 2's complement of the sum of all bytes from byte 1 to byte n-3
        if checksum != self.checksum(packet[1:-3]):
            raise LinkError("Invalid packet: checksum failed")

        return {'id': id, 'data': data}

    def pack(self, pid, data):
        """
        All data is transferred in byte-oriented packets. A packet contains a
        three-byte header (DLE, ID, and Size), followed by a variable number of
        data bytes, followed by a three-byte trailer (Checksum, DLE, and ETX).

        Serial Packet Format

        ============= ===================== ================================================================
         Byte Number   Byte Description      Notes
        ============= ===================== ================================================================
         0             Data Link Escape      ASCII DLE character (16 decimal)
         1             Packet ID             identifies the type of packet
         2             Size of Packet Data   number of bytes of packet data (bytes 3 to n-4)
         3 to n-4      Packet Data           0 to 255 bytes
         n-3           Checksum              2's complement of the sum of all bytes from byte 1 to byte n-4
         n-2           Data Link Escape      ASCII DLE character (16 decimal)
         n-1           End of Text           ASCII ETX character (3 decimal)
        ============= ===================== ================================================================

        """
        log.debug("Pack packet...")
        if 0 < pid < 256:
            pass
        else:
            raise ProtocolError("Serial link doesn't support PIDs higher than 255. Try USB link instead.")
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
            datatype = type(data).__name__
            raise ProtocolError(f"Invalid data type: should be 'bytes' or 'int', but is {datatype}")
        size = len(data)
        log.debug(f"Packet data size: {size}")
        checksum = self.checksum(bytes([pid])
                                 + bytes([size])
                                 + data)
        log.debug(f"Packet data checksum: {checksum}")
        packet = bytes([self.dle]) \
            + bytes([pid]) \
            + self.escape(bytes([size])) \
            + self.escape(data) \
            + self.escape(bytes([checksum])) \
            + bytes([self.dle]) \
            + bytes([self.etx])

        return packet

    def read(self):
        """Read one packet from the buffer."""
        dle = bytes([self.dle])
        etx = bytes([self.etx])
        buffer = bytearray()
        packet = bytearray()

        while True:
            # Buffer two bytes, because all DLEs occur in pairs except at packet
            # boundaries
            try:
                buffer += self.ser.read(2-len(buffer))
            except serial.SerialException as e:
                raise LinkError(e.strerror)
            if not buffer:
                raise LinkError("Reading packet timed out")
            elif len(buffer) != 2:
                raise LinkError("Invalid packet: unexpected end")
            elif len(packet) == 0:
                # Packet header
                if buffer.startswith(dle):
                    packet += bytes([buffer.pop(0)])
                else:
                    raise LinkError("Invalid packet: doesn't start with DLE character")
            elif buffer.startswith(dle):
                # Escape DLE
                if buffer == dle + dle:
                    packet += buffer
                    buffer.clear()
                    # Packet trailer
                elif buffer == dle + etx:
                    packet += buffer
                    break
                else:
                    raise LinkError("Invalid packet: doesn't end with DLE and ETX character")
            else:
                packet += bytes([buffer.pop(0)])

        return bytes(packet)

    def write(self, buffer):
        try:
            self.ser.write(buffer)
        except serial.SerialException as e:
            raise LinkError(e.strerror)

    def read_packet(self, acknowledge=True):
        retries = 0
        while retries <= self.max_retries:
            try:
                buffer = self.read()
                log.debug(f"> {bytes.hex(buffer, sep=' ')}")
                packet = self.unpack(buffer)
                if acknowledge:
                    self.send_ack(packet['id'])
                break
            except LinkError as e:
                log.info(e)
                self.send_nak()
                retries += 1

        if retries > self.max_retries:
            raise LinkError("Maximum retries exceeded")

        return packet

    def send_packet(self, pid, data, acknowledge=True):
        """Send a packet."""
        buffer = self.pack(pid, data)
        log.debug(f"< {bytes.hex(buffer, sep=' ')}")
        retries = 0
        while retries <= self.max_retries:
            try:
                self.write(buffer)
                if acknowledge:
                    self.read_ack(pid)
                break
            except LinkError as e:
                log.error(e)
                retries += 1

        if retries > self.max_retries:
            raise LinkError("Maximum retries exceeded")

    def read_ack(self, pid):
        """Read a ACK/NAK packet.

        If an ACK packet is received the packet was received correctly and
        communication may continue. If a NAK packet is received, the data packet was not
        received correctly and should be sent again.

        """
        log.debug("Read ACK/NAK")
        packet = self.read_packet(acknowledge=False)
        expected_pid = pid
        received_pid = int.from_bytes(packet['data'], byteorder='little')

        if packet['id'] == self.pid_ack_byte:
            log.debug("Received ACK packet")
            if expected_pid != received_pid:
                raise ProtocolError(f"Device expected {expected_pid}, got {received_pid}")
        elif packet['id'] == self.pid_nak_byte:
            log.debug("Received NAK packet")
            raise LinkError("Packet was not received correctly")
        else:
            raise GarminError("Received neither ACK nor NAK packet")

    def send_ack(self, pid):
        """Send an ACK packet."""
        log.debug("Send ACK packet")
        data = pid.to_bytes(2, byteorder='little')
        self.send_packet(self.pid_ack_byte, data, acknowledge=False)

    def send_nak(self):
        """Send a NAK packet.

        NAKs are used only to indicate errors in the communications link, not
        errors in any higher-layer protocol.

        """
        log.debug("Send NAK packet")
        data = bytes()  # we cannot determine the packet id because it was corrupted
        self.send_packet(self.pid_nak_byte, data, acknowledge=False)

    def __del__(self):
        """Should close down any opened resources."""
        self.close()

    def close(self):
        """Close the serial port."""
        if "ser" in self.__dict__:
            self.ser.close()


class USBLink(P000):
    """Implementation of the Garmin USB protocol.

    Support for the Garmin USB protocol needs libusb 1.0 and probably removing
    and blacklisting the ``garmin_gps`` kernel module. It will talk to the first
    Garmin GPS device it finds.

    """
    idVendor = 2334  # 0x091e
    configuration_value = 1
    max_buffer_size = 4096

    # Packet Types
    USB_Protocol_Layer = 0  # 0x00
    Application_Layer = 20  # 0x14

    # Endpoints
    Bulk_OUT = 2        # 0x02
    Interrupt_IN = 129  # 0x81
    Bulk_IN = 131       # 0x83  # unused

    # USB Protocol Layer Packet Ids
    pid_data_available = 2  # unused
    pid_start_session = 5
    pid_session_started = 6

    def __init__(self):
        self.timeout = 1
        self.max_retries = 5
        self.start_session()

    def __del__(self):
        usb.util.dispose_resources(self.dev)

    def set_timeout(self, seconds):
        self.timeout = seconds

    def get_timeout(self):
        return self.timeout

    @cached_property
    def dev(self):
        """Return the Garmin device.

        This property will cause some USB traffic the first time it is accessed
        and cache the resulting value for future use.

        """
        dev = usb.core.find(idVendor=self.idVendor)
        if dev is None:
            raise LinkError("Garmin device not found")

        return dev

    @cached_property
    def cfg(self):
        """Configure the Garmin device and return the current configuration.

        This property will cause some USB traffic the first time it is accessed
        and cache the resulting value for future use.

        """
        # Check the currently active configuration. If the configuration we want
        # is already active, then we don't have to select any configuration.
        # This prevents the configuration selection problem described in the
        # libusb documentation
        # (https://libusb.sourceforge.io/api-1.0/libusb_caveats.html#configsel).
        cfg = self.dev.get_active_configuration()
        if cfg.bConfigurationValue != self.configuration_value:
            self.dev.set_configuration(self.configuration_value)
            cfg = self.dev.get_active_configuration()

        return cfg

    @cached_property
    def intf(self):
        """Return the current interface configuration.

        This property will cause some USB traffic the first time it is accessed
        and cache the resulting value for future use.

        """
        intf = self.cfg[(0, 0)]
        return intf

    @cached_property
    def ep_in(self):
        """Return the Interrupt IN instance.

        This property will cause some USB traffic the first time it is accessed
        and cache the resulting value for future use.

        """
        ep = usb.util.find_descriptor(self.intf,
                                           bEndpointAddress=self.Interrupt_IN)
        return ep

    @cached_property
    def ep_out(self):
        """Return the Bulk OUT instance.

        This property will cause some USB traffic the first time it is accessed
        and cache the resulting value for future use.

        """

        ep = usb.util.find_descriptor(self.intf,
                                           bEndpointAddress=self.Bulk_OUT)
        return ep

    def unpack(self, buffer):
        """Unpack a raw USB packet.

        """
        # packet_type = buffer[0]  # unused
        # reserved_1 = buffer[1:4]  # unused
        id = buffer[4:6]
        # reserved_2 = buffer[6:8]  # unused
        size = buffer[8:12]
        data = buffer[12:]

        id = int.from_bytes(id, byteorder='little')
        size = int.from_bytes(size, byteorder='little')

        if size != len(data):
            raise ProtocolError("Invalid packet: wrong size of packet data")

        return {'id': id, 'data': data}

    def pack(self, layer, pid, data=None):
        """Pack an USB packet.

        USB Packet Format:

        ============= ================== ================================================
         Byte Number   Byte Description   Notes
        ============= ================== ================================================
                   0   Packet Type        USB Protocol Layer = 0, Application Layer = 20
                 1-3   Reserved           must be set to 0
                 4-5   Packet ID
                 6-7   Reserved           must be set to 0
                8-11   Data size
                 12+   Data
        ============= ================== ================================================

        """
        log.debug("Pack packet")
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
            datatype = type(data).__name__
            raise ProtocolError(f"Invalid data type: should be 'bytes' or 'int', but is {datatype}")

        size = len(data)
        log.debug(f"Data size: {size}")

        packet = bytes([layer]) \
            + bytes([0]) * 3 \
            + pid.to_bytes(2, byteorder='little') \
            + bytes([0]) * 2 \
            + size.to_bytes(4, byteorder='little') \
            + data

        return packet

    def read(self):
        """Read buffer."""
        endpoint = self.Interrupt_IN
        size = self.max_buffer_size
        # The libusb timeout is specified in milliseconds
        timeout = self.timeout * 1000 if self.timeout else None
        try:
            buffer = self.dev.read(endpoint, size, timeout=timeout)
        except usb.core.USBError as e:
            raise LinkError(e.strerror)

        # pyusb returns an array object, but we want a bytes object
        return buffer.tobytes()

    def write(self, buffer):
        """Write buffer."""
        endpoint = self.Bulk_OUT
        # The libusb timeout is specified in milliseconds
        timeout = self.timeout * 1000 if self.timeout else None
        try:
            self.dev.write(endpoint, buffer, timeout=timeout)
        except usb.core.USBError as e:
            raise LinkError(e.strerror)

    def read_packet(self):
        """Read a packet."""
        retries = 0
        while retries <= self.max_retries:
            try:
                buffer = self.read()
                log.debug(f"> {bytes.hex(buffer, sep=' ')}")
                packet = self.unpack(buffer)
                break
            except LinkError as e:
                log.info(e)
                retries += 1

        if retries > self.max_retries:
            raise LinkError("Maximum retries exceeded")

        return packet

    def send_packet(self, pid, data):
        """Send a packet."""
        buffer = self.pack(self.Application_Layer, pid, data)
        log.debug(f"< {bytes.hex(buffer, sep=' ')}")
        retries = 0
        while retries <= self.max_retries:
            try:
                self.write(buffer)
                break
            except LinkError as e:
                log.error(e)
                retries += 1

        if retries > self.max_retries:
            raise LinkError("Maximum retries exceeded")

    def send_start_session_packet(self):
        """Send a Start Session packet.

        The Start Session packet must be sent by the host to begin transferring
        packets over USB. It must also be sent anytime the host deliberately
        stops transferring packets continuously over USB and wishes to begin
        again. No data is associated with this packet.

        Start Session Packet

        === ================ =================== ==================
         N   Direction        Packet ID           Packet Data Type
        === ================ =================== ==================
         0   Host to Device   pid_start_session   n/a
        === ================ =================== ==================

        """
        log.info("Send Start Session packet")
        buffer = self.pack(self.USB_Protocol_Layer, self.pid_start_session)
        log.debug(f"< packet {self.pid_start_session}: {bytes.hex(b'')}")
        self.write(buffer)

    def read_session_started_packet(self):
        """Read Start Session packet.

        The Session Started packet indicates that transfers can take place to
        and from the device. The host should ignore any packets it receives
        before receiving this packet. The data returned with this packet is the
        device’s unit ID. We ignore this, because it is retrieved elsewhere as
        well.

        Session Started Packet

        === ================ ===================== ==================
         N   Direction        Packet ID             Packet Data Type
        === ================ ===================== ==================
         0   Device to Host   pid_session_started   uint32
        === ================ ===================== ==================

        """
        log.info("Read Session Started packet")
        while True:
            packet = self.read_packet()
            if packet['id'] == self.pid_session_started:
                log.info("Received Session Started packet")
                break


    def start_session(self):
        """Start USB session and return the unit ID.

        """
        log.info("Start USB session")
        self.send_start_session_packet()
        self.read_session_started_packet()


class L000:
    """Basic Link Protocol.

    The Basic Link Protocol is used for the initial communication with the A000
    Product Data Protocol to determine the product data of the connected device.

    """
    pid_ext_product_data = 248  # may not be implemented in all devices
    pid_protocol_array = 253    # may not be implemented in all devices
    pid_product_rqst = 254
    pid_product_data = 255

    def __init__(self, physicalLayer):
        self.phys = physicalLayer

    def send_packet(self, pid, data):
        """Send a packet."""
        self.phys.send_packet(pid, data)

    def read_packet(self):
        """Read a packet."""
        while True:
            packet = self.phys.read_packet()
            if packet['id'] == self.pid_ext_product_data:
                # The ExtProductData contains zero or more null-terminated
                # strings that are used during manufacturing to identify other
                # properties of the device and are not formatted for display to the
                # end user. According to the specification the host should ignore
                # it.
                log.info(f"Got packet type {self.pid_ext_product_data}, ignoring...")
                datatype = ExtProductData()
                datatype.unpack(packet['data'])
                for property in datatype.properties:
                    log.debug(f"Extra Product Data: {property[0].decode()}")
            else:
                break

        return packet

    def expect_packet(self, pid):
        """Expect and read a particular packet type. Return data.

        """
        packet = self.read_packet()
        if packet['id'] != pid:
            raise ProtocolError(f"Expected {pid:3}, got {packet['id']:3}")

        return packet


class L001(L000):
    """Link Protocol 1.

    This Link Protocol used by most devices.

    """
    pid_command_data = 10
    pid_xfer_cmplt = 12
    pid_date_time_data = 14
    pid_position_data = 17
    pid_prx_wpt_data = 19
    pid_records = 27
    pid_enable_async_events = 28
    pid_rte_hdr = 29
    pid_rte_wpt_data = 30
    pid_almanac_data = 31
    pid_trk_data = 34
    pid_wpt_data = 35
    pid_mem_write = 36  # undocumented
    pid_unit_id = 38  # undocumented
    pid_mem_wrdi = 45  # Write Disable (WRDI) undocumented
    pid_baud_rqst_data = 48  # undocumented
    pid_baud_acpt_data = 49  # undocumented
    pid_pvt_data = 51
    pid_screen_data = 69  # undocumented
    pid_mem_wel = 74  # Write Enable Latch (WEL) undocumented
    pid_mem_wren = 75  # Write Enable (WREN) undocumented
    pid_mem_read = 89  # undocumented
    pid_mem_chunk = 90  # undocumented
    pid_mem_records = 91  # undocumented
    pid_mem_data = 92  # undocumented
    pid_capacity_data = 95  # undocumented
    pid_rte_link_data = 98
    pid_trk_hdr = 99
    pid_tx_unlock_key = 108  # undocumented
    pid_ack_unlock_key = 109  # undocumented
    pid_flightbook_record = 134  # packet with FlightBook data
    pid_lap = 149  # part of Forerunner data
    pid_wpt_cat = 152
    pid_baud_data = 252  # undocumented
    pid_image_name_rx = 875
    pid_image_name_tx = 876
    pid_image_list_rx = 877
    pid_image_list_tx = 878
    pid_image_props_rx = 879
    pid_image_props_tx = 880
    pid_image_id_rx = 881
    pid_image_id_tx = 882
    pid_image_data_cmplt = 883
    pid_image_data_rx = 884
    pid_image_data_tx = 885
    pid_color_table_rx = 886
    pid_color_table_tx = 887
    pid_image_type_idx_rx = 888
    pid_image_type_idx_tx = 889
    pid_image_type_name_rx = 890
    pid_image_type_name_tx = 891
    pid_run = 990
    pid_workout = 991
    pid_workout_occurrence = 992
    pid_fitness_user_profile = 993
    pid_workout_limits = 994
    pid_course = 1061
    pid_course_lap = 1062
    pid_course_point = 1063
    pid_course_trk_hdr = 1064
    pid_course_trk_data = 1065
    pid_course_limits = 1066
    pid_external_time_sync_data = 6724


class L002(L000):
    """Link Protocol 2.

    This Link Protocol used by panel-mounted aviation devices.

    """
    pid_almanac_data = 4
    pid_command_data = 11
    pid_xfer_cmplt = 12
    pid_date_time_data = 20
    pid_position_data = 24
    pid_prx_wpt_data = 27
    pid_records = 35
    pid_rte_hdr = 37
    pid_rte_wpt_data = 39
    pid_wpt_data = 43


class A000:
    """Product Data Protocol.

    The Product Data Protocol is used to determine the product data of the
    connected device, which enables the host to determine the protocols
    and data types supported by the device.

    Packet sequence:

    ===== ================ ====================== ==================
       N   Direction        Packet ID              Packet Data Type
    ===== ================ ====================== ==================
       0   Host to Device   pid_product_rqst       ignored
       1   Device to Host   pid_product_data       ProductData
       2   Device to Host   pid_ext_product_data   ExtProductData
       …   …                …                      …
     n-1   Device to Host   pid_ext_product_data   ExtProductData
    ===== ================ ====================== ==================

    """

    def __init__(self, linkLayer):
        self.link = linkLayer

    def get_product_data(self):
        log.info("Request product data...")
        self.link.send_packet(self.link.pid_product_rqst, None)
        log.info("Expect product data")
        packet = self.link.expect_packet(self.link.pid_product_data)
        datatype = ProductData()
        datatype.unpack(packet['data'])
        log.info(f"Product ID: {datatype.product_id}")
        log.info(f"Software version: {datatype.software_version:.2f}")
        log.info(f"Product description: {datatype.product_description.decode()}")

        return datatype


class A001:
    """Protocol capabilities protocol.

    The Protocol Capability Protocol is used by the device to report the
    protocols and data types it supports. When this protocol is supported, it
    will send a list of all supported protocols and data types after completion
    of the A000 Product Data Protocol.

    Packet sequence:

    === ================ ==================== ==================
     N   Direction        Packet ID            Packet Data Type
    === ================ ==================== ==================
     0   Device to Host   pid_protocol_array   ProtocolArray
    === ================ ==================== ==================

    """

    def __init__(self, linkLayer):
        self.link = linkLayer

    def get_protocols(self):
        log.info("Read protocols using Protocol Capability Protocol")
        packet = self.link.expect_packet(self.link.pid_protocol_array)
        protocols = []
        log.info("Parse supported protocols and datatypes...")
        # The order of array elements is used to associate data types with
        # protocols. For example, a protocol that requires two data types <D0>
        # and <D1> is indicated by a tag-encoded protocol ID followed by two
        # tag-encoded data type IDs, where the first data type ID identifies
        # <D0> and the second data type ID identifies <D1>.
        datatype = ProtocolArray()
        datatype.unpack(packet['data'])
        for protocol_data in datatype.get_protocol_data():
            # Format the record to a string consisting of the tag and 3-digit number
            protocol_datatype = str(protocol_data)
            tag = protocol_data.get_tag()
            # Create a list of lists with supported protocols and associated datatypes
            if tag == 'tag_phys_prot_id':
                # We ignore the physical protocol, because it is initialized
                # already
                log.info(f"Got physical protocol '{protocol_datatype}'. Ignoring...")
            elif tag == 'tag_tx_prot_id':
                # Append new list with protocol.
                log.info(f"Got transmission protocol '{protocol_datatype}'. Adding...")
                protocols.append([protocol_datatype])
            elif tag == 'tag_link_prot_id':
                # Append new list with protocol.
                log.info(f"Got link protocol '{protocol_datatype}'. Adding...")
                protocols.append([protocol_datatype])
            elif tag == 'tag_appl_prot_id':
                # Append new list with protocol.
                log.info(f"Got application protocol '{protocol_datatype}'. Adding...")
                protocols.append([protocol_datatype])
            elif tag == 'tag_data_type_id':
                # Append datatype to list of previous protocol
                log.info(f"Got datatype '{protocol_datatype}'. Adding...")
                protocols[-1].append(protocol_datatype)
            else:
                log.info(f"Got unknown protocol or datatype '{protocol_datatype}'. Ignoring...")

        return protocols


class CommandProtocol:
    """Device Command Protocol.

    The Device Command protocols are used to send commands to the device. An
    unimplemented command will not cause an error, but is ignored.

    Packet sequence:

    === ==================== ================== ==================
     N   Direction            Packet ID          Packet Data Type
    === ==================== ================== ==================
     0   Device1 to Device2   pid_command_data   Command
    === ==================== ================== ==================

    """
    cmnd_abort_transfer = None
    cmnd_turn_off_pwr = None

    def __init__(self, link):
        self.link = link

    def abort_transfer(self):
        self.link.send_packet(self.link.pid_command_data,
                              self.cmnd_abort_transfer)

    def turn_power_off(self):
        self.link.send_packet(self.link.pid_command_data,
                              self.cmnd_turn_off_pwr)


class A010(CommandProtocol):
    """Device Command Protocol 1.

    This Device Command Protocol is used by most devices.

    """
    cmnd_abort_transfer = 0                   # abort current transfer
    cmnd_transfer_alm = 1                     # transfer almanac
    cmnd_transfer_posn = 2                    # transfer position
    cmnd_transfer_prx = 3                     # transfer proximity waypoints
    cmnd_transfer_rte = 4                     # transfer routes
    cmnd_transfer_time = 5                    # transfer time
    cmnd_transfer_trk = 6                     # transfer track log
    cmnd_transfer_wpt = 7                     # transfer waypoints
    cmnd_turn_off_pwr = 8                     # turn off power
    cmnd_transfer_unit_id = 14                # transfer product id (undocumented)
    cmnd_transfer_screen = 32                 # transfer screenshot (undocumented)
    cmnd_start_pvt_data = 49                  # start transmitting PVT data
    cmnd_stop_pvt_data = 50                   # stop transmitting PVT data
    cmnd_transfer_baud = 57                   # transfer supported baudrates (undocumented)
    cmnd_ack_ping = 58                        # ping device (undocumented)
    cmnd_transfer_mem = 63                    # transfer memory capacity (undocumented)
    cmnd_flightbook_transfer = 92             # transfer flight records
    cmnd_transfer_laps = 117                  # transfer fitness laps
    cmnd_transfer_wpt_cats = 121              # transfer waypoint categories
    cmnd_transfer_runs = 450                  # transfer fitness runs
    cmnd_transfer_workouts = 451              # transfer workouts
    cmnd_transfer_workout_occurrences = 452   # transfer workout occurrences
    cmnd_transfer_fitness_user_profile = 453  # transfer fitness user profile
    cmnd_transfer_workout_limits = 454        # transfer workout limits
    cmnd_transfer_courses = 561               # transfer fitness courses
    cmnd_transfer_course_laps = 562           # transfer fitness course laps
    cmnd_transfer_course_points = 563         # transfer fitness course points
    cmnd_transfer_course_tracks = 564         # transfer fitness course tracks
    cmnd_transfer_course_limits = 565         # transfer fitness course limits


class A011(CommandProtocol):
    """Device command protocol 2.

    This Device Command Protocol is used by panel-mounted aviation devices.

    """
    cmnd_abort_transfer = 0   # abort current transfer
    cmnd_transfer_alm = 4     # transfer almanac
    cmnd_transfer_rte = 8     # transfer routes
    cmnd_transfer_prx = 17    # transfer proximity waypoints
    cmnd_transfer_time = 20   # transfer time
    cmnd_transfer_wpt = 21    # transfer waypoints
    cmnd_turn_off_pwr = 26    # turn off power


class T001:
    """Transmission Protocol.

    This protocol is undocumented, but it appears to be a transmission protocol
    according to the GPS Manager (gpsman) application
    (https://sourceforge.net/projects/gpsman/).

    This feature is undocumented in the spec. The implementation is derived
    from Appendix C: Changing the baud rate in Garmin mode in the GPS 18x
    Technical Specifications
    (https://static.garmin.com/pumac/GPS_18x_Tech_Specs.pdf)

    """

    def __init__(self, phys, link, command):
        self.phys = phys
        self.link = link
        self.command = command

    @staticmethod
    def desired_baudrate(baudrate):
        """Return the desired baudrate.

        Asynchronous protocols do not allow for much tolerance. The relative baudrate
        error tolerance for UART with 8N1 configuration is only ±5%.

        However, since both transmitter and receiver may not generate the exact
        baudrate, the error must not exceed ±5% in total, which in the worst
        case (one too fast, one too slow) imposes a tight allowed deviation of
        +2.5% and -2.5% on the modules respectively. We therefore choose ±2.5%
        tolerance.

        """
        tolerance = 0.025
        baudrates = (9600, 14400, 19200, 28800, 38400, 57600, 115200, 250000)
        for x in baudrates:
            if math.isclose(baudrate, x, rel_tol=tolerance):
                return x

    def get_supported_baudrates(self):
        log.info("Get supported baudrates...")
        self.link.send_packet(self.link.pid_command_data,
                              self.command.cmnd_transfer_baud)
        packet = self.link.expect_packet(self.link.pid_baud_data)
        baudrates = []
        for baudrate, in rawutil.iter_unpack('<I', packet['data']):
            baudrate = self.desired_baudrate(baudrate)
            if baudrate:
                baudrates.append(baudrate)
        log.info(f"Supported baudrates: {*baudrates, }.")
        return baudrates

    def set_baudrate(self, baudrate):
        """Change the baudrate of the device.

        """
        log.info(f"Change baudrate to {baudrate}...")
        log.info("Turn off async mode")
        self.link.send_packet(self.link.pid_enable_async_events, b'\x00\x00')
        log.info("Request baudrate change")
        data = baudrate.to_bytes(4, byteorder='little')
        self.link.send_packet(self.link.pid_baud_rqst_data,
                              data)
        # The device will respond by sending a packet with the highest
        # acceptable baudrate closest to what was requested
        packet = self.link.expect_packet(self.link.pid_baud_acpt_data)
        baudrate = int.from_bytes(packet['data'], byteorder='little')
        log.info(f"Accepted baudrate: {baudrate}")
        # Determine the desired baudrate value from accepted baudrate
        desired_baudrate = self.desired_baudrate(baudrate)
        if desired_baudrate:
            log.info(f"Desired baudrate: {desired_baudrate}")
            # Set the new baudrate
            log.info(f"Set the baudrate to {desired_baudrate}")
            self.phys.set_baudrate(desired_baudrate)
            try:
                # Immediately after setting the baudrate, transmit an Ack ping packet
                self.link.send_packet(self.link.pid_command_data,
                                      self.command.cmnd_ack_ping)
                # Transmit the same packet again
                self.link.send_packet(self.link.pid_command_data,
                                      self.command.cmnd_ack_ping)
                # The baudrate has been successfully changed upon acknowledging the
                # above two ping packets. If the device does not receive these two
                # packets within two seconds, it will reset its baudrate to the default
                # 9600.
                log.info(f"Baudrate successfully changed to {desired_baudrate}")
            except:
                log.info("Failed to change baudrate")
        else:
            log.warning("Unsupported baudrate {baudrate}")

    def get_baudrate(self):
        return self.phys.get_baudrate()


class TransferProtocol:
    """Transfer protocol.

    The data transfer protocols are used to send data to and receive data from
    the device.

    Many Application protocols use standard beginning and ending packets called
    pid_records and pid_xfer_cmplt, respectively. The first packet indicates the
    number of data packets to follow, excluding the last packet. The last packet
    indicates that the transfer is complete. It also indicates the command ID
    used to initiate the data transfer transfer.

    Some protocols are able to send or receive only one set of data. The packets
    in between (packet 1 through n-2) each contain data records using a
    device-specific data type.

    ===== ==================== ================ ==================
       N   Direction            Packet ID        Packet Data Type
    ===== ==================== ================ ==================
       0   Device1 to Device2   pid_records      Records
       1   Device1 to Device2   <Data Pid>       <D0>
       2   Device1 to Device2   <Data Pid>       <D0>
       …   …                    …                …
     n-2   Device1 to Device2   <Data Pid>       <D0>
     n-1   Device1 to Device2   pid_xfer_cmplt   Command
    ===== ==================== ================ ==================

    Other protocols are able to send or receive multiple sets of data. The
    second packet (packet 1) contains header information that uniquely
    identifies the data. The packets in between (packet 2 through n-2) each
    contain data records using a device-specific data type. More sets of data
    can be transferred by appending another set of packets with header
    information and data records (like packets 1 through n-2).

    ===== ==================== ================ ==================
       N   Direction            Packet ID        Packet Data Type
    ===== ==================== ================ ==================
       0   Device1 to Device2   pid_records      Records
       1   Device1 to Device2   <Header Pid>     <D0>
       2   Device1 to Device2   <Data Pid>       <D1>
       3   Device1 to Device2   <Data Pid>       <D1>
       …   …                    …                …
     n-2   Device1 to Device2   <Data Pid>       <D1>
     n-1   Device1 to Device2   pid_xfer_cmplt   Command
    ===== ==================== ================ ==================

    """

    def __init__(self, link, command, datatypes):
        self.link = link
        self.command = command
        self.datatypes = datatypes

    def get_data(self, cmd, *pids, callback=None):
        self.link.send_packet(self.link.pid_command_data, cmd)
        packet = self.link.expect_packet(self.link.pid_records)
        datatype = Records()
        datatype.unpack(packet['data'])
        packet_count = datatype.records
        log.info(f"{type(self).__name__}: Expecting {packet_count} records")
        result = []
        for idx in range(packet_count):
            packet = self.link.read_packet()
            pid = packet['id']
            data = packet['data']
            i = pids.index(pid)
            datatype = self.datatypes[i]()
            log.info(f"Datatype {type(datatype).__name__}")
            datatype.unpack(data)
            log.info(f"{str(datatype)}")
            if pid in pids:
                result.append(datatype)
            else:
                raise ProtocolError(f"Expected one of {*pids,}, got {pid}")
            if callback:
                callback(datatype, idx+1, packet_count)
        self.link.expect_packet(self.link.pid_xfer_cmplt)

        return result

    def put_data(self, cmd, packets, callback=None):
        packet_count = len(packets)
        log.info(f"{type(self).__name__}: Sending {packet_count} records")
        self.link.send_packet(self.link.pid_records, packet_count)
        for idx, packet in enumerate(packets):
            pid = packet['id']
            datatype = packet['data']
            datatype.pack()
            log.info(f"{str(datatype)}")
            data = datatype.get_data()
            log.debug(f"> packet {pid:3}: {bytes.hex(data, sep=' ')}")
            self.link.send_packet(pid, data)
            if callback:
                callback(datatype, idx+1, packet_count)

        self.link.send_packet(self.link.pid_xfer_cmplt, cmd)


class A100(TransferProtocol):
    """Waypoint Transfer Protocol.

    Packet sequence:

    ===== ==================== ================ ==================
       N   Direction            Packet ID        Packet Data Type
    ===== ==================== ================ ==================
       0   Device1 to Device2   pid_records      Records
       1   Device1 to Device2   pid_wpt_data     <D0>
       2   Device1 to Device2   pid_wpt_data     <D0>
       …   …                    …                …
     n-2   Device1 to Device2   pid_wpt_data     <D0>
     n-1   Device1 to Device2   pid_xfer_cmplt   Command
    ===== ==================== ================ ==================

    """

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.command.cmnd_transfer_wpt,
                                         self.link.pid_wpt_data,
                                         callback=callback)

    def put_data(self, points, callback=None):
        packets = []
        log.info(f"Datatypes: {*[datatype.__name__ for datatype in self.datatypes],}")
        for point in points:
            pid = self.link.pid_wpt_data
            if isinstance(point, Wpt):
                datatype = point
            elif isinstance(point, dict):
                datatype = self.datatypes[0](**point)
            else:
                raise ProtocolError("Invalid class type: expected dict or {datatypes[0].__name__}")
            packet = {'id': pid, 'data': datatype}
            packets.append(packet)

        return TransferProtocol.put_data(self,
                                         self.command.cmnd_transfer_wpt,
                                         packets,
                                         callback=callback)


class A101(TransferProtocol):
    """Waypoint Transfer Protocol.

    Packet sequence:

    ===== ==================== ================ ==================
       N   Direction            Packet ID        Packet Data Type
    ===== ==================== ================ ==================
       0   Device1 to Device2   pid_records      Records
       1   Device1 to Device2   pid_wpt_cat      <D0>
       2   Device1 to Device2   pid_wpt_cat      <D0>
       …   …                    …                …
     n-2   Device1 to Device2   pid_wpt_cat      <D0>
     n-1   Device1 to Device2   pid_xfer_cmplt   Command
    ===== ==================== ================ ==================

    """

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.command.cmnd_transfer_wpt_cats,
                                         self.link.pid_wpt_cat,
                                         callback=callback)

    def put_data(self, categories, callback=None):
        packets = []
        log.info(f"Datatypes: {*[datatype.__name__ for datatype in self.datatypes],}")
        for category in categories:
            pid = self.link.pid_wpt_cat
            if isinstance(point, WptCat):
                datatype = point
            elif isinstance(point, dict):
                datatype = self.datatypes[0](**point)
            else:
                raise ProtocolError("Invalid class type: expected dict or {datatypes[0].__name__}")
            packet = {'id': pid, 'data': datatype}
            packets.append(packet)
        return TransferProtocol.put_data(self,
                                         self.command.cmnd_transfer_wpt_cats,
                                         packets,
                                         callback=callback)


class A200(TransferProtocol):
    """Route Transfer Protocol.

    Packet sequence:

    ===== ==================== ================== ==================
       N   Direction            Packet ID          Packet Data Type
    ===== ==================== ================== ==================
       0   Device1 to Device2   pid_records        Records
       1   Device1 to Device2   pid_rte_hdr        <D0>
       2   Device1 to Device2   pid_rte_wpt_data   <D1>
       3   Device1 to Device2   pid_rte_wpt_data   <D1>
       …   …                    …                  …
     n-2   Device1 to Device2   pid_rte_wpt_data   <D1>
     n-1   Device1 to Device2   pid_xfer_cmplt     Command
    ===== ==================== ================== ==================

    """

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.command.cmnd_transfer_rte,
                                         self.link.pid_rte_hdr,
                                         self.link.pid_rte_wpt_data,
                                         callback=callback)

    def put_data(self, routes, callback=None):
        packets = []
        for route in routes:
            header = route[0]
            points = route[1:]
            pid = self.link.pid_rte_hdr
            if isinstance(header, RteHdr):
                datatype = header
            elif isinstance(header, dict):
                datatype = self.datatypes[0](**header)
            else:
                raise ProtocolError("Invalid class type: expected dict or {datatypes[0].__name__}")
            packet = {'id': pid, 'data': datatype}
            packets.append(packet)
            for point in points:
                pid = self.link.pid_rte_wpt_data
                if isinstance(point, Wpt):
                    datatype = point
                elif isinstance(point, dict):
                    datatype = self.datatypes[0](**point)
                else:
                    raise ProtocolError("Invalid class type: expected dict or {datatypes[0].__name__}")
                packet = {'id': pid, 'data': datatype}
                packets.append(packet)

        return TransferProtocol.put_data(self,
                                         self.command.cmnd_transfer_rte,
                                         packets,
                                         callback=callback)


class A201(TransferProtocol):
    """Route Transfer Protocol.

    Packet sequence:

    ===== ==================== =================== ==================
       N   Direction            Packet ID           Packet Data Type
    ===== ==================== =================== ==================
       0   Device1 to Device2   pid_records         Records
       1   Device1 to Device2   pid_rte_hdr         <D0>
       2   Device1 to Device2   pid_rte_wpt_data    <D1>
       3   Device1 to Device2   pid_rte_link_data   <D2>
       4   Device1 to Device2   pid_rte_wpt_data    <D1>
       5   Device1 to Device2   pid_rte_link_data   <D2>
       …   …                    …                   …
     n-2   Device1 to Device2   pid_rte_wpt_data    <D1>
     n-1   Device1 to Device2   pid_xfer_cmplt      Command
    ===== ==================== =================== ==================

    """

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.command.cmnd_transfer_rte,
                                         self.link.pid_rte_hdr,
                                         self.link.pid_rte_wpt_data,
                                         self.link.pid_rte_link_data,
                                         callback=callback)

    def put_data(self, routes, callback=None):
        packets = []
        for point in routes:
            header = route[0]
            points = route[1:]
            pid = self.link.pid_rte_hdr
            datatype = self.datatypes[0](**header)
            packet = {'id': pid, 'data': datatype}
            packets.append(packet)
            is_even = lambda x: x % 2 == 0
            for idx, point in enumerate(points):
                if is_even(idx):
                    pid = self.link.pid_rte_wpt_data
                else:
                    pid = self.link.pid_rte_link_data
                datatype = self.datatypes[idx+1](**point)
                packet = {'id': pid, 'data': datatype}
                packets.append(packet)
        return TransferProtocol.put_data(self,
                                         self.command.cmnd_transfer_rte,
                                         packets,
                                         callback=callback)


class A300(TransferProtocol):
    """Track Log Transfer Protocol.

    Packet sequence:

    ===== ==================== ================ ==================
       N   Direction            Packet ID        Packet Data Type
    ===== ==================== ================ ==================
       0   Device1 to Device2   pid_records      Records
       1   Device1 to Device2   pid_trk_data     <D0>
       2   Device1 to Device2   pid_trk_data     <D0>
       …   …                    …                …
     n-2   Device1 to Device2   pid_trk_data     <D0>
     n-1   Device1 to Device2   pid_xfer_cmplt   Command
    ===== ==================== ================ ==================

    """

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.command.cmnd_transfer_trk,
                                         self.link.pid_trk_data,
                                         callback=callback)

    def put_data(self, points, callback=None):
        packets = []
        for point in points:
            pid = self.link.pid_trk_data
            if isinstance(point, TrkPoint):
                datatype = point
            elif isinstance(point, dict):
                datatype = self.datatypes[0](**point)
            else:
                raise ProtocolError("Invalid class type: expected dict or {datatypes[0].__name__}")
            packet = (pid, datatype)
            packets.append(packet)

        return TransferProtocol.put_data(self,
                                         self.command.cmnd_transfer_trk,
                                         packets,
                                         callback=callback)


class A301(TransferProtocol):
    """Track Log Transfer Protocol.

    Packet sequence:

    ===== ==================== ================ ==================
       N   Direction            Packet ID        Packet Data Type
    ===== ==================== ================ ==================
       0   Device1 to Device2   pid_records      Records
       1   Device1 to Device2   pid_trk_hdr      <D0>
       2   Device1 to Device2   pid_trk_data     <D1>
       3   Device1 to Device2   pid_trk_data     <D1>
       …   …                    …                …
     n-2   Device1 to Device2   pid_trk_data     <D1>
     n-1   Device1 to Device2   pid_xfer_cmplt   Command
    ===== ==================== ================ ==================

    """

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.command.cmnd_transfer_trk,
                                         self.link.pid_trk_hdr,
                                         self.link.pid_trk_data,
                                         callback=callback)

    def put_data(self, tracks, callback=None):
        packets = []
        for track in tracks:
            header = track[0]
            points = track[1:]
            pid = self.link.pid_trk_hdr
            if isinstance(header, TrkHdr):
                datatype = header
            elif isinstance(header, dict):
                datatype = self.datatypes[0](**header)
            else:
                raise ProtocolError("Invalid class type: expected dict or {datatypes[0].__name__}")
            packet = (pid, datatype)
            packets.append(packet)
            for point in points:
                pid = self.link.pid_trk_data
                if isinstance(point, TrkPoint):
                    datatype = point
                elif isinstance(point, dict):
                    datatype = self.datatypes[1](**point)
                else:
                    raise ProtocolError("Invalid class type: expected dict or {datatypes[1].__name__}")
                packet = (pid, datatype)
                packets.append(packet)

        return TransferProtocol.put_data(self,
                                         self.command.cmnd_transfer_trk,
                                         packets,
                                         callback=callback)


class A302(A301):
    """Track Log Transfer Protocol.

    The A302 Track Log Transfer Protocol is used in fitness devices to transfer
    tracks from the device to the Host. The packet sequence for the protocol is
    identical to A301, except that the Host may only receive tracks from the
    device, and not send them.

    """

    def put_data(self, tracks, callback=None):
        pass


class A400(TransferProtocol):
    """Proximity Waypoint Transfer Protocol.

    Packet sequence:

    ===== ==================== ================== ==================
       N   Direction            Packet ID          Packet Data Type
    ===== ==================== ================== ==================
       0   Device1 to Device2   pid_records        Records
       1   Device1 to Device2   pid_prx_wpt_data   <D0>
       2   Device1 to Device2   pid_prx_wpt_data   <D0>
       …   …                    …                  …
     n-2   Device1 to Device2   pid_prx_wpt_data   <D0>
     n-1   Device1 to Device2   pid_xfer_cmplt     Command
    ===== ==================== ================== ==================

    """

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.command.cmnd_transfer_prx,
                                         self.link.pid_prx_wpt_data,
                                         callback=callback)

    def put_data(self, points, callback=None):
        packets = []
        for point in points:
            pid = self.link.pid_prx_wpt_data
            if isinstance(point, PrxWpt):
                datatype = point
            elif isinstance(point, dict):
                datatype = self.datatypes[0](**point)
            else:
                raise ProtocolError("Invalid class type: expected dict or {datatypes[0].__name__}")
            packet = {'id': pid, 'data': datatype}
            packets.append(packet)

        return TransferProtocol.put_data(self,
                                         self.command.cmnd_transfer_prx,
                                         packets,
                                         callback=callback)


class A500(TransferProtocol):
    """Almanac Transfer Protocol.

    Packet sequence:

    ===== ==================== ================== ==================
       N   Direction            Packet ID          Packet Data Type
    ===== ==================== ================== ==================
       0   Device1 to Device2   pid_records        Records
       1   Device1 to Device2   pid_almanac_data   <D0>
       2   Device1 to Device2   pid_almanac_data   <D0>
       …   …                    …                  …
     n-2   Device1 to Device2   pid_almanac_data   <D0>
     n-1   Device1 to Device2   pid_xfer_cmplt     Command
    ===== ==================== ================== ==================

    Some device-specific data types do not include a satellite ID to relate each
    data packet to a particular satellite in the GPS constellation. For these
    data types, the order of the 32 pid_almanac_data packets corresponds to PRN
    order (i.e., the first packet contains data for PRN-01 and so on up to
    PRN-32).

    """

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.command.cmnd_transfer_alm,
                                         self.link.pid_almanac_data,
                                         callback=callback)


class A600(TransferProtocol):
    """Date and Time Initialization Protocol.

    Packet sequence:

    === ==================== ==================== ==================
     N   Direction            Packet ID            Packet Data Type
    === ==================== ==================== ==================
     0   Device1 to Device2   pid_date_time_data   <D0>
    === ==================== ==================== ==================

    """

    def get_data(self, callback=None):
        self.link.send_packet(self.link.pid_command_data,
                              self.command.cmnd_transfer_time)
        packet = self.link.expect_packet(self.link.pid_date_time_data)
        datatype = self.datatypes[0]()
        datatype.unpack(packet['data'])
        if callback:
            callback(datatype, 1, 1)

        return datatype


class A601(TransferProtocol):
    """A601 implementation.

    Used by GPSmap 60cs, no specifications as of 2004-09-26."""


class A650(TransferProtocol):
    """Flightbook Transfer Protocol.

    Packet sequence:

    ===== ================ ======================= ==================
       N   Direction        Packet ID               Packet Data Type
    ===== ================ ======================= ==================
       0   Host to Device   pid_command_data        Command
       1   Device to Host   pid_records             Records
       2   Device to Host   pid_flightbook_record   <D0>
       …   …                …                       …
     n-2   Device to Host   pid_flightbook_record   <D0>
     n-1   Device to Host   pid_xfer_cmplt          Command
    ===== ================ ======================= ==================

    """

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.command.cmnd_flightbook_transfer,
                                         self.link.pid_flightbook_record,
                                         callback=callback)


class A700(TransferProtocol):
    """Position initialisation protocol.

    Packet sequence:

     === ==================== =================== ==================
      N   Direction            Packet ID           Packet Data Type
     === ==================== =================== ==================
      0   Device1 to Device2   pid_position_data   <D0>
     === ==================== =================== ==================

    """

    def get_data(self, callback=None):
        self.link.send_packet(self.link.pid_command_data,
                              self.command.cmnd_transfer_posn)
        packet = self.link.expect_packet(self.link.pid_position_data)
        datatype = self.datatypes[0]()
        datatype.unpack(packet['data'])
        if callback:
            callback(datatype, 1, 1)

        return datatype


class A800(TransferProtocol):
    """PVT Data Protocol.

    In PVT mode the device will transmit packets once per second with real-time
    position, velocity, and time. This protocol is used as an alternative to
    NMEA (https://www.nmea.org/content/STANDARDS/STANDARDS).

    PVT mode can be switched on and off by sending the cmnd_start_pvt_data and
    cmnd_stop_pvt_data command.

    According to the specification the ACK and NAK packets are optional, but the
    device will not retransmit a PVT packet in response to receiving a NAK.

    Packet sequence:

    === =================================== ============== ==================
     N   Direction                           Packet ID      Packet Data Type
    === =================================== ============== ==================
     0   Device to Host (ACK/NAK optional)   pid_pvt_data   <D0>
    === =================================== ============== ==================

    """

    def data_on(self):
        self.link.send_packet(self.link.pid_command_data,
                              self.command.cmnd_start_pvt_data)

    def data_off(self):
        self.link.send_packet(self.link.pid_command_data,
                              self.command.cmnd_stop_pvt_data)

    def get_data(self, callback=None):
        packet = self.link.expect_packet(self.link.pid_pvt_data)
        datatype = self.datatypes[0]()
        datatype.unpack(packet['data'])
        if callback:
            callback(datatype, 1, 1)

        return datatype


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

    This protocol is undocumented, but it appears to be a map transfer protocol.
    The implementation is derived from the GarminDev drivers of the abandoned
    QLandkarteGT application (https://sourceforge.net/projects/qlandkartegt/)
    and the sendmap application included with the also abandoned cGPSmapper
    application (https://sourceforge.net/projects/cgpsmapper/).

    On devices without mass storage mode, maps are stored in the internal flash
    memory of the device. Some of the memory regions are:

    ======== ====== ============================== ==============
     Region    Hex   Map Name                       Filename
    ======== ====== ============================== ==============
          3   0x03   Device Base Map                gmapbmap.img
         10   0x0a   Supplementary map              gmapsupp.img
         14   0x0e   Firmware/System Software       fw_all.bin
         16   0x10   Logo/Splash Screen             logo.bin
         49   0x31   Primary or Pre Installed Map   gmapprom.img
         50   0x32   OEM Installed Map              gmapoem.img
    ======== ====== ============================== ==============

    These regions are derived from the Garmin RGN firmware update file format
    (confusingly, the RGN subfiles within Garmin IMG files share the same name,
    but have a completely different structure and purpose). The file format is
    reverse engineered by Herbert Oppmann
    (https://www.memotech.franken.de/FileFormats/Garmin_RGN_Format.pdf). This
    protocol only seems to be able to access region 10 with the supplementary
    map.

    The terminology of the commands below is taken from SPI interfaces for
    serial flash memory that are used elsewhere. Before any write operation, the
    write enable command WREN must be issued. Sending the WREN sets the internal
    write enable latch, which is indicated by the WEL response. The write
    disable command WRDI clears it.

    Packet sequence:

    ===== ================ =============== ==================
       N   Direction        Packet ID       Packet Data Type
    ===== ================ =============== ==================
       0   Host to Device   pid_mem_wren    Region
       1   Device to Host   pid_mem_wel
       2   Device to Host   pid_mem_write   MemChunk
       …   …                …               …
     n-2   Device to Host   pid_mem_write   MemChunk
     n-1   Device to Host   pid_mem_wrdi    Region
    ===== ================ =============== ==================

    """

    def __init__(self, link, command):
        self.link = link
        self.command = command

    @cached_property
    def memory_properties(self):
        return self.get_memory_properties()

    def get_memory_properties(self):
        log.info("Request capacity data...")
        self.link.send_packet(self.link.pid_command_data,
                              self.command.cmnd_transfer_mem)
        log.info("Expect capacity data")
        packet = self.link.expect_packet(self.link.pid_capacity_data)
        datatype = MemProperties()
        datatype.unpack(packet['data'])
        mem_size = datatype.mem_size
        log.info(f"Memory size: {mem_size} bytes")
        return datatype

    def _read_memory(self, filename='', callback=None):
        log.info("Get memory data...")
        mem_region = self.memory_properties.mem_region
        datatype = MemFile(mem_region=mem_region, subfile=filename)
        datatype.pack()
        data = datatype.get_data()
        self.link.send_packet(self.link.pid_mem_read, data)
        packet = self.link.read_packet()
        pid = packet['id']
        if pid == self.link.pid_mem_data:
            datatype = MemData()
            datatype.unpack(packet['data'])
            if int.from_bytes(datatype.data, byteorder='little') == 0:
                log.info("Data not found")
            else:
                log.info(f"Got unknown data {datatype.data}. Ignoring...")
        elif pid == self.link.pid_mem_records:
            # The Records contains a 32-bit integer that indicates the number
            # of data packets to follow.
            datatype = Records()
            datatype.unpack(packet['data'])
            packet_count = datatype.records
            log.info(f"{type(self).__name__}: Expecting {packet_count} records")
            data = bytes()
            for idx in range(packet_count):
                packet = self.link.expect_packet(self.link.pid_mem_chunk)
                datatype = MemRecord()
                datatype.unpack(packet['data'])
                data += datatype.chunk
                if callback:
                    callback(datatype, idx+1, packet_count)
            return data

    def _write_file(self, file, chunk_size=250, callback=None):
        log.info(f"Upload map {file}")
        file_size = os.path.getsize(file)
        with open(file, 'rb') as f:
            while True:
                offset = f.tell()
                chunk = f.read(chunk_size)
                if not chunk:  # EOF reached
                    break
                datatype = MemChunk(offset, chunk)
                datatype.pack()
                data = datatype.get_data()
                log.debug(f"Upload {offset+len(chunk)}/{file_size} bytes")
                self.link.send_packet(self.link.pid_mem_write, data)
                if callback:
                    callback(datatype, offset+len(chunk), file_size)

    def _write_handle(self, handle, chunk_size=250, callback=None):
        log.info(f"Upload map {handle.name}")
        handle.seek(0, os.SEEK_END)
        file_size = handle.tell()
        handle.seek(0, os.SEEK_SET)
        while True:
            offset = handle.tell()
            chunk = handle.read(chunk_size)
            if not chunk:  # EOF reached
                break
            datatype = MemChunk(offset, chunk)
            datatype.pack()
            data = datatype.get_data()
            log.debug(f"Upload {offset+len(chunk)}/{file_size} bytes")
            self.link.send_packet(self.link.pid_mem_write, data)
            if callback:
                callback(datatype, offset+len(chunk), file_size)

    def _write_bytes(self, bytes, chunk_size=250, callback=None):
        log.info(f"Upload map")
        file_size = len(bytes)
        offsets = range(0, file_size, chunk_size)
        for offset in offsets:
            chunk = bytes[offset:offset+chunk_size]
            datatype = MemChunk(offset, chunk)
            datatype.pack()
            data = datatype.get_data()
            log.debug(f"Upload {offset+len(chunk)}/{file_size} bytes")
            self.link.send_packet(self.link.pid_mem_write, data)
            if callback:
                callback(datatype, offset+len(chunk), file_size)

    def _write_memory(self, data, chunk_size=250, callback=None):
        mem_region = self.memory_properties.mem_region
        log.info("Turn off async mode")
        self.link.send_packet(self.link.pid_enable_async_events, b'\x00\x00')
        log.info("Enable write")
        self.link.send_packet(self.link.pid_mem_wren, mem_region)
        self.link.expect_packet(self.link.pid_mem_wel)
        log.info("Write enabled")
        if data is None:
            log.info("Delete map...")
            pass
        elif isinstance(data, str):
            self._write_file(data, chunk_size, callback)
        elif isinstance(data, io.BufferedReader):
            self._write_handle(data, chunk_size, callback)
        elif isinstance(data, bytes):
            self._write_bytes(data, chunk_size, callback)
        log.info("Disable write")
        self.link.send_packet(self.link.pid_mem_wrdi, mem_region)

    def get_map_properties(self):
        log.info("Get map properties...")
        filenames = ("MAKEGMAP.MPS", "MAPSOURC.MPS", "BLUCHART.MPS")
        for filename in filenames:
            data = self._read_memory(filename=filename)
            if data is not None:
                datatype = MPSFile()
                datatype.unpack(data)
                records = datatype.get_records()
                result = [ record.get_content() for record in records ]
                return result

    def get_map(self, callback=None):
        log.info("Download map...")
        data = self._read_memory(filename='', callback=callback)
        if data is not None:
            return data


class A902:
    """A902 implementation.

    This protocol is undocumented, but it appears to be a map unlock protocol.
    The implementation is derived from the GarminDev drivers of the abandoned
    QLandkarteGT application (https://sourceforge.net/projects/qlandkartegt/)
    and the also abandoned sendmap application included with the cGPSmapper
    application (https://sourceforge.net/projects/cgpsmapper/).

    """

    def __init__(self, link, command):
        self.link = link
        self.command = command

    def send_unlock_key(self, key):
        data = bytes(key)
        log.info("Send unlock key")
        self.link.send_packet(self.link.pid_tx_unlock_key,
                              data)
        log.info("Acknowledge unlock key")
        self.link.expect_packet(self.link.pid_ack_unlock_key)
        # TODO: read data


class A903:
    """A903 implementation.

    Used by etrex, no documentation as of 2001-05-30.
    """


class A904:
    """A904 implementation.

    This protocol is undocumented, but it appears to be a routable protocol. No
    implementation as of yet.

    """


class ImageTransfer:
    """Image transfer protocol.

    With the image transfer protocol a screenshot and custom waypoint icons can
    be downloaded. The latter can also be uploaded. This protocol is
    undocumented. The implementation is derived from the GarminDev drivers of
    the abandoned QLandkarteGT application
    (https://sourceforge.net/projects/qlandkartegt/) and by reverse-engineering
    the Garmin xImage utility
    (https://www8.garmin.com/support/download_details.jsp?id=545). Compatible
    devices include the Garmin GPSMAP 60CX/60CSX, eTrex Legend C, eTrex Vista C,
    GPSMAP 60C/60CS, GPSMAP 76C/76CS. Some devices, like the 60C and 76C,
    originally didn’t support custom waypoint icons, but later it was added with
    a firmware update.

    """

    def __init__(self, link, command):
        self.link = link
        self.command = command


    def get_image_types(self):
        log.info("Request image types")
        self.link.send_packet(self.link.pid_image_type_idx_rx, None)
        packet = self.link.expect_packet(self.link.pid_image_type_idx_tx)
        indices = list(packet['data'])
        log.info("Request image type names")
        image_types = list()
        for idx in indices:
            self.link.send_packet(self.link.pid_image_type_name_rx, idx)
            packet = self.link.expect_packet(self.link.pid_image_type_name_tx)
            datatype = ImageName()
            datatype.unpack(packet['data'])
            name = datatype.name.decode()
            log.info(f"Image type name: {name}")
            image_types.append({'idx': idx, 'name': name})
        return image_types

    def get_image_list(self):
        log.info("Request image list")
        self.link.send_packet(self.link.pid_image_list_rx, None)
        packet = self.link.expect_packet(self.link.pid_image_list_tx)
        datatype = ImageList()
        datatype.unpack(packet['data'])
        images = list()
        for image in datatype.get_images():
            idx = image.idx
            image_dict = image.get_dict()
            log.info("Request image name")
            self.link.send_packet(self.link.pid_image_name_rx, idx)
            packet = self.link.expect_packet(self.link.pid_image_name_tx)
            datatype = ImageName()
            datatype.unpack(packet['data'])
            name = datatype.name.decode()
            log.info(f"Image name: {name}")
            image_dict['name'] = name
            images.append(image_dict)
        return images

    def get_image(self, idx=None, callback=None):
        log.info("Turn off async mode")
        self.link.send_packet(self.link.pid_enable_async_events, b'\x00\x00')
        log.info("Request image properties")
        self.link.send_packet(self.link.pid_image_props_rx, idx)
        packet = self.link.expect_packet(self.link.pid_image_props_tx)
        if not packet['data']:
            raise ValueError(f"Invalid symbol index {idx}")
        datatype = ImageInformationHeader()
        datatype.unpack(packet['data'])
        dimensions = datatype.get_dimensions()
        pixel_size = datatype.get_size()
        colors_used = datatype.get_colors_used()
        log.info(f"Dimensions: {'x'.join(map(str, dimensions))} pixels")
        log.info(f"Size: {pixel_size} bytes")
        log.info(f"Bits per pixel: {datatype.bpp}")
        log.info(f"Colors used: {colors_used}")
        if colors_used is None or colors_used == 0:
            raise GarminError("Images without a color palette are not supported")
        log.info("Request image ID")
        self.link.send_packet(self.link.pid_image_id_rx, idx)
        packet = self.link.expect_packet(self.link.pid_image_id_tx)
        receive = ImageId()
        receive.unpack(packet['data'])
        log.info(f"Image ID: {receive.id}")
        log.info(f"Request color table for image ID {receive.id}")
        # The color table is sent in one packet, consisting of 4 bytes for the
        # id, and 4 bytes per color.
        color_table_size = colors_used * 4 + 4
        # The pixel data is sent in chunks, with a packet data size of maximum
        # 500 bytes, consisting of 4 bytes for the id and maximum 496 bytes for
        # the chunk of pixel data. Finally, a packet with only the 4 byte id is
        # sent.
        max_chunk_size = 496
        chunk_count = math.ceil(pixel_size / max_chunk_size)
        pixel_data_size = chunk_count * 4 + pixel_size + 4
        total_bytes = color_table_size + pixel_data_size
        received_bytes = 0
        self.link.send_packet(self.link.pid_color_table_rx, receive.get_data())
        packet = self.link.expect_packet(self.link.pid_color_table_tx)
        received_bytes += len(packet['data'])
        if callback:
            callback(datatype, received_bytes, total_bytes)
        datatype = ImageColorTable()
        datatype.unpack(packet['data'])
        palette = datatype.get_palette()
        log.info(f"Request pixel data for image ID {receive.id}")
        pixel_data = bytes()
        while True:
            self.link.send_packet(self.link.pid_image_data_rx, receive.get_data())
            packet = self.link.expect_packet(self.link.pid_image_data_tx)
            received_bytes += len(packet['data'])
            datatype = ImageChunk()
            datatype.unpack(packet['data'])
            if callback:
                callback(datatype, received_bytes, total_bytes)
            if not datatype.data:
                break
            else:
                pixel_data += datatype.data
        log.info(f"Completed request pixel data for image ID {receive.id}")
        self.link.send_packet(self.link.pid_image_data_cmplt, receive.get_data())
        log.info("Create image from pixel data")
        image = PIL.Image.frombytes(mode='P', size=dimensions, data=pixel_data, decoder_name='raw')
        log.info("Attach palette to image")
        image.putpalette(palette, rawmode='RGB')
        return image.transpose(method=PIL.Image.Transpose.ROTATE_180)

    def put_image(self, idx=None, image=None, callback=None):
        log.info("Turn off async mode")
        self.link.send_packet(self.link.pid_enable_async_events, b'\x00\x00')
        log.info("Request image properties")
        self.link.send_packet(self.link.pid_image_props_rx, idx)
        packet = self.link.expect_packet(self.link.pid_image_props_tx)
        if not packet['data']:
            raise ValueError(f"Invalid symbol index {idx}")
        datatype = ImageInformationHeader()
        datatype.unpack(packet['data'])
        dimensions = datatype.get_dimensions()
        pixel_size = datatype.get_size()
        bpp = datatype.bpp
        colors_used = datatype.get_colors_used()
        log.info(f"Dimensions: {'x'.join(map(str, dimensions))} pixels")
        log.info(f"Size: {pixel_size} bytes")
        log.info(f"Bits per pixel: {bpp}")
        log.info(f"Colors used: {colors_used}")
        if colors_used is None or colors_used == 0:
            raise GarminError("Images without a color palette are not supported")
        log.info("Request image ID")
        self.link.send_packet(self.link.pid_image_id_rx, idx)
        packet = self.link.expect_packet(self.link.pid_image_id_tx)
        transmit = ImageId()
        transmit.unpack(packet['data'])
        log.info(f"Image ID: {transmit.id}")
        log.info(f"Request color table for image ID {transmit.id}")
        self.link.send_packet(self.link.pid_color_table_rx, transmit.get_data())
        packet = self.link.expect_packet(self.link.pid_color_table_tx)
        datatype = ImageColorTable()
        datatype.unpack(packet['data'])
        palette = datatype.get_palette()
        # The color table is sent in one packet, consisting of 4 bytes for the
        # id, and 4 bytes per color.
        color_table_size = colors_used * 4 + 4
        # The pixel data is sent in chunks, with a packet data size of maximum
        # 500 bytes, consisting of 4 bytes for the id and maximum 496 bytes for
        # the chunk of pixel data. Finally, a packet with only the 4 byte id is
        # sent.
        max_chunk_size = 496
        chunk_count = math.ceil(pixel_size / max_chunk_size)
        pixel_data_size = chunk_count * 4 + pixel_size + 4
        total_bytes = color_table_size + pixel_data_size
        sent_bytes = 0
        log.info(f"Send color table for image ID {transmit.id}")
        # Use the just received color table of the existing image
        data = datatype.get_data()
        self.link.send_packet(self.link.pid_color_table_tx, data)
        sent_bytes += len(data)
        if callback:
            callback(datatype, sent_bytes, total_bytes)
        packet = self.link.expect_packet(self.link.pid_color_table_rx)
        receive = ImageId()
        receive.unpack(packet['data'])
        if receive.id != transmit.id:
            raise ProtocolError(f"Expected {transmit.id}, got {receive.id}")
        out = image.transpose(method=PIL.Image.Transpose.ROTATE_180)
        if out.mode in ('RGBA', 'LA','PA'):
            log.info(f"Replace the alpha channel with magenta as transparency color")
            color=(255, 0, 255)
            alpha = out.getchannel('A')
            # convert semi-transparent pixels to black and white
            mask = out.convert(mode='1')
            background = PIL.Image.new('RGB', out.size, color)
            background.paste(out, mask=mask)
            out = background
        if out.size != dimensions:
            log.info(f"Resize image to {'x'.join(map(str, dimensions))} pixels")
            out = out.resize(dimensions)
        if not (out.mode == 'P' and out.palette == palette):
            log.info(f"Convert image to {bpp}-bit RGB format")
            out = out.convert(mode='RGB')
            log.info(f"Quantize image to the received color palette.")
            new_image = PIL.Image.new('P', dimensions)
            new_palette = PIL.ImagePalette.ImagePalette(palette=palette)
            new_image.putpalette(new_palette)
            out = out.quantize(colors=colors_used, palette=new_image)
        pixel_data = out.tobytes()
        log.info(f"Send pixel data for image ID {transmit.id}")
        datatype = ImageChunk(transmit.id, pixel_data)
        datatype.pack()
        data = datatype.get_data()
        self.link.send_packet(self.link.pid_image_data_tx, data)
        sent_bytes += len(data)
        if callback:
            callback(datatype, sent_bytes, total_bytes)
        packet = self.link.expect_packet(self.link.pid_image_data_rx)
        receive = ImageId()
        receive.unpack(packet['data'])
        if receive.id != transmit.id:
            raise ProtocolError(f"Expected {transmit.id}, got {receive.id}")
        log.info(f"Completed send pixel data for image ID {transmit.id}")
        self.link.send_packet(self.link.pid_image_data_cmplt, transmit.get_data())
        sent_bytes += len(transmit.get_data())
        if callback:
            callback(transmit, sent_bytes, total_bytes)


class ScreenshotTransfer:

    def __init__(self, link, command):
        self.link = link
        self.command = command

    def get_image(self, callback=None):
        log.info("Request screenshot...")
        self.link.send_packet(self.link.pid_command_data, self.command.cmnd_transfer_screen)
        log.info("Expect screen data")
        packet = self.link.expect_packet(self.link.pid_screen_data)
        datatype = ScreenshotHeader()
        datatype.unpack(packet['data'])
        dimensions = datatype.get_dimensions()
        pixel_size = datatype.get_size()
        colors_used = datatype.get_colors_used()
        log.info(f"Dimensions: {'x'.join(map(str, dimensions))} pixels")
        log.info(f"Size: {pixel_size} bytes")
        log.info(f"Bits per pixel: {datatype.bpp}")
        log.info(f"Colors used: {colors_used}")
        if colors_used is None or colors_used == 0:
            raise GarminError("Screenshots without a color palette are not supported")
        # The color table is sent per color, so each packet data size is 11
        # bytes, consisting of 4 bytes for the section, 4 bytes for the offset,
        # and 3 bytes for the color.
        color_table_size = colors_used * 11
        # The pixel data is sent per row, "bottom-up", with a packet data size
        # of maximum 136 bytes, consisting of 4 bytes for the section, 4 bytes
        # for the offset, and maximum 128 bytes for the chunk of pixel data.
        max_chunk_size = 128
        chunk_count = math.ceil(datatype.width / max_chunk_size)
        row_size = chunk_count * 8 + datatype.width
        pixel_data_size = row_size * datatype.height
        total_bytes = color_table_size + pixel_data_size
        received_bytes = 0
        log.info("Expect color table")
        color_table = bytes()
        while received_bytes < color_table_size:
            packet = self.link.expect_packet(self.link.pid_screen_data)
            datatype = ScreenshotChunk()
            datatype.unpack(packet['data'])
            section = datatype.get_section()
            if section == 'color_table':
                color_table += datatype.chunk
                received_bytes += len(packet['data'])
                if callback:
                    callback(datatype, received_bytes, total_bytes)
            else:
                raise ProtocolError(f"Invalid section: expected color_table, got {section}")
        log.info("Expect pixel data")
        pixel_data = bytes()
        while received_bytes < total_bytes:
            packet = self.link.expect_packet(self.link.pid_screen_data)
            datatype = ScreenshotChunk()
            datatype.unpack(packet['data'])
            section = datatype.get_section()
            if section == 'pixel_data':
                pixel_data += datatype.chunk
                received_bytes += len(packet['data'])
                if callback:
                    callback(datatype, received_bytes, total_bytes)
            else:
                raise ProtocolError(f"Invalid section: expected pixel_data, got {section}")
        image = PIL.Image.frombytes(mode='P', size=dimensions, data=pixel_data, decoder_name='raw')
        image.putpalette(color_table, rawmode='BGR')
        return image.transpose(method=PIL.Image.Transpose.ROTATE_180)


class A906(TransferProtocol):
    """Lap Transfer Protocol.

    Packet sequence:

    ===== ================ ================ ==================
       N   Direction        Packet ID        Packet Data Type
    ===== ================ ================ ==================
       0   Device to Host   pid_records      Records
       1   Device to Host   pid_lap          <D0>
       2   Device to Host   pid_lap          <D0>
       …   …                …                …
     n-2   Device to Host   pid_lap          <D0>
     n-1   Device to Host   pid_xfer_cmplt   Command
    ===== ================ ================ ==================

    """

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.command.cmnd_transfer_laps,
                                         self.link.pid_lap,
                                         callback=callback)


class A1000(TransferProtocol):
    """Run Transfer Protocol.

    Packet sequence:

    ===== ================ ================== ==================
       N   Direction        Packet ID          Packet Data Type
    ===== ================ ================== ==================
       0   Host to Device   pid_command_data   Command
       1   Device to Host   pid_records        Records
       2   Device to Host   pid_run            <D0>
       …   …                …                  …
     k-2   Device to Host   pid_run            <D0>
     k-1   Device to Host   pid_xfer_cmplt     Command
       k   Host to Device   pid_command_data   Command
     k+1   Device to Host   pid_records        Records
     k+2   Device to Host   pid_lap            Lap
       …   …                …                  …
     m-2   Device to Host   pid_lap            Lap
     m-1   Device to Host   pid_xfer_cmplt     Command
       m   Host to Device   pid_command_data   Command
     m+1   Device to Host   pid_records        Records
     m+2   Device to Host   pid_trk_hdr        TrkHdr
     m+3   Device to Host   pid_trk_data       TrkPoint
       …   …                …                  …
     n-2   Device to Host   pid_trk_data       TrkPoint
     n-1   Device to Host   pid_xfer_cmplt     Command
    ===== ================ ================== ==================

    """

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.command.cmnd_transfer_runs,
                                         self.link.pid_run,
                                         callback=callback)


class DataType():
    byteorder = 'little'
    data = bytes()
    epoch = datetime(1989, 12, 31, 12, 0)  # 12:00 am December 31, 1989 UTC
    re_upcase_digit = r'[A-Z0-9]'
    re_upcase_digit_space = r'[A-Z0-9 ]'
    re_upcase_digit_space_hyphen = r'[A-Z0-9 _]'
    re_ascii = r'[\x20-\x7E]'

    @classmethod
    def get_keys(cls):
        keys = list(zip(*cls._fields))[0]
        return keys

    @classmethod
    def get_format(cls):
        fmt_chars = list(zip(*cls._fields))[1]
        fmt = ' '.join(fmt_chars)
        return fmt

    @classmethod
    def get_struct(cls):
        struct = rawutil.Struct(cls.get_format(),
                                names=cls.get_keys())
        struct.setbyteorder(cls.byteorder)
        return struct

    def get_dict(self):
        keys = self.get_keys()
        return {key: self.__dict__.get(key) for key in keys}

    def get_values(self):
        return list(self.get_dict().values())

    def get_data(self):
        return self.data

    def unpack(self, data):
        struct = self.get_struct()
        values = struct.unpack(data)
        self.data = data
        self.__dict__.update(values._asdict())

    def pack(self):
        struct = self.get_struct()
        values = self.get_values()
        self.data = struct.pack(*values)

    def is_valid_charset(self, pattern, bytes):
        string = bytes.decode()
        matches = [re.search(pattern, char) for char in string]
        return all(matches)

    def __str__(self):
        return str(self.get_dict())

    def __repr__(self):
        keys = self.get_keys()
        values = map(str, self.get_values())
        kwargs = ', '.join(map('='.join, zip(keys, values)))
        return f"{self.__class__.__name__}({kwargs})"


class Records(DataType):
    """The Records type contains a 16-bit integer that indicates the number of data
    packets to follow, excluding the pid_xfer_cmplt packet.

    """
    _fields = [('records', 'H'),  # number of data packets to follow
               ]


class ProductData(DataType):
    # The product description contains one or more null-terminated strings.
    # According to the specification, only the first string is used, and all
    # subsequent strings should be ignored.
    _fields = [('product_id', 'H'),           # product ID
               ('software_version', 'h'),     # software version number multiplied by 100
               ('product_description', 'n'),  # product description
               ]


class ExtProductData(DataType):
    """The ExtProductData contains zero or more null-terminated strings. The host
    should ignore all these strings; they are used during manufacturing to
    identify other properties of the device and are not formatted for display to
    the end user.

    """
    _fields = [('properties', '{n}'),  # zero or more additional null-terminated strings
               ]


class ProtocolData(DataType):
    """The ProtocolData is comprised of a one-byte tag field and a two-byte data
    field. The tag identifies which kind of ID is contained in the data field,
    and the data field contains the actual ID.

    The combination of tag value and data value must correspond to one of the
    protocols or data types specified.

    """
    _fields = [('tag', 'B'),
               ('data', 'H'),
               ]
    _tag = {'P': 'tag_phys_prot_id',  # Physical protocol ID
            'T': 'tag_tx_prot_id',    # Transmission protocol ID
            'L': 'tag_link_prot_id',  # Link protocol ID
            'A': 'tag_appl_prot_id',  # Application protocol ID
            'D': 'tag_data_type_id',  # Data Type ID
            }

    def __init__(self, tag, data):
        self.tag = tag
        self.data = data

    def __str__(self):
        """Format the record to a string consisting of the tag and 3-digit number.

        """
        return f'{chr(self.tag)}{self.data:03}'

    def get_tag(self):
        """Return the tag value.

        The characters shown are translated to numeric values using the ASCII
        character set.

        """
        return self._tag.get(chr(self.tag))


class ProtocolArray(DataType):
    """The ProtocolArray is a list of ProtocolData structures.

    """
    _protocol_data_fmt = ProtocolData.get_format()
    _fields = [('protocol_array', f'{{{_protocol_data_fmt}}}'),
               ]

    def get_protocol_data(self):
        return [ ProtocolData(*protocol_data) for protocol_data in self.protocol_array ]


class Position(DataType):
    """The Position type is used to indicate latitude and longitude in semicircles,
    where 2^31 semicircles equal 180 degrees. North latitudes and East
    longitudes are indicated with positive numbers; South latitudes and West
    longitudes are indicated with negative numbers.

    The following formulas show how to convert between degrees and semicircles:
    degrees = semicircles * ( 180 / 2^31 )
    semicircles = degrees * ( 2^31 / 180 )

    """
    _fields = [('lat', 'i'),  # latitude in semicircles
               ('lon', 'i'),  # longitude in semicircles
               ]

    def __init__(self, lat=0, lon=0):
        self.lat = lat
        self.lon = lon

    def __str__(self):
        return f'{self.lat}, {self.lon}'

    @staticmethod
    def to_degrees(semi):
        return semi * (180 / 2 ** 31)

    @staticmethod
    def to_radians(semi):
        return semi * (math.pi / 2 ** 31)

    def as_degrees(self):
        return DegreePosition(lat=self.to_degrees(self.lat),
                              lon=self.to_degrees(self.lon))

    def as_radians(self):
        return RadianPosition(lat=self.to_radians(self.lat),
                              lon=self.to_radians(self.lon))

    def is_valid(self):
        """Return whether the position is valid.

        A waypoint is invalid if both the “lat” and “lon” members are equal to
        0x7FFFFFFF (-129).

        """
        return not ( self.lat == -129 and self.lon == -129 )


class RadianPosition(DataType):
    """The Radian Position type is used to indicate latitude and longitude in
    radians, where π radians equal 180 degrees. North latitudes and East
    longitudes are indicated with positive numbers; South latitudes and West
    longitudes are indicated with negative numbers.

    The following formulas show how to convert between degrees and radians:
    degrees = radians * ( 180 / π )
    radians = degrees * ( π / 180 )

    """
    _fields = [('lat', 'd'),  # latitude in radians
               ('lon', 'd'),  # longitude in radians
               ]

    def __init__(self, lat=0, lon=0):
        self.lat = lat
        self.lon = lon

    def __str__(self):
        return f'{self.lat:.5f}, {self.lon:.5f}'

    @staticmethod
    def to_degrees(radians):
        return radians * (180 / math.pi)

    @staticmethod
    def to_semicircles(radians):
        return round(radians * (2 ** 31 / math.pi))

    def as_degrees(self):
        return DegreePosition(lat=self.to_degrees(self.lat),
                                  lon=self.to_degrees(self.lon))

    def as_semicircles(self):
        return Position(lat=self.to_semicircles(self.lat),
                            lon=self.to_semicircles(self.lon))


class DegreePosition(DataType):
    """The Degree Position type is used to indicate latitude and longitude in
    degrees. North latitudes and East longitudes are indicated with positive
    numbers; South latitudes and West longitudes are indicated with negative
    numbers.

    """
    _fields = [('lat', 'f'),  # latitude in radians
               ('lon', 'f'),  # longitude in radians
               ]

    def __init__(self, lat=0, lon=0):
        self.lat = lat
        self.lon = lon

    def __str__(self):
        return f'{self.lat:.5f}, {self.lon:.5f}'

    @staticmethod
    def to_semicircles(degrees):
        return round(degrees * (2 ** 31 / 180))

    @staticmethod
    def to_radians(degrees):
        return degrees * (math.pi / 180)

    def as_semicircles(self):
        return Position(lat=self.to_semicircles(self.lat),
                            lon=self.to_semicircles(self.lon))

    def as_radians(self):
        return RadianPosition(lat=self.to_radians(self.lat),
                                  lon=self.to_radians(self.lon))


class Time(DataType):
    _epoch = datetime(1989, 12, 31, 12, 0)  # 12:00 am December 31, 1989 UTC
    _fields = [('time', 'I'),  # timestamp, invalid if 0xFFFFFFFF
               ]

    def __init__(self, time=4294967295):
        self.time = time

    def __str__(self):
        datetime = self.get_datetime()
        return str(datetime)

    def get_datetime(self):
        """Return a datetime object of the time.

        The “time” member indicates the number of seconds since 12:00 am
        December 31, 1989 UTC.

        A value of 0xFFFFFFFF (4294967295) indicates that the “time” member is
        unsupported or unknown.

        """
        if self.is_valid():
            delta = timedelta(seconds=self.time)
            return self._epoch + delta

    def is_valid(self):
        """Return whether the time is valid.

        A “time” value of 0xFFFFFFFF that this parameter is not supported or unknown.

        """
        return not self.time == 4294967295


class Symbol(DataType):
    _fields = [('smbl', 'H'),    # symbol id
               ]
    _smbl = {
        # Marine symbols
        0: 'sym_anchor',                          # white anchor symbol
        1: 'sym_bell',                            # white bell symbol
        2: 'sym_diamond_grn',                     # green diamond symbol
        3: 'sym_diamond_red',                     # red diamond symbol
        4: 'sym_dive1',                           # diver down flag 1
        5: 'sym_dive2',                           # diver down flag 2
        6: 'sym_dollar',                          # white dollar symbol
        7: 'sym_fish',                            # white fish symbol
        8: 'sym_fuel',                            # white fuel symbol
        9: 'sym_horn',                            # white horn symbol
        10: 'sym_house',                          # white house symbol
        11: 'sym_knife',                          # white knife & fork symbol
        12: 'sym_light',                          # white light symbol
        13: 'sym_mug',                            # white mug symbol
        14: 'sym_skull',                          # white skull and crossbones symbol
        15: 'sym_square_grn',                     # green square symbol
        16: 'sym_square_red',                     # red square symbol
        17: 'sym_wbuoy',                          # white buoy waypoint symbol
        18: 'sym_wpt_dot',                        # waypoint dot
        19: 'sym_wreck',                          # white wreck symbol
        20: 'sym_null',                           # null symbol (transparent)
        21: 'sym_mob',                            # man overboard symbol
        22: 'sym_buoy_ambr',                      # amber map buoy symbol
        23: 'sym_buoy_blck',                      # black map buoy symbol
        24: 'sym_buoy_blue',                      # blue map buoy symbol
        25: 'sym_buoy_grn',                       # green map buoy symbol
        26: 'sym_buoy_grn_red',                   # green/red map buoy symbol
        27: 'sym_buoy_grn_wht',                   # green/white map buoy symbol
        28: 'sym_buoy_orng',                      # orange map buoy symbol
        29: 'sym_buoy_red',                       # red map buoy symbol
        30: 'sym_buoy_red_grn',                   # red/green map buoy symbol
        31: 'sym_buoy_red_wht',                   # red/white map buoy symbol
        32: 'sym_buoy_violet',                    # violet map buoy symbol
        33: 'sym_buoy_wht',                       # white map buoy symbol
        34: 'sym_buoy_wht_grn',                   # white/green map buoy symbol
        35: 'sym_buoy_wht_red',                   # white/red map buoy symbol
        36: 'sym_dot',                            # white dot symbol
        37: 'sym_rbcn',                           # radio beacon symbol
        150: 'sym_boat_ramp',                     # boat ramp symbol
        151: 'sym_camp',                          # campground symbol
        152: 'sym_restrooms',                     # restrooms symbol
        153: 'sym_showers',                       # shower symbol
        154: 'sym_drinking_wtr',                  # drinking water symbol
        155: 'sym_phone',                         # telephone symbol
        156: 'sym_1st_aid',                       # first aid symbol
        157: 'sym_info',                          # information symbol
        158: 'sym_parking',                       # parking symbol
        159: 'sym_park',                          # park symbol
        160: 'sym_picnic',                        # picnic symbol
        161: 'sym_scenic',                        # scenic area symbol
        162: 'sym_skiing',                        # skiing symbol
        163: 'sym_swimming',                      # swimming symbol
        164: 'sym_dam',                           # dam symbol
        165: 'sym_controlled',                    # controlled area symbol
        166: 'sym_danger',                        # danger symbol
        167: 'sym_restricted',                    # restricted area symbol
        168: 'sym_null_2',                        # null symbol
        169: 'sym_ball',                          # ball symbol
        170: 'sym_car',                           # car symbol
        171: 'sym_deer',                          # deer symbol
        172: 'sym_shpng_cart',                    # shopping cart symbol
        173: 'sym_lodging',                       # lodging symbol
        174: 'sym_mine',                          # mine symbol
        175: 'sym_trail_head',                    # trail head symbol
        176: 'sym_truck_stop',                    # truck stop symbol
        177: 'sym_user_exit',                     # user exit symbol
        178: 'sym_flag',                          # flag symbol
        179: 'sym_circle_x',                      # circle with x in the center
        180: 'sym_open_24hr',                     # open 24 hours symbol
        181: 'sym_fhs_facility',                  # U Fishing Hot Spots™ Facility
        182: 'sym_bot_cond',                      # bottom conditions
        183: 'sym_tide_pred_stn',                 # tide/current prediction station
        184: 'sym_anchor_prohib',                 # U anchor prohibited symbol
        185: 'sym_beacon',                        # U beacon symbol
        186: 'sym_coast_guard',                   # U coast guard symbol
        187: 'sym_reef',                          # U reef symbol
        188: 'sym_weedbed',                       # U weedbed symbol
        189: 'sym_dropoff',                       # U dropoff symbol
        190: 'sym_dock',                          # U dock symbol
        191: 'sym_marina',                        # U marina symbol
        192: 'sym_bait_tackle',                   # U bait and tackle symbol
        193: 'sym_stump',                         # U stump symbol
        194: 'sym_dsc_posn',                      # DSC position report symbol
        195: 'sym_dsc_distress',                  # DSC distress call symbol
        196: 'sym_wbuoy_dark',                    # dark buoy waypoint symbol
        197: 'sym_exp_wreck',                     # exposed wreck symbol
        198: 'sym_rcmmd_anchor',                  # recommended anchor symbol
        199: 'sym_brush_pile',                    # brush pile symbol
        200: 'sym_caution',                       # caution symbol
        201: 'sym_fish_1',                        # fish symbol 1
        202: 'sym_fish_2',                        # fish symbol 2
        203: 'sym_fish_3',                        # fish symbol 3
        204: 'sym_fish_4',                        # fish symbol 4
        205: 'sym_fish_5',                        # fish symbol 5
        206: 'sym_fish_6',                        # fish symbol 6
        207: 'sym_fish_7',                        # fish symbol 7
        208: 'sym_fish_8',                        # fish symbol 8
        209: 'sym_fish_9',                        # fish symbol 9
        210: 'sym_fish_attract',                  # fish attractor
        211: 'sym_hump',                          # hump symbol
        212: 'sym_laydown',                       # laydown symbol
        213: 'sym_ledge',                         # ledge symbol
        214: 'sym_lilly_pads',                    # lilly pads symbol
        215: 'sym_no_wake_zone',                  # no wake zone symbol
        216: 'sym_rocks',                         # rocks symbol
        217: 'sym_stop',                          # stop symbol
        218: 'sym_undrwtr_grss',                  # underwater grass symbol
        219: 'sym_undrwtr_tree',                  # underwater tree symbol
        220: 'sym_pin_yllw',                      # yellow pin symbol
        221: 'sym_flag_yllw',                     # yellow flag symbol
        222: 'sym_diamond_yllw',                  # yellow diamond symbol
        223: 'sym_cricle_yllw',                   # yellow circle symbol
        224: 'sym_square_yllw',                   # yellow square symbol
        225: 'sym_triangle_yllw',                 # yellow triangle symbol
        # User customizable symbols
        # The values from sym_begin_custom to sym_end_custom inclusive are
        # reserved for the identification of user customizable symbols.
        7680: 'sym_begin_custom',                 # first user customizable symbol
        8191: 'sym_end_custom',                   # last user customizable symbol
        # Land symbols
        8192: 'sym_is_hwy',                       # interstate hwy symbol
        8193: 'sym_us_hwy',                       # us hwy symbol
        8194: 'sym_st_hwy',                       # state hwy symbol
        8195: 'sym_mi_mrkr',                      # mile marker symbol
        8196: 'sym_trcbck',                       # TracBack (feet) symbol
        8197: 'sym_golf',                         # golf symbol
        8198: 'sym_sml_cty',                      # small city symbol
        8199: 'sym_med_cty',                      # medium city symbol
        8200: 'sym_lrg_cty',                      # large city symbol
        8201: 'sym_freeway',                      # intl freeway hwy symbol
        8202: 'sym_ntl_hwy',                      # intl national hwy symbol
        8203: 'sym_cap_cty',                      # capitol city symbol (star)
        8204: 'sym_amuse_pk',                     # amusement park symbol
        8205: 'sym_bowling',                      # bowling symbol
        8206: 'sym_car_rental',                   # car rental symbol
        8207: 'sym_car_repair',                   # car repair symbol
        8208: 'sym_fastfood',                     # fast food symbol
        8209: 'sym_fitness',                      # fitness symbol
        8210: 'sym_movie',                        # movie symbol
        8211: 'sym_museum',                       # museum symbol
        8212: 'sym_pharmacy',                     # pharmacy symbol
        8213: 'sym_pizza',                        # pizza symbol
        8214: 'sym_post_ofc',                     # post office symbol
        8215: 'sym_rv_park',                      # RV park symbol
        8216: 'sym_school',                       # school symbol
        8217: 'sym_stadium',                      # stadium symbol
        8218: 'sym_store',                        # dept. store symbol
        8219: 'sym_zoo',                          # zoo symbol
        8220: 'sym_gas_plus',                     # convenience store symbol
        8221: 'sym_faces',                        # live theater symbol
        8222: 'sym_ramp_int',                     # ramp intersection symbol
        8223: 'sym_st_int',                       # street intersection symbol
        8226: 'sym_weigh_sttn',                   # inspection/weigh station symbol
        8227: 'sym_toll_booth',                   # toll booth symbol
        8228: 'sym_elev_pt',                      # elevation point symbol
        8229: 'sym_ex_no_srvc',                   # exit without services symbol
        8230: 'sym_geo_place_mm',                 # geographic place name, man-made
        8231: 'sym_geo_place_wtr',                # geographic place name, water
        8232: 'sym_geo_place_lnd',                # geographic place name, land
        8233: 'sym_bridge',                       # bridge symbol
        8234: 'sym_building',                     # building symbol
        8235: 'sym_cemetery',                     # cemetery symbol
        8236: 'sym_church',                       # church symbol
        8237: 'sym_civil',                        # civil location symbol
        8238: 'sym_crossing',                     # crossing symbol
        8239: 'sym_hist_town',                    # historical town symbol
        8240: 'sym_levee',                        # levee symbol
        8241: 'sym_military',                     # military location symbol
        8242: 'sym_oil_field',                    # oil field symbol
        8243: 'sym_tunnel',                       # tunnel symbol
        8244: 'sym_beach',                        # beach symbol
        8245: 'sym_forest',                       # forest symbol
        8246: 'sym_summit',                       # summit symbol
        8247: 'sym_lrg_ramp_int',                 # large ramp intersection symbol
        8249: 'sym_badge',                        # police/official badge symbol
        8250: 'sym_cards',                        # gambling/casino symbol
        8251: 'sym_snowski',                      # snow skiing symbol
        8252: 'sym_iceskate',                     # ice skating symbol
        8253: 'sym_wrecker',                      # tow truck (wrecker) symbol
        8254: 'sym_border',                       # border crossing (port of entry)
        8255: 'sym_geocache',                     # geocache location
        8256: 'sym_geocache_fnd',                 # found geocache
        8257: 'sym_cntct_smiley',                 # Rino contact symbol, "smiley"
        8258: 'sym_cntct_ball_cap',               # Rino contact symbol, "ball cap"
        8259: 'sym_cntct_big_ears',               # Rino contact symbol, "big ear"
        8260: 'sym_cntct_spike',                  # Rino contact symbol, "spike"
        8261: 'sym_cntct_goatee',                 # Rino contact symbol, "goatee"
        8262: 'sym_cntct_afro',                   # Rino contact symbol, "afro"
        8263: 'sym_cntct_dreads',                 # Rino contact symbol, "dreads"
        8264: 'sym_cntct_female1',                # Rino contact symbol, "female 1"
        8265: 'sym_cntct_female2',                # Rino contact symbol, "female 2"
        8266: 'sym_cntct_female3',                # Rino contact symbol, "female 3"
        8267: 'sym_cntct_ranger',                 # Rino contact symbol, "ranger"
        8268: 'sym_cntct_kung_fu',                # Rino contact symbol, "kung fu"
        8269: 'sym_cntct_sumo',                   # Rino contact symbol, "sumo"
        8270: 'sym_cntct_pirate',                 # Rino contact symbol, "pirate"
        8271: 'sym_cntct_biker',                  # Rino contact symbol, "biker"
        8272: 'sym_cntct_alien',                  # Rino contact symbol, "alien"
        8273: 'sym_cntct_bug',                    # Rino contact symbol, "bug"
        8274: 'sym_cntct_cat',                    # Rino contact symbol, "cat"
        8275: 'sym_cntct_dog',                    # Rino contact symbol, "dog"
        8276: 'sym_cntct_pig',                    # Rino contact symbol, "pig"
        8277: 'sym_cntct_blond_woman',            # contact symbol - blond woman
        8278: 'sym_cntct_clown',                  # contact symbol - clown
        8279: 'sym_cntct_glasses_boy',            # contact symbol - glasses boy
        8280: 'sym_cntct_panda',                  # contact symbol - panda
        8281: 'sym_cntct_reserved5',              # contact symbol -
        8282: 'sym_hydrant',                      # water hydrant symbol
        8283: 'sym_voice_rec',                    # icon for a voice recording
        8284: 'sym_flag_blue',                    # blue flag symbol
        8285: 'sym_flag_green',                   # green flag symbol
        8286: 'sym_flag_red',                     # red flag symbol
        8287: 'sym_pin_blue',                     # blue pin symbol
        8288: 'sym_pin_green',                    # green pin symbol
        8289: 'sym_pin_red',                      # red pin symbol
        8290: 'sym_block_blue',                   # blue block symbol
        8291: 'sym_block_green',                  # green block symbol
        8292: 'sym_block_red',                    # red block symbol
        8293: 'sym_bike_trail',                   # bike trail symbol
        8294: 'sym_circle_red',                   # red circle symbol
        8295: 'sym_circle_green',                 # green circle symbol
        8296: 'sym_circle_blue',                  # blue circle symbol
        8299: 'sym_diamond_blue',                 # blue diamond symbol
        8300: 'sym_oval_red',                     # red oval symbol
        8301: 'sym_oval_green',                   # green oval symbol
        8302: 'sym_oval_blue',                    # blue oval symbol
        8303: 'sym_rect_red',                     # red rectangle symbol
        8304: 'sym_rect_green',                   # green rectangle symbol
        8305: 'sym_rect_blue',                    # blue rectangle symbol
        8308: 'sym_square_blue',                  # blue square symbol
        8309: 'sym_letter_a_red',                 # red letter 'A' symbol
        8310: 'sym_letter_b_red',                 # red letter 'B' symbol
        8311: 'sym_letter_c_red',                 # red letter 'C' symbol
        8312: 'sym_letter_d_red',                 # red letter 'D' symbol
        8313: 'sym_letter_a_green',               # green letter 'A' symbol
        8314: 'sym_letter_b_green',               # green letter 'B' symbol
        8315: 'sym_letter_c_green',               # green letter 'C' symbol
        8316: 'sym_letter_d_green',               # green letter 'D' symbol
        8317: 'sym_letter_a_blue',                # blue letter 'A' symbol
        8318: 'sym_letter_b_blue',                # blue letter 'B' symbol
        8319: 'sym_letter_c_blue',                # blue letter 'C' symbol
        8320: 'sym_letter_d_blue',                # blue letter 'D' symbol
        8321: 'sym_number_0_red',                 # red number '0' symbol
        8322: 'sym_number_1_red',                 # red number '1' symbol
        8323: 'sym_number_2_red',                 # red number '2' symbol
        8324: 'sym_number_3_red',                 # red number '3' symbol
        8325: 'sym_number_4_red',                 # red number '4' symbol
        8326: 'sym_number_5_red',                 # red number '5' symbol
        8327: 'sym_number_6_red',                 # red number '6' symbol
        8328: 'sym_number_7_red',                 # red number '7' symbol
        8329: 'sym_number_8_red',                 # red number '8' symbol
        8330: 'sym_number_9_red',                 # red number '9' symbol
        8331: 'sym_number_0_green',               # green number '0' symbol
        8332: 'sym_number_1_green',               # green number '1' symbol
        8333: 'sym_number_2_green',               # green number '2' symbol
        8334: 'sym_number_3_green',               # green number '3' symbol
        8335: 'sym_number_4_green',               # green number '4' symbol
        8336: 'sym_number_5_green',               # green number '5' symbol
        8337: 'sym_number_6_green',               # green number '6' symbol
        8338: 'sym_number_7_green',               # green number '7' symbol
        8339: 'sym_number_8_green',               # green number '8' symbol
        8340: 'sym_number_9_green',               # green number '9' symbol
        8341: 'sym_number_0_blue',                # blue number '0' symbol
        8342: 'sym_number_1_blue',                # blue number '1' symbol
        8343: 'sym_number_2_blue',                # blue number '2' symbol
        8344: 'sym_number_3_blue',                # blue number '3' symbol
        8345: 'sym_number_4_blue',                # blue number '4' symbol
        8346: 'sym_number_5_blue',                # blue number '5' symbol
        8347: 'sym_number_6_blue',                # blue number '6' symbol
        8348: 'sym_number_7_blue',                # blue number '7' symbol
        8349: 'sym_number_8_blue',                # blue number '8' symbol
        8350: 'sym_number_9_blue',                # blue number '9' symbol
        8351: 'sym_triangle_blue',                # blue triangle symbol
        8352: 'sym_triangle_green',               # green triangle symbol
        8353: 'sym_triangle_red',                 # red triangle symbol
        8354: 'sym_library',                      # library (book)
        8355: 'sym_bus',                          # ground transportation
        8356: 'sym_city_hall',                    # city hall
        8357: 'sym_wine',                         # winery
        8358: 'sym_oem_dealer',                   # OEM dealer
        8359: 'sym_food_asian',                   # asian food symbol
        8360: 'sym_food_deli',                    # deli symbol
        8361: 'sym_food_italian',                 # italian food symbol
        8362: 'sym_food_seafood',                 # seafood symbol
        8363: 'sym_food_steak',                   # steak symbol
        8364: 'sym_atv',                          # ATV
        8365: 'sym_big_game',                     # big game
        8366: 'sym_blind',                        # blind
        8367: 'sym_blood_trail',                  # blood trail
        8368: 'sym_cover',                        # cover
        8369: 'sym_covey',                        # covey
        8370: 'sym_food_source',                  # food source
        8371: 'sym_furbearer',                    # furbearer
        8372: 'sym_lodge',                        # lodge
        8373: 'sym_small_game',                   # small game
        8374: 'sym_tracks',                       # tracks
        8375: 'sym_treed_quarry',                 # treed quarry
        8376: 'sym_tree_stand',                   # tree stand
        8377: 'sym_truck',                        # truck
        8378: 'sym_upland_game',                  # upland game
        8379: 'sym_waterfowl',                    # waterfowl
        8380: 'sym_water_source',                 # water source
        8381: 'sym_tracker_auto_dark_blue',       # tracker - vehicles
        8382: 'sym_tracker_auto_green',
        8383: 'sym_tracker_auto_light_blue',
        8384: 'sym_tracker_auto_light_purple',
        8385: 'sym_tracker_auto_lime',
        8386: 'sym_tracker_auto_normal',
        8387: 'sym_tracker_auto_orange',
        8388: 'sym_tracker_auto_purple',
        8389: 'sym_tracker_auto_red',
        8390: 'sym_tracker_auto_sky_blue',
        8391: 'sym_tracker_auto_yellow',
        8392: 'sym_tracker_gnrc_dark_blue',       # tracker - generic
        8393: 'sym_tracker_gnrc_green',
        8394: 'sym_tracker_gnrc_light_blue',
        8395: 'sym_tracker_gnrc_light_purple',
        8396: 'sym_tracker_gnrc_lime',
        8397: 'sym_tracker_gnrc_normal',
        8398: 'sym_tracker_gnrc_orange',
        8399: 'sym_tracker_gnrc_purple',
        8400: 'sym_tracker_gnrc_red',
        8401: 'sym_tracker_gnrc_sky_blue',
        8402: 'sym_tracker_gnrc_yellow',
        8403: 'sym_tracker_pdstrn_dark_blue',     # tracker - pedestrians
        8404: 'sym_tracker_pdstrn_green',
        8405: 'sym_tracker_pdstrn_light_blue',
        8406: 'sym_tracker_pdstrn_light_purple',
        8407: 'sym_tracker_pdstrn_lime',
        8408: 'sym_tracker_pdstrn_normal',
        8409: 'sym_tracker_pdstrn_orange',
        8410: 'sym_tracker_pdstrn_purple',
        8411: 'sym_tracker_pdstrn_red',
        8412: 'sym_tracker_pdstrn_sky_blue',
        8413: 'sym_tracker_pdstrn_yellow',
        8414: 'sym_tracker_auto_dsbl_dark_blue',  # tracker - vehicles
        8415: 'sym_tracker_auto_dsbl_green',
        8416: 'sym_tracker_auto_dsbl_light_blue',
        8417: 'sym_tracker_auto_dsbl_light_purple',
        8418: 'sym_tracker_auto_dsbl_lime',
        8419: 'sym_tracker_auto_dsbl_normal',
        8420: 'sym_tracker_auto_dsbl_orange',
        8421: 'sym_tracker_auto_dsbl_purple',
        8422: 'sym_tracker_auto_dsbl_red',
        8423: 'sym_tracker_auto_dsbl_sky_blue',
        8424: 'sym_tracker_auto_dsbl_yellow',
        8425: 'sym_tracker_gnrc_dsbl_dark_blue',  # tracker - generic
        8426: 'sym_tracker_gnrc_dsbl_green',
        8427: 'sym_tracker_gnrc_dsbl_light_blue',
        8428: 'sym_tracker_gnrc_dsbl_light_purple',
        8429: 'sym_tracker_gnrc_dsbl_lime',
        8430: 'sym_tracker_gnrc_dsbl_normal',
        8431: 'sym_tracker_gnrc_dsbl_orange',
        8432: 'sym_tracker_gnrc_dsbl_purple',
        8433: 'sym_tracker_gnrc_dsbl_red',
        8434: 'sym_tracker_gnrc_dsbl_sky_blue',
        8435: 'sym_tracker_gnrc_dsbl_yellow',
        8436: 'sym_tracker_pdstrn_dsbl_dark_blue',  # tracker – pedestrians
        8437: 'sym_tracker_pdstrn_dsbl_green',
        8438: 'sym_tracker_pdstrn_dsbl_light_blue',
        8439: 'sym_tracker_pdstrn_dsbl_light_purple',
        8440: 'sym_tracker_pdstrn_dsbl_lime',
        8441: 'sym_tracker_pdstrn_dsbl_normal',
        8442: 'sym_tracker_pdstrn_dsbl_orange',
        8443: 'sym_tracker_pdstrn_dsbl_purple',
        8444: 'sym_tracker_pdstrn_dsbl_red',
        8445: 'sym_tracker_pdstrn_dsbl_sky_blue',
        8446: 'sym_tracker_pdstrn_dsbl_yellow',
        8447: 'sym_sm_red_circle',                # small red circle
        8448: 'sym_sm_yllw_circle',               # small yellow circle
        8449: 'sym_sm_green_circle',              # small green circle
        8450: 'sym_sm_blue_circle',               # small blue circle
        8451: 'sym_alert',                        # red alert (! point)
        8452: 'sym_snow_mobile',                  # snow mobile
        8453: 'sym_wind_turbine',                 # wind turbine
        8454: 'sym_camp_fire',                    # camp fire
        8455: 'sym_binoculars',                   # binoculars
        8456: 'sym_kayak',                        # kayak
        8457: 'sym_canoe',                        # canoe
        8458: 'sym_shelter',                      # lean to
        8459: 'sym_xski',                         # cross country skiing
        8460: 'sym_hunting',                      # hunting
        8461: 'sym_horse_tracks',                 # horse trail
        8462: 'sym_tree',                         # deciduous tree
        8463: 'sym_lighthouse',                   # lighthouse
        8464: 'sym_creek_crossing',               # creek crossing
        8465: 'sym_deer_sign_scrape',             # deer sign (scrape)
        8466: 'sym_deer_sign_rub',                # deer sign (rub)
        8467: 'sym_elk',                          # elk
        8468: 'sym_elk_wallow',                   # elk wallow
        8469: 'sym_shed_antlers',                 # shed (antlers)
        8470: 'sym_turkey',                       # turkey
        # Aviation symbols
        16384: 'sym_airport',                     # airport symbol
        16385: 'sym_int',                         # intersection symbol
        16386: 'sym_ndb',                         # non-directional beacon symbol
        16387: 'sym_vor',                         # VHF omni-range symbol
        16388: 'sym_heliport',                    # heliport symbol
        16389: 'sym_private',                     # private field symbol
        16390: 'sym_soft_fld',                    # soft field symbol
        16391: 'sym_tall_tower',                  # tall tower symbol
        16392: 'sym_short_tower',                 # short tower symbol
        16393: 'sym_glider',                      # glider symbol
        16394: 'sym_ultralight',                  # ultralight symbol
        16395: 'sym_parachute',                   # parachute symbol
        16396: 'sym_vortac',                      # VOR/TACAN symbol
        16397: 'sym_vordme',                      # VOR-DME symbol
        16398: 'sym_faf',                         # first approach fix
        16399: 'sym_lom',                         # localizer outer marker
        16400: 'sym_map',                         # missed approach point
        16401: 'sym_tacan',                       # TACAN symbol
        16402: 'sym_seaplane',                    # seaplane base
    }

    def __init__(self, smbl=0):
        self.smbl = smbl

    def __str__(self):
        return f'{self.get_smbl()}'

    def get_smbl(self):
        """Return the symbol value.

        """
        return self._smbl.get(self.smbl)


class Wpt(DataType):

    def is_valid_ident(self):
        return self.is_valid_charset(self.re_upcase_digit, self.ident)

    def is_valid_wpt_ident(self):
        wpt_class = self.get_wpt_class
        if wpt_class == 'user_wpt' or wpt_class == 'usr_wpt_class':
            pattern = self.re_upcase_digit
        else:
            pattern = self.re_ascii
        return self.is_valid_charset(pattern, self.wpt_ident)

    def is_valid_lnk_ident(self):
        pattern = self.re_ascii
        return self.is_valid_charset(pattern, self.lnk_ident)

    def is_valid_cmnt(self):
        pattern = self.re_upcase_digit_space_hyphen
        return self.is_valid_charset(pattern, self.cmnt)

    def is_valid_cc(self):
        pattern = self.re_upcase_digit_space
        return self.is_valid_charset(pattern, self.cc)


class D100(Wpt):
    _posn_fmt = Position.get_format()
    _fields = [('ident', '6s'),             # identifier
               ('posn', f'({_posn_fmt})'),  # position
               ('unused', 'I'),             # should be set to zero
               ('cmnt', '40s'),             # comment
               ]

    def __init__(self, ident=b'', posn=[0, 0], cmnt=b''):
        self.ident = ident
        self.posn = posn
        self.unused = 0
        self.cmnt = cmnt

    def get_posn(self):
        return Position(*self.posn)


class D101(D100):
    _posn_fmt = Position.get_format()
    _fields = [('ident', '6s'),             # identifier
               ('posn', f'({_posn_fmt})'),  # position
               ('unused', 'I'),             # should be set to zero
               ('cmnt', '40s'),             # comment
               ('dst', 'f'),                # proximity distance (meters)
               ('smbl', 'B'),               # symbol id
               ]

    def __init__(self, dst=0, smbl=0, **kwargs):
        super().__init__(**kwargs)
        self.dst = dst
        self.smbl = smbl

    def get_symbol(self):
        return Symbol(self.smbl)

    def get_smbl(self):
        symbol = self.get_symbol()
        return symbol.get_smbl()

    def is_valid_dst(self):
        """Return whether the proximity distance is valid.

        A “dst” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.dst:.1e}" == "1.0e+25"


class D102(D101):
    _posn_fmt = Position.get_format()
    _smbl_fmt = Symbol.get_format()
    _fields = [('ident', '6s'),             # identifier
               ('posn', f'({_posn_fmt})'),  # position
               ('unused', 'I'),             # should be set to zero
               ('cmnt', '40s'),             # comment
               ('dst', 'f'),                # proximity distance (meters)
               ('smbl', f'{_smbl_fmt}'),    # symbol id
               ]


class D103(D100):
    _posn_fmt = Position.get_format()
    _fields = [('ident', '6s'),             # identifier
               ('posn', f'({_posn_fmt})'),  # position
               ('unused', 'I'),             # should be set to zero
               ('cmnt', '40s'),             # comment
               ('smbl', 'B'),               # symbol id
               ('dspl', 'B'),               # display option
               ]
    _smbl = {0:  'smbl_dot',         # dot symbol
             1:  'smbl_house',       # house symbol
             2:  'smbl_gas',         # gas symbol
             3:  'smbl_car',         # car symbol
             4:  'smbl_fish',        # fish symbol
             5:  'smbl_boat',        # boat symbol
             6:  'smbl_anchor',      # anchor symbol
             7:  'smbl_wreck',       # wreck symbol
             8:  'smbl_exit',        # exit symbol
             9:  'smbl_skull',       # skull symbol
             10: 'smbl_flag',        # flag symbol
             11: 'smbl_camp',        # camp symbol
             12: 'smbl_circle_x',    # circle with x symbol
             13: 'smbl_deer',        # deer symbol
             14: 'smbl_1st_aid',     # first aid symbol
             15: 'smbl_back_track',  # back track symbol
             }
    _dspl = {0: 'dspl_smbl_name',  # display symbol with waypoint name
             1: 'dspl_smbl_none',  # display symbol by itself
             2: 'dspl_smbl_cmnt',  # display symbol with comment
             }

    def __init__(self, smbl=0, dspl=0, **kwargs):
        super().__init__(**kwargs)
        self.smbl = smbl
        self.dspl = dspl

    def get_smbl(self):
        """Return the symbol value.

        """
        return _smbl.get(self.smbl)

    def get_dspl(self):
        """Return the display attribute value.

        """
        return self._dspl.get(self.dspl, 0)


class D104(D101):
    _posn_fmt = Position.get_format()
    _smbl_fmt = Symbol.get_format()
    _fields = [('ident', '6s'),             # identifier
               ('posn', f'({_posn_fmt})'),  # position
               ('unused', 'I'),             # should be set to zero
               ('cmnt', '40s'),             # comment
               ('dst', 'B'),                # proximity distance (meters)
               ('smbl', f'{_smbl_fmt}'),    # symbol id
               ('dspl', 'B'),               # display option
               ]
    _dspl = {0: 'dspl_smbl_none',  # display symbol by itself
             1: 'dspl_smbl_only',  # display symbol by itself
             3: 'dspl_smbl_name',  # display symbol with waypoint name
             5: 'dspl_smbl_cmnt',  # display symbol with comment
             }

    def __init__(self, dspl=0, **kwargs):
        super().__init__(**kwargs)
        self.dspl = dspl

    def get_dspl(self):
        """Return the display attribute value.

        """
        return self._dspl.get(self.dspl, 0)


class D105(D101):
    _posn_fmt = Position.get_format()
    _smbl_fmt = Symbol.get_format()
    _fields = [('posn', f'({_posn_fmt})'),  # position
               ('smbl', f'{_smbl_fmt}'),    # symbol id
               ('wpt_ident', 'n'),          # waypoint identifier
               ]

    def __init__(self, wpt_ident=b'', **kwargs):
        super().__init__(**kwargs)
        self.wpt_ident = wpt_ident


class D106(D101):
    _posn_fmt = Position.get_format()
    _smbl_fmt = Symbol.get_format()
    _fields = [('wpt_class', 'B'),          # class
               ('subclass', '(13B)'),       # subclass
               ('posn', f'({_posn_fmt})'),  # position
               ('smbl', f'{_smbl_fmt}'),    # symbol id
               ('wpt_ident', 'n'),          # waypoint identifier
               ('lnk_ident', 'n'),          # link identifier
               ]

    def __init__(self, wpt_class=0, subclass=(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0), wpt_ident=b'', lnk_ident=b'', **kwargs):
        super().__init__(**kwargs)
        self.wpt_class = wpt_class
        self.subclass = subclass
        self.wpt_ident = wpt_ident
        self.lnk_ident = lnk_ident


class D107(D103):
    _posn_fmt = Position.get_format()
    _fields = [('ident', '6s'),             # identifier
               ('posn', f'({_posn_fmt})'),  # position
               ('unused', 'I'),             # should be set to zero
               ('cmnt', '40s'),             # comment
               ('smbl', 'B'),               # symbol id
               ('dspl', 'B'),               # display option
               ('dst', 'f'),                # proximity distance (meters)
               ('color', 'B'),              # waypoint color
               ]
    _color = {0: 'clr_default',  # default waypoint color
              1: 'clr_red',      # red
              2: 'clr_green',    # green
              3: 'clr_blue',     # blue
              }

    def __init__(self, dst=0, color=0, **kwargs):
        super().__init__(**kwargs)
        self.dst = dst
        self.color = color

    def get_color(self):
        """Return the color value.

        """
        return self._color.get(self.color, 0)

    def is_valid_dst(self):
        """Return whether the proximity distance is valid.

        A “dst” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.dst:.1e}" == "1.0e+25"


class D108(D103):
    _posn_fmt = Position.get_format()
    _smbl_fmt = Symbol.get_format()
    _fields = [('wpt_class', 'B'),          # class
               ('color', 'B'),              # waypoint color
               ('dspl', 'B'),               # display option
               ('attr', 'B'),               # attributes (0x60 for D108)
               ('smbl', f'{_smbl_fmt}'),    # symbol id
               ('subclass', '(18B)'),       # subclass
               ('posn', f'({_posn_fmt})'),  # position
               ('alt', 'f'),                # altitude in meters
               ('dpth', 'f'),               # depth in meters
               ('dist', 'f'),               # proximity distance in meters
               ('state', '2s'),             # state
               ('cc', '2s'),                # country code
               ('ident', 'n'),              # identifier
               ('cmnt', 'n'),               # waypoint user comment
               ('facility', 'n'),           # facility name
               ('city', 'n'),               # city name
               ('addr', 'n'),               # address number
               ('cross_road', 'n'),         # intersecting road label
               ]
    _wpt_class = {0:   'user_wpt',       # user waypoint
                  64:  'avtn_apt_wpt',   # aviation airport waypoint
                  65:  'avtn_int_wpt',   # aviation intersection waypoint
                  66:  'avtn_ndb_wpt',   # aviation NDB waypoint
                  67:  'avtn_vor_wpt',   # aviation VOR waypoint
                  68:  'avtn_arwy_wpt',  # aviation airport runway waypoint
                  69:  'avtn_aint_wpt',  # aviation airport intersection
                  70:  'avtn_andb_wpt',  # aviation airport ndb waypoint
                  128: 'map_pnt_wpt',    # map point waypoint
                  129: 'map_area_wpt',   # map area waypoint
                  130: 'map_int_wpt',    # map intersection waypoint
                  131: 'map_adrs_wpt',   # map address waypoint
                  132: 'map_line_wpt',   # map line waypoint
                  }
    _color = {0:   'clr_black',
              1:   'clr_dark_red',
              2:   'clr_dark_green',
              3:   'clr_dark_yellow',
              4:   'clr_dark_blue',
              5:   'clr_dark_magenta',
              6:   'clr_dark_cyan',
              7:   'clr_light_gray',
              8:   'clr_dark_gray',
              9:   'clr_red',
              10:  'clr_green',
              11:  'clr_yellow',
              12:  'clr_blue',
              13:  'clr_magenta',
              14:  'clr_cyan',
              15:  'clr_white',
              255: 'clr_default_color'
              }

    def __init__(self, wpt_class=0, color=255, attr=96, smbl=0, subclass=(0, 0, 0, 0, 0, 0, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255), alt=1.0e25, dpth=1.0e25, dist=1.0e25, state=b'', cc=b'', cmnt=b'', facility=b'', city=b'', addr=b'', cross_road=b'', **kwargs):
        super().__init__(**kwargs)
        self.wpt_class = wpt_class
        self.color = color
        self.attr = attr
        self.smbl = smbl
        self.subclass = subclass
        self.alt = alt
        self.dpth = dpth
        self.dist = dist
        self.state = state
        self.cc = cc
        self.cmnt = cmnt
        self.facility = facility
        self.city = city
        self.addr = addr
        self.cross_road = cross_road

    def get_wpt_class(self):
        """return the waypoint class value.

        if an invalid value is received, the value will be user_wpt.

        """
        return self._wpt_class.get(self.wpt_class, 0)

    def get_color(self):
        """return the color value.

        """
        return self._color.get(self.color, 255)

    def get_symbol(self):
        return Symbol(self.smbl)

    def get_smbl(self):
        symbol = self.get_symbol()
        return symbol.get_smbl()

    def is_valid_alt(self):
        """Return whether the altitude is valid.

        A “alt” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.alt:.1e}" == "1.0e+25"

    def is_valid_dpth(self):
        """Return whether the depth is valid.

        A “dpth” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.dpth:.1e}" == "1.0e+25"

    def is_valid_dist(self):
        """Return whether the proximity distance is valid.

        A “dist” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.dist:.1e}" == "1.0e+25"


class D109(D108):
    _smbl_fmt = Symbol.get_format()
    _posn_fmt = Position.get_format()
    _fields = [('dtyp', 'B'),               # data packet type (0x01 for d109)
               ('wpt_class', 'B'),          # class
               ('dspl_color', 'B'),         # display & color
               ('attr', 'B'),               # attributes (0x70 for d109)
               ('smbl', f'{_smbl_fmt}'),    # symbol id
               ('subclass', '(18B)'),       # subclass
               ('posn', f'({_posn_fmt})'),  # position
               ('alt', 'f'),                # altitude in meters
               ('dpth', 'f'),               # depth in meters
               ('dist', 'f'),               # proximity distance in meters
               ('state', '2s'),             # state
               ('cc', '2s'),                # country code
               ('ete', 'I'),                # outbound link ete in seconds (default value is 0xffffffff)
               ('ident', 'n'),              # identifier
               ('cmnt', 'n'),               # waypoint user comment
               ('facility', 'n'),           # facility name
               ('city', 'n'),               # city name
               ('addr', 'n'),               # address number
               ('cross_road', 'n'),         # intersecting road label
               ]

    def __init__(self, dtyp=1, dspl_color=0, attr=112, ete=4294967295, **kwargs):
        super().__init__(**kwargs)
        self.dtyp = dtyp
        self.dspl_color = dspl_color
        self.attr = attr
        self.ete = ete

    def get_color(self):
        """Return the color value.

        The “dspl_color” member contains three fields; bits 0-4 specify the color,
        bits 5-6 specify the waypoint display attribute and bit 7 is unused and
        must be 0.

        """
        bits = f"{self.dspl_color:08b}"
        color = int(bits[0:5], 2)
        # According to the specification the default color value should be 0x1f,
        # but this is an invalid value. It probably should be 0xff.
        return self._color.get(color, 255)

    def get_dspl(self):
        """Return the display attribute value.

        The “dspl_color” member contains three fields; bits 0-4 specify the
        color, bits 5-6 specify the waypoint display attribute and bit 7 is
        unused and must be 0.

        If an invalid display attribute value is received, the value will be
        Name.

        """
        bits = f"{self.dspl_color:08b}"
        dspl = int(bits[5:7], 2)
        return self._dspl.get(dspl, 0)


class D110(D109):
    _smbl_fmt = Symbol.get_format()
    _posn_fmt = Position.get_format()
    _time_fmt = Time.get_format()
    _fields = [('dtyp', 'B'),               # data packet type (0x01 for D110)
               ('wpt_class', 'B'),          # class
               ('dspl_color', 'B'),         # display & color
               ('attr', 'B'),               # attributes (0x80 for D110)
               ('smbl', f'{_smbl_fmt}'),    # symbol id
               ('subclass', '(18B)'),       # subclass
               ('posn', f'({_posn_fmt})'),  # position
               ('alt', 'f'),                # altitude in meters
               ('dpth', 'f'),               # depth in meters
               ('dist', 'f'),               # proximity distance in meters
               ('state', '2s'),             # state
               ('cc', '2s'),                # country code
               ('ete', 'I'),                # outbound link ete in seconds
               ('temp', 'f'),               # temperature, invalid if 1.0e25
               ('time', f'{_time_fmt}'),    # timestamp, invalid if 0xFFFFFFFF
               ('wpt_cat', 'H'),            # category membership (default value is 0x0000)
               ('ident', 'n'),              # identifier
               ('cmnt', 'n'),               # waypoint user comment
               ('facility', 'n'),           # facility name
               ('city', 'n'),               # city name
               ('addr', 'n'),               # address number
               ('cross_road', 'n'),         # intersecting road label
               ]
    _wpt_class = {0:   'user_wpt',       # user waypoint
                  64:  'avtn_apt_wpt',   # aviation airport waypoint
                  65:  'avtn_int_wpt',   # aviation intersection waypoint
                  66:  'avtn_ndb_wpt',   # aviation NDB waypoint
                  67:  'avtn_vor_wpt',   # aviation VOR waypoint
                  68:  'avtn_arwy_wpt',  # aviation airport runway waypoint
                  69:  'avtn_aint_wpt',  # aviation airport intersection
                  70:  'avtn_andb_wpt',  # aviation airport ndb waypoint
                  128: 'map_pnt_wpt',    # map point waypoint
                  129: 'map_area_wpt',   # map area waypoint
                  130: 'map_int_wpt',    # map intersection waypoint
                  131: 'map_adrs_wpt',   # map address waypoint
                  132: 'map_line_wpt',   # map line waypoint
                  }
    _color = {0:  'clr_black',
              1:  'clr_dark_red',
              2:  'clr_dark_green',
              3:  'clr_dark_yellow',
              4:  'clr_dark_blue',
              5:  'clr_dark_magenta',
              6:  'clr_dark_cyan',
              7:  'clr_light_gray',
              8:  'clr_dark_gray',
              9:  'clr_red',
              10: 'clr_green',
              11: 'clr_yellow',
              12: 'clr_blue',
              13: 'clr_magenta',
              14: 'clr_cyan',
              15: 'clr_white',
              16: 'clr_transparent'
              }

    def __init__(self, attr=128, temp=1.0e25, time=4294967295,
                 wpt_cat=0, **kwargs):
        super().__init__(**kwargs)
        self.attr = attr
        self.temp = temp
        self.time = time
        self.wpt_cat = wpt_cat

    def get_wpt_class(self):
        """Return the waypoint class value.

        If an invalid value is received, the value will be user_wpt.

        """
        return self._wpt_class.get(self.wpt_class, 0)

    def get_color(self):
        """Return the color value.

        The “dspl_color” member contains three fields; bits 0-4 specify the color,
        bits 5-6 specify the waypoint display attribute and bit 7 is unused and
        must be 0.

        If an invalid color value is received, the value will be Black.

        """
        bits = f"{self.dspl_color:08b}"
        color = int(bits[0:5], 2)
        return self._color.get(color, 0)

    def get_dspl(self):
        """Return the display attribute value.

        The “dspl_color” member contains three fields; bits 0-4 specify the
        color, bits 5-6 specify the waypoint display attribute and bit 7 is
        unused and must be 0.

        If an invalid display attribute value is received, the value will be
        Name.

        """
        bits = f"{self.dspl_color:08b}"
        dspl = int(bits[5:7], 2)
        return self._dspl.get(dspl, 0)

    def get_datetime(self):
        return Time(self.time).get_datetime()

    def get_wpt_cat(self):
        """Return a list of waypoint categories.

        The “wpt_cat” member contains a 16 bits that provide category membership
        information for the waypoint. If a bit is set then the waypoint is a
        member of the corresponding category.

        """
        categories = []
        bits = f"{self.wpt_cat:016b}"
        for count, bit in enumerate(bits):
            if bit == '1':
                categories.append(count + 1)
        return categories

    def is_valid(self):
        """Return whether the waypoint is valid.

        A waypoint is invalid if the “lat” member of the “posn” member contains
        a value greater than 2^30 or less than -2^30

        """
        return not self.posn.lat > 2**30 or self.posn.lat < -2**30

    def is_valid_temp(self):
        """Return whether the temperature is valid.

        A “temp” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.temp:.1e}" == "1.0e+25"

    def is_valid_time(self):
        """Return whether the time is valid.

        A “time” value of 0xFFFFFFFF that this parameter is not supported or unknown.

        """
        return not self.time == 4294967295


class WptCat(DataType):

    def is_valid(self):
        """Return whether the waypoint category is valid.

        A waypoint category is invalid if the “name” member contains a value
        with a null byte in the first character.

        """
        self.name[0] != 0


class D120(WptCat):
    _fields = [('name', '17s'),  # category name
               ]

    def __init__(self, name=b''):
        self.name = name


class D150(Wpt):
    _posn_fmt = Position.get_format()
    _fields = [('ident', '6s'),             # identifier
               ('cc', '2s'),                # country code
               ('wpt_class', 'B'),          # class
               ('posn', f'({_posn_fmt})'),  # position
               ('alt', 'h'),                # altitude in meters
               ('city', '24s'),             # city
               ('state', '2s'),             # state
               ('facility', '30s'),         # facility name
               ('cmnt', '40s'),             # comment
               ]
    _wpt_class = {0: 'apt_wpt_class',     # airport waypoint class
                  1: 'int_wpt_class',     # intersection waypoint class
                  2: 'ndb_wpt_class',     # NDB waypoint class
                  3: 'vor_wpt_class',     # VOR waypoint class
                  4: 'usr_wpt_class',     # user defined waypoint class
                  5: 'rwy_wpt_class',     # airport runway threshold waypoint class
                  6: 'aint_wpt_class',    # airport intersection waypoint class
                  7: 'locked_wpt_class',  # locked waypoint class
                  }

    def __init__(self, ident=b'', cc=b'', wpt_class=0, posn=[0, 0], alt=1.0e25,
                 city=b'', state=b'', facility=b'', cmnt=b''):
        self.ident = ident
        self.cc = cc
        self.wpt_class = wpt_class
        self.posn = posn
        self.alt = alt
        self.city = city
        self.state = state
        self.facility = facility
        self.cmnt = cmnt

    def get_posn(self):
        return Position(*self.posn)

    def get_wpt_class(self):
        """Return the waypoint class value.

        If an invalid value is received, the value will be user_wpt.

        """
        return self._wpt_class.get(self.wpt_class, 0)


class D151(D150):
    _posn_fmt = Position.get_format()
    _fields = [('ident', '6s'),             # identifier
               ('posn', f'({_posn_fmt})'),  # position
               ('unused', 'I'),             # should be set to zero
               ('cmnt', '40s'),             # comment
               ('dst', 'f'),                # proximity distance (meters)
               ('name', '30s'),             # facility name
               ('city', '24s'),             # city
               ('state', '2s'),             # state
               ('alt', 'h'),                # altitude (meters)
               ('cc', '2s'),                # country code
               ('unused2', 'B'),            # should be set to zero
               ('wpt_class', 'B'),          # class
               ]
    _wpt_class = {0: 'apt_wpt_class',    # airport waypoint class
                  1: 'vor_wpt_class',    # VOR waypoint class
                  2: 'usr_wpt_class',    # user defined waypoint class
                  3: 'locked_wpt_class'  # locked waypoint class
                  }

    def __init__(self, dst=0, name=b'', **kwargs):
        super().__init__(**kwargs)
        self.unused = 0
        self.dst = dst
        self.name = name
        self.unused2 = 0


class D152(D150):
    _wpt_class = {0: 'apt_wpt_class',    # airport waypoint class
                  1: 'int_wpt_class',    # intersection waypoint class
                  2: 'ndb_wpt_class',    # NDB waypoint class
                  3: 'vor_wpt_class',    # VOR waypoint class
                  4: 'usr_wpt_class',    # user defined waypoint class
                  5: 'locked_wpt_class'  # locked waypoint class
                  }


class D154(D101, D150):
    _smbl_fmt = Symbol.get_format()
    _fields = D150._fields + [('smbl', f'{_smbl_fmt}')]  # symbol id

    _wpt_class = {0: 'apt_wpt_class',     # airport waypoint class
                  1: 'int_wpt_class',     # intersection waypoint class
                  2: 'ndb_wpt_class',     # NDB waypoint class
                  3: 'vor_wpt_class',     # VOR waypoint class
                  4: 'usr_wpt_class',     # user defined waypoint class
                  5: 'rwy_wpt_class',     # airport runway threshold waypoint class
                  6: 'aint_wpt_class',    # airport intersection waypoint class
                  7: 'andb_wpt_class',    # airport NDB waypoint class
                  8: 'sym_wpt_class',     # user defined symbol-only waypoint class
                  9: 'locked_wpt_class',  # locked waypoint class
                  }

    def __init__(self, smbl=0, **kwargs):
        super().__init__(**kwargs)
        self.smbl = smbl


class D155(D101, D150):
    _smbl_fmt = Symbol.get_format()
    _fields = D150._fields + [('smbl', f'{_smbl_fmt}'),    # symbol id
                              ('dspl', 'B'),               # display option
                              ]
    _dspl = {1: 'dspl_smbl_only',  # display symbol by itself
             3: 'dspl_smbl_name',  # display symbol with waypoint name
             5: 'dspl_smbl_cmnt',  # display symbol with comment
             }
    _wpt_class = {0: 'apt_wpt_class',     # airport waypoint class
                  1: 'int_wpt_class',     # intersection waypoint class
                  2: 'ndb_wpt_class',     # NDB waypoint class
                  3: 'vor_wpt_class',     # VOR waypoint class
                  4: 'usr_wpt_class',     # user defined waypoint class
                  5: 'locked_wpt_class',  # locked waypoint class
                  }

    def __init__(self, smbl=0, dspl=1, **kwargs):
        super().__init__(**kwargs)
        self.smbl = smbl
        self.dspl = dspl

    def get_dspl(self):
        """Return the display attribute value.

        """
        return self._dspl.get(self.dspl, 1)


class RteHdr(DataType):

    def is_valid_ident(self):
        pattern = self.re_upcase_digit_space_hyphen
        return self.is_valid_charset(pattern, self.ident)

    def is_valid_cmnt(self):
        pattern = self.re_upcase_digit_space_hyphen
        return self.is_valid_charset(pattern, self.cmnt)


class D200(RteHdr):
    _fields = [('nmbr', 'B'),  # route number
               ]

    def __init__(self, nmbr=0):
        self.nmbr = nmbr


class D201(RteHdr):
    _fields = [('nmbr', 'B'),    # route number
               ('cmnt', '20s'),  # comment
               ]

    def __init__(self, nmbr=0, cmnt=b''):
        self.nmbr = nmbr
        self.cmnt = cmnt


class D202(RteHdr):
    _fields = [('ident', 'n'),  # identifier
               ]

    def __init__(self, ident=b''):
        self.ident = ident


class RteLink(DataType):

    def is_valid_ident(self):
        pattern = self.re_upcase_digit_space_hyphen
        self.is_valid_charset(pattern, self.ident)


class D210(RteLink):
    _fields = [('lnk_class', 'H'),     # link class
               ('subclass', '(18B)'),  # subclass
               ('ident', 'n'),         # identifier
               ]
    _lnk_class = {0:   'line',
                  1:   'link',
                  2:   'net',
                  3:   'direct',
                  255: 'snap'}

    def __init__(self, lnk_class=0, subclass=(0, 0, 0, 0, 0, 0, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255), ident=b''):
        self.lnk_class = lnk_class
        self.subclass = subclass
        self.ident = ident

    def get_lnk_class(self):
        """Return the link class value.

        """
        return self._lnk_class.get(self.lnk_class, 0)


class TrkPoint(DataType):

    def get_posn(self):
        return Position(*self.posn)

    def get_datetime(self):
        return Time(self.time).get_datetime()

    def is_valid_time(self):
        """Return whether the time is valid.

        The device ignores the time value for track log points that are not
        recorded by the device itself, but transferred to the device by an
        external host. Some devices use 0x7FFFFFFF or 0xFFFFFFFF instead of zero
        to indicate an invalid time value.

        """
        return not ( self.time == 0 or
                     self.time == 4294967295 or  # 0xFFFFFFFF
                     self.time == 4294967167 )   # 0x7FFFFFFF


class D300(TrkPoint):
    _posn_fmt = Position.get_format()
    _time_fmt = Time.get_format()
    _fields = [('posn', f'({_posn_fmt})'),  # position
               ('time', f'{_time_fmt}'),    # time, invalid if 0xFFFFFFFF
               ('new_trk', '?'),            # new track segment?
               ]

    def __init__(self, posn=[0, 0], time=4294967295, new_trk=False):
        self.posn = posn
        self.time = time
        self.new_trk = new_trk


class D301(D300):
    _posn_fmt = Position.get_format()
    _time_fmt = Time.get_format()
    _fields = [('posn', f'({_posn_fmt})'),  # position
               ('time', f'{_time_fmt}'),    # time, invalid if 0xFFFFFFFF
               ('alt', 'f'),                # altitude in meters
               ('dpth', 'f'),               # depth in meters
               ('new_trk', '?'),            # new track segment?
               ]

    def __init__(self, alt=1.0e25, dpth=1.0e25, **kwargs):
        super().__init__(**kwargs)
        self.alt = alt
        self.dpth = dpth

    def is_valid_alt(self):
        """Return whether the altitude is valid.

        A “alt” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.alt:.1e}" == "1.0e+25"

    def is_valid_dpth(self):
        """Return whether the depth is valid.

        A “dpth” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.dpth:.1e}" == "1.0e+25"


class D302(D300):
    _posn_fmt = Position.get_format()
    _time_fmt = Time.get_format()
    _fields = [('posn', f'({_posn_fmt})'),  # position
               ('time', f'{_time_fmt}'),    # time, invalid if 0xFFFFFFFF
               ('alt', 'f'),                # altitude in meters, invalid if 1.0e25
               ('dpth', 'f'),               # depth in meters, invalid if 1.0e25
               ('temp', 'f'),               # temp in degrees C, invalid if 1.0e25
               ('new_trk', '?'),            # new track segment?
               ]

    def __init__(self, alt=1.0e25, dpth=1.0e25, temp=1.0e25, **kwargs):
        super().__init__(**kwargs)
        self.alt = alt
        self.dpth = dpth
        self.temp = temp

    def is_valid_alt(self):
        """Return whether the altitude is valid.

        A “alt” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.alt:.1e}" == "1.0e+25"

    def is_valid_dpth(self):
        """Return whether the depth is valid.

        A “dpth” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.dpth:.1e}" == "1.0e+25"

    def is_valid_temp(self):
        """Return whether the temperature is valid.

        A “temp” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.temp:.1e}" == "1.0e+25"


class D303(D301):
    _posn_fmt = Position.get_format()
    _time_fmt = Time.get_format()
    _fields = [('posn', f'({_posn_fmt})'),  # position
               ('time', f'{_time_fmt}'),    # time, invalid if 0xFFFFFFFF
               ('alt', 'f'),                # altitude in meters, invalid if 1.0e25
               ('heart_rate', 'B'),         # heart rate in beats per minute, invalid if 0
               ]

    def __init__(self, posn=[0, 0], time=4294967295, alt=1.0e25, heart_rate=0):
        self.posn = posn
        self.time = time
        self.alt = alt
        self.heart_rate = heart_rate

    def is_valid_alt(self):
        """Return whether the altitude is valid.

        A “alt” value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.alt:.1e}" == "1.0e+25"

    def is_valid_heart_rate(self):
        """Return whether the heart rate is valid.

        A “heart_rate” value of 0 indicates that this parameter is not supported or unknown.

        """
        return not self.heart_rate == 0


class D304(D303):
    _fields = D303._fields + [('distance', 'f'),    # distance traveled in meters, invalid if 1.0e25
                              ('cadence', 'B'),     # in revolutions per minute, invalid if 0xFF
                              ('sensor', '?'),      # is a wheel sensor present?
                              ]

    def __init__(self, distance=1.0e25, heart_rate=0, cadence=255, sensor=False, **kwargs):
        super().__init__(**kwargs)
        self.distance = distance
        self.heart_rate = heart_rate
        self.cadence = cadence
        self.sensor = sensor

    def is_valid_distance(self):
        """Return whether the distance is valid.

        A “distance” value of 0 indicates that this parameter is not supported or unknown.

        """
        return not self.distance == 0

    def is_valid_cadence(self):
        """Return whether the cadence is valid.

        A “cadence” value of 0xFF indicates that this parameter is not supported or unknown.

        """
        return not self.cadence == 255


class TrkHdr(DataType):

    def is_valid_trk_ident(self):
        return self.is_valid_charset(self.re_upcase_digit_space_hyphen, self.trk_ident)


class D310(TrkHdr):
    _fields = [('dspl', '?'),       # display on the map?
               ('color', 'B'),      # color
               ('trk_ident', 'n'),  # track identifier
               ]
    _color = {0:   'clr_black',
              1:   'clr_dark_red',
              2:   'clr_dark_green',
              3:   'clr_dark_yellow',
              4:   'clr_dark_blue',
              5:   'clr_dark_magenta',
              6:   'clr_dark_cyan',
              7:   'clr_light_gray',
              8:   'clr_dark_gray',
              9:   'clr_red',
              10:  'clr_green',
              11:  'clr_yellow',
              12:  'clr_blue',
              13:  'clr_magenta',
              14:  'clr_cyan',
              15:  'clr_white',
              255: 'clr_default_color'
              }

    def __init__(self, dspl=True, color=255, trk_ident=b''):
        self.dspl = dspl
        self.color = color
        self.trk_ident = trk_ident

    def get_color(self):
        """Return the color value.

        """
        return self._color.get(self.color, 255)


class D311(TrkHdr):
    _fields = [('index', 'H'),  # unique among all tracks received from device
               ]

    def __init__(self, index=0):
        self.index = index


class D312(D310):
    _color = {0:   'clr_black',
              1:   'clr_dark_red',
              2:   'clr_dark_green',
              3:   'clr_dark_yellow',
              4:   'clr_dark_blue',
              5:   'clr_dark_magenta',
              6:   'clr_dark_cyan',
              7:   'clr_light_gray',
              8:   'clr_dark_gray',
              9:   'clr_red',
              10:  'clr_green',
              11:  'clr_yellow',
              12:  'clr_blue',
              13:  'clr_magenta',
              14:  'clr_cyan',
              15:  'clr_white',
              16:  'clr_transparent',
              255: 'clr_defaultcolor',
              }


class PrxWpt(Wpt):
    pass


class D400(PrxWpt, D100):
    _fields = D100._fields + [('dst', 'f')]  # proximity distance (meters)

    def __init__(self, dst=0, **kwargs):
        super().__init__(**kwargs)
        self.dst = dst


class D403(PrxWpt, D103):
    _fields = D103._fields + [('dst', 'f')]  # proximity distance (meters)

    def __init__(self, dst=0, **kwargs):
        super().__init__(**kwargs)
        self.dst = dst


class D450(PrxWpt, D150):
    _fields = [('idx', 'i')  # proximity index
               ] + \
               D150._fields + \
               [('dst', 'f')]  # proximity distance (meters)

    def __init__(self, idx=0, dst=0, **kwargs):
        super().__init__(**kwargs)
        self.idx = idx
        self.dst = dst


class Almanac(DataType):

    def is_valid(self):
        """Return whether the data is valid.

        If the data for a particular satellite is missing or if the satellite is
        non-existent, then the week number for that satellite must be set to a
        negative number to indicate that the data is invalid.

        """
        return not self.wn < 0

class D500(Almanac):
    _fields = [('wn', 'H'),     # week number (weeks)
               ('toa', 'f'),    # almanac data reference time (s)
               ('af0', 'f'),    # clock correction coefficient (s)
               ('af1', 'f'),    # clock correction coefficient (s/s)
               ('e', 'f'),      # eccentricity (-)
               ('sqrta', 'f'),  # square root of semi-major axis (a)(m**1/2)
               ('m0', 'f'),     # mean anomaly at reference time (r)
               ('w', 'f'),      # argument of perigee (r)
               ('omg0', 'f'),   # right ascension (r)
               ('odot', 'f'),   # rate of right ascension (r/s)
               ('i', 'f'),      # inclination angle (r)
               ]

    def __init__(self, wn=0, toa=0, af0=0, af1=0, e=0, sqrta=0, m0=0, w=0, omg0=0, odot=0, i=0):
        self.wn = wn,
        self.toa = toa,
        self.af0 = af0,
        self.af1 = af1,
        self.e = e,
        self.sqrta = sqrta,
        self.m0 = m0,
        self.w = w,
        self.omg0 = omg0,
        self.odot = odot,
        self.i = i


class D501(D500):
    _fields = D500._fields + [('hlth', 'B')]  # almanac health

    def __init__(self, hlth=0, **kwargs):
        super().__init__(**kwargs)
        self.hlth = hlth


class D550(D500):
    _fields = [('svid', 'B')  # satellite id
               ] + D500._fields

    def get_prn(self):
        """Return the PRN.

        The “svid” member identifies a satellite in the GPS constellation as
        follows: PRN-01 through PRN-32 are indicated by “svid” equal to 0
        through 31, respectively.

        """
        return self.svid + 1


class D551(D501):
    _fields = [('svid', 'B')  # satellite id
               ] + D501._fields

    def get_prn(self):
        """Return the PRN.

        The “svid” member identifies a satellite in the GPS constellation as
        follows: PRN-01 through PRN-32 are indicated by “svid” equal to 0
        through 31, respectively.

        """
        return self.svid + 1


class DateTime(DataType):
    def get_datetime(self):
        """Return a datetime object of the time.

        """
        return datetime(self.year,
                        self.month,
                        self.day,
                        self.hour,
                        self.minute,
                        self.second)

    def __str__(self):
        datetime = self.get_datetime()
        return str(datetime)


class D600(DateTime):
    _fields = [('month', 'B'),   # month (1-12)
               ('day', 'B'),     # day (1-31)
               ('year', 'H'),    # year (1990 means 1990)
               ('hour', 'H'),    # hour (0-23)
               ('minute', 'B'),  # minute (0-59)
               ('second', 'B'),  # second (0-59)
               ]


class FlightBookRecord(DataType):

    def get_takeoff_datetime(self):
        return Time(self.takeoff_time).get_datetime()

    def get_landing_datetime(self):
        return Time(self.landing_time).get_datetime()

    def get_takeoff_posn(self):
        return Position(*self.takeoff_posn)

    def get_landing_posn(self):
        return Position(*self.landing_posn)


class D650(FlightBookRecord):
    _time_fmt = Time.get_format()
    _posn_fmt = Position.get_format()
    _fields = [('takeoff_time', f'{_time_fmt}'),    # Time flight started
               ('landing_time', f'{_time_fmt}'),    # Time flight ended
               ('takeoff_posn', f'({_posn_fmt})'),  # Takeoff lat/lon
               ('landing_posn', f'({_posn_fmt})'),  # Landing lat/lon
               ('night_time', 'I'),                 # Seconds flown in night time conditions
               ('num_landings', 'I'),               # Number of landings during the flight
               ('max_speed', 'I'),                  # Max velocity during flight (meters/sec)
               ('max_alt', 'I'),                    # Max altitude above WGS84 ellipsoid (meters)
               ('distance', 'f'),                   # Distance of flight (meters)
               ('cross_country_flag', 'f'),         # Flight met cross country criteria
               ('departure_name', 'f'),             # Name of airport
               ('departure_ident', 'B'),            # ID of airport
               ('arrival_name', 'n'),               # Name of airport
               ('arrival_ident', 'n'),              # ID of airport
               ('ac_id', 'n'),                      # N Number of airplane
               ]


class D700(RadianPosition):
    _fields = RadianPosition._fields


class PVT(DataType):

    def is_legacy(self, product_description):
        """Return whether the device uses a legacy software version.

        According to the specification some devices use different enumerated
        values for fix in older software versions. However, this list of devices
        is ambiguous (eTrex Summit is named twice) and doesn't include product
        ID's. Therefore, we have no reliable way to ascertain whether the device
        is legacy or not.

        This method checks the device name and software version in the product
        description. The list of devices and the last software version in which
        these different values are used is:

        ======================= ==============
         Device                  Last Version
        ======================= ==============
         eMap                            2.64
         GPSMAP 162                      2.62
         GPSMAP 295                      2.19
         eTrex                           2.10
         eTrex Summit                    2.07
         StreetPilot III                 2.10
         eTrex Japanese                  2.10
         eTrex Venture/Mariner           2.20
         eTrex Europe                    2.03
         GPS 152                         2.01
         eTrex Chinese                   2.01
         eTrex Vista                     2.12
         eTrex Summit Japanese           2.01
         eTrex Summit                    2.24
         eTrex GolfLogix                 2.49
        ======================= ==============

        """
        devices = {
            "emap": 2.64,
            "gpsmap 162": 2.62,
            "gpsmap 295": 2.19,
            "etrex": 2.10,
            "streetpilot iii": 2.10,
            "etrex japanese": 2.10,
            "etrex venture": 2.20,
            "etrex mariner": 2.20,
            "etrex europe": 2.03,
            "gps 152": 2.01,
            "etrex chinese": 2.01,
            "etrex vista": 2.12,
            "etrex summit japanese": 2.01,
            "etrex summit": 2.24,
            "etrex golflogix": 2.49,
        }
        pattern = r'(?P<device>[\w ]+) Software Version (?P<version>\d+.\d+)'
        m = re.search(pattern, product_description.decode('ascii'))
        device = m.group('device').lower()
        version = float(m.group('version'))
        last_version = devices.get(device)
        if last_version and version <= last_version:
            return True
        else:
            return False

    def get_posn(self):
        return RadianPosition(*self.posn)

    def get_msl_alt(self):
        """Return the altitude above mean sea level.

        To find the altitude above mean sea level, add “msl_hght” (height of the
        WGS 84 ellipsoid above mean sea level) to “alt” (altitude above the WGS
        84 ellipsoid).

        """
        return self.msl_hght + self.alt

    def get_datetime(self):
        """Return a datetime object of the time.

        """
        seconds = math.floor(self.tow - self.leap_scnds)
        days = self.wn_days
        delta = timedelta(days=days, seconds=seconds)
        return self.epoch + delta

    def get_fix(self, product_description=None):
        """Return the fix value.

        The default enumerated values for the “fix” member of the D800 PVT are
        shown below. It is important for the host to inspect this value to
        ensure that other data members in the D800 PVT are valid. No indication
        is given as to whether the device is in simulator mode versus having an
        actual position fix.

        Some legacy devices use values for fix that are one more than the
        default.

        """
        fix = self.fix
        if product_description and self.is_legacy(product_description):
            fix += 1

        return self._fix.get(fix)


class D800(PVT):
    _posn_fmt = RadianPosition.get_format()
    _fields = [('alt', 'f'),                # altitude above WGS 84 ellipsoid (meters)
               ('epe', 'f'),                # estimated position error, 2 sigma (meters)
               ('eph', 'f'),                # epe, but horizontal only (meters)
               ('epv', 'f'),                # epe, but vertical only (meters)
               ('fix', 'H'),                # type of position fix
               ('tow', 'd'),                # time of week (seconds)
               ('posn', f'({_posn_fmt})'),  # latitude and longitude (radians)
               ('east', 'f'),               # velocity east (meters/second)
               ('north', 'f'),              # velocity north (meters/second)
               ('up', 'f'),                 # velocity up (meters/second)
               ('msl_hght', 'f'),           # height of WGS84 ellipsoid above MSL(meters)
               ('leap_scnds', 'h'),         # difference between GPS and UTC (seconds)
               ('wn_days', 'I'),            # week number days
               ]
    _fix = {0: 'unusable',  # failed integrity check
            1: 'invalid',   # invalid or unavailable
            2: '2D',        # two dimensional
            3: '3D',        # three dimensional
            4: '2D_diff',   # two dimensional differential
            5: '3D_diff',   # three dimensional differential
            }


class Lap(DataType):

    def get_start_datetime(self):
        return Time(self.start_time).get_datetime()

    def get_begin(self):
        return Position(*self.begin)

    def get_end(self):
        return Position(*self.end)


class D906(Lap):
    _time_fmt = Time.get_format()
    _posn_fmt = Position.get_format()
    _fields = [('start_time', f'{_time_fmt}'),
               ('total_time', 'I'),          # In hundredths of a second
               ('total_dist', 'f'),          # In meters
               ('begin', f'({_posn_fmt})'),  # Invalid if both lat and lon are 0x7FFFFFFF
               ('end', f'({_posn_fmt})'),    # Invalid if both lat and lon are 0x7FFFFFFF
               ('calories', 'H'),
               ('track_index', 'B'),         # See below
               ('unused', 'B'),              # Unused. Set to 0.
               ]


class Step(DataType):
    _fields = [('custom_name', '16s'),            # Null-terminated step name
               ('target_custom_zone_low', 'f'),   # See below
               ('target_custom_zone_high', 'f'),  # See below
               ('duration_value', 'H'),           # See below
               ('intensity', 'B'),                # Same as D1001
               ('duration_type', 'B'),            # See below
               ('target_type', 'B'),              # See below
               ('target_value', 'B'),             # See below
               ('unused', 'H'),                   # Unused. Set to 0
               ]


class Run(DataType):
    _fields = [('track_index', 'I'),      # Index of associated track
               ('first_lap_index', 'I'),  # Index of first associated lap
               ('last_lap_index', 'I'),   # Index of last associated lap
               ('sport_type', 'B'),       # See below
               ('program_type', 'B'),     # See below
               ]
    _sport_type = {0: 'running',
                   1: 'biking',
                   2: 'other',
                   }
    _program_type = {0: 'none',
                     1: 'virtual_partner',  # Completed with Virtual Partner
                     2: 'workout',          # Completed as part of a workout
                     }


class VirtualPartner(DataType):
    _fields = ([('time', 'I'),      # Time result of virtual partner
                ('distance', 'f'),  # Distance result of virtual partner
                ])


class Workout(DataType):
    _fields = [('num_valid_steps', 'I'),  # Number of valid steps (1-20)
               ('steps', '/0[32c]'),      # Steps
               ('name', '16s'),           # Null-terminated workout name
               ('sport_type', 'B'),       # Same as D1000
               ]
    _sport_type = {0: 'running',
                   1: 'biking',
                   2: 'other',
                   }

    def get_steps(self):
        steps = []
        for data in self.steps:
            step = Step()
            step.unpack(data)
            steps.append(step)
        return steps


class D1000(Run):
    _fields = Run._fields + \
        [('unused', 'H')  # Unused. Set to 0.
         ] + \
         VirtualPartner._fields + \
         Workout._fields


class D1001(Lap):
    _time_fmt = Time.get_format()
    _posn_fmt = Position.get_format()
    _fields = [('index', 'I'),                  # Unique among all laps received from device
               ('start_time', f'{_time_fmt}'),  # Start of lap time
               ('total_time', 'I'),             # Duration of lap, in hundredths of a second
               ('total_dist', 'f'),             # Distance in meters
               ('max_speed;', 'f'),             # In meters per second
               ('begin', f'({_posn_fmt})'),     # Invalid if both lat and lon are 0x7FFFFFFF
               ('end', f'({_posn_fmt})'),       # Invalid if both lat and lon are 0x7FFFFFFF
               ('calories', 'H'),               # Calories burned this lap
               ('avg_heart_rate', 'B'),         # In beats-per-minute, invalid if 0
               ('max_heart_rate', 'B'),         # In beats-per-minute, invalid if 0
               ('intensity', 'B'),
               ]
    _intensity = {0: 'active',  # This is a standard, active lap
                  1: 'rest',    # This is a rest lap in a workout
                  }


class D1002(Workout):
    pass


class WorkoutOccurrence(DataType):
    _fields = [('workout_name', '16s'),  # Null-terminated workout name
               ('day', 'I'),             # Day on which the workout falls
               ]


class D1003(WorkoutOccurrence):
    _fields = WorkoutOccurrence._fields


class HeartRateZones(DataType):
    _fields = [('low_heart_rate', 'B'),   # In beats-per-minute, must be > 0
               ('high_heart_rate', 'B'),  # In beats-per-minute, must be > 0
               ('unused', 'H'),           # Unused. Set to 0.
               ]


class SpeedZones(DataType):
    _fields = [('low_speed', 'f'),   # In meters-per-second
               ('high_speed', 'f'),  # In meters-per-second
               ('name', '16s'),      # Null-terminated speed-zone name
               ]


class Activities(DataType):
    _fields = [('gear_weight', 'f'),     # Weight of equipment in kilograms
               ('max_heart_rate', 'B'),  # In beats-per-minute, must be > 0
               ('unused1', 'B'),         # Unused. Set to 0.
               ('unused2', 'H'),         # Unused. Set to 0.
               ]


class FitnessUserProfile(DataType):
    _fields = [('weight', 'f'),       # User’s weight, in kilograms
               ('birth_year', 'H'),   # No base value (i.e. 1990 means 1990)
               ('birth_month', 'B'),  # 1 = January, etc.
               ('birth_day', 'B'),    # 1 = first day of month, etc.
               ('gender', 'B'),       # See below
               ]
    _gender = {0: 'female',
               1: 'male',
               }

    def get_gender(self):
        return self._gender.get(self.gender)


class D1004(FitnessUserProfile):
    pass


class WorkoutLimits(DataType):
    _fields = [('max_workouts', 'L'),              # Maximum workouts
               ('max_unscheduled_workouts', 'L'),  # Maximum unscheduled workouts
               ('max_occurrences', 'L'),           # Maximum workout occurrences
               ]


class D1005(WorkoutLimits):
    pass


class Course(DataType):
    pass


class D1006(Course):
    _fields = [('index', 'H'),          # Unique among courses on device
               ('unused', 'H'),         # Unused. Set to 0.
               ('course_name', '16s'),  # Null-terminated, unique course name
               ('track_index', 'H'),    # Index of the associated track
               ]


class CourseLap(DataType):

    def get_begin(self):
        return Position(*self.begin)

    def get_end(self):
        return Position(*self.end)


class D1007(CourseLap):
    _posn_fmt = Position.get_format()
    _fields = [('course_index', 'H'),        # Index of associated course
               ('lap_index', 'H'),           # This lap’s index in the course
               ('total_time', 'L'),          # In hundredths of a second
               ('total_dist', 'f'),          # In meters
               ('begin', f'({_posn_fmt})'),  # Starting position of the lap. Invalid if both lat and lon are 0x7FFFFFFF
               ('end', f'({_posn_fmt})'),    # Final position of the lap. Invalid if both lat and lon are 0x7FFFFFFF
               ('avg_heart_rate', 'B'),      # In beats-per-minute, invalid if 0
               ('max_heart_rate', 'B'),      # In beats-per-minute, invalid if 0
               ('intensity', 'B'),           # Same as D1001
               ('avg_cadence', 'B'),         # In revolutions-per-minute, invalid if 0xFF
               ]


class D1008(Workout):
    pass


class D1009(Run):
    _fields = Run._fields + [('multisport', 'B'),
                                 ('unused1', 'B'),
                                 ('unused2', 'H'),
                                 ('quick_workout_time', 'I'),
                                 ('quick_workout_distance', 'f'),
                                 ]


class D1011(Lap):
    _time_fmt = Time.get_format()
    _posn_fmt = Position.get_format()
    _fields = [('index', 'H'),                  # Unique among all laps received from device
               ('unused', 'H'),                 # Unused. Set to 0.
               ('start_time', f'{_time_fmt}'),  # Start of lap time
               ('total_time', 'I'),             # Duration of lap, in hundredths of a second
               ('total_dist', 'f'),             # Distance in meters
               ('max_speed', 'f'),              # In meters per second
               ('begin', f'({_posn_fmt})'),     # Invalid if both lat and lon are 0x7FFFFFFF
               ('end', f'({_posn_fmt})'),       # Invalid if both lat and lon are 0x7FFFFFFF
               ('calories', 'H'),               # Calories burned this lap
               ('avg_heart_rate', 'B'),         # In beats-per-minute, invalid if 0
               ('max_heart_rate', 'B'),         # In beats-per-minute, invalid if 0
               ('intensity', 'B'),              # Same as D1001
               ('avg_cadence', 'B'),            # In revolutions-per-minute, invalid if 0xFF
               ('trigger_method', 'B'),         # See below
               ]
    _trigger_method = {0: 'manual',
                       1: 'distance',
                       2: 'location',
                       3: 'time',
                       4: 'heart_rate',
                       }

    def get_trigger_method(self):
        return self._trigger_method.get(self.trigger_method)


class D1010(Run):
    _time_fmt = Time.get_format()
    _fields = [('track_index', 'I'),      # Index of associated track
               ('first_lap_index', 'I'),  # Index of first associated lap
               ('last_lap_index', 'I'),   # Index of last associated lap
               ('sport_type', 'B'),       # Sport type (same as D1000)
               ('program_type', 'B'),     # See below
               ('multisport', 'B'),       # Same as D1009
               ('unused', 'B'),           # Unused. Set to 0.
               ('time', f'{_time_fmt}'),  # Time result of virtual partner
               ('distance', 'f'),         # Distance result of virtual partner
               ] + \
               Workout._fields  # Workout
    _program_type = {0: 'none',
                     1: 'virtual_partner',  # Completed with Virtual Partner
                     2: 'workout',          # Completed as part of a workout
                     3: 'auto_multisport',  # Completed as part of an auto MultiSport
                     }

    def get_datetime(self):
        return Time(self.time).get_datetime()


class CoursePoint(DataType):
    _time_fmt = Time.get_format()
    _fields = [('name', '11s'),                       # Null-terminated name
               ('unused1', 'B'),                      # Unused. Set to 0.
               ('course_index', 'H'),                 # Index of associated course
               ('unused2', 'H'),                      # Unused. Set to 0.
               ('track_point_time', f'{_time_fmt}'),  # Time
               ('point_type', 'B'),                   # See below
               ]
    _point_type = {0: 'generic',
                   1: 'summit',
                   2: 'valley',
                   3: 'water',
                   4: 'food',
                   5: 'danger',
                   6: 'left',
                   7: 'right',
                   8: 'straight',
                   9: 'first_aid',
                   10: 'fourth_category',
                   11: 'third_category',
                   12: 'second_category',
                   13: 'first_category',
                   14: 'hors_category',
                   15: 'sprint',
                   }

    def get_track_point_datetime(self):
        return Time(self.track_point_time).get_datetime()

    def get_point_type(self):
        return self._point_type.get(self.point_type)


class D1012(CoursePoint):
    pass


class CourseLimits(DataType):
    _fields = [('max_courses', 'I'),         # Maximum courses
               ('max_course_laps', 'I'),     # Maximum course laps
               ('max_course_pnt', 'I'),      # Maximum course points
               ('max_course_trk_pnt', 'I'),  # Maximum course track points
               ]


class D1013(CourseLimits):
    pass


class ExternalTimeSyncData(DataType):
    _time_fmt = Time.get_format()
    _fields = [('current_utc', f'{_time_fmt}'),  # Current UTC
               ('timezone_offset', 'i'),         # Local timezone in seconds from UTC
               ('is_dst_info_included', '?'),    # Is DST information valid?
               ('dst_adjustment', 'B'),          # DST adjustment in 15 minute increments
               ('dst_start', f'{_time_fmt}'),    # Specified in UTC
               ('dst_end', f'{_time_fmt}'),      # Specified in UTC
               ]

    def get_datetime(self):
        "Return timezone aware datetime object."
        datetime = Time(self.current_utc).get_datetime()
        return datetime.replace(tzinfo=self.timezone_offset)

    def get_dst(self):
        "Return Daylight Saving Time adjustment as timedelta."
        if self.is_dst_info_included:
            if self.dst_start < self.current_utc < self.dest_end:
                # convert DST adjustment value from quarters to minutes
                dst_adjustment = self.dst_adjustment * 15
                return timedelta(minutes=dst_adjustment)
            else:
                return timedelta(0)


class D1051(ExternalTimeSyncData):
    pass


class MemProperties(DataType):
    _fields = [('mem_region', 'H'),  # flash memory region for supplementary map
               ('max_tiles', 'H'),   # maximum number of map tiles that can be stored
               ('mem_size', 'I'),    # memory size
               ('unknown', 'I'),
               ]


class MemFile(DataType):
    _fields = [('unknown', 'I'),
               ('mem_region', 'H'),  # flash memory region for supplementary map
               ('subfile', 'n'),     # subfile in the IMG container file format,
                                     # zero length string for whole file
               ]

    def __init__(self, unknown=0, mem_region=10, subfile=''):
        self.unknown = unknown
        self.mem_region = mem_region
        self.subfile = subfile


class MemData(DataType):
    _fields = [('length', 'B'),
               ('data', '/0s'),
               ]


class MemRecord(DataType):
    _fields = [('index', 'B'),  # index of the record (starting with 0)
               ('chunk', '$'),
               ]


class MemChunk(DataType):
    _fields = [('offset', 'I'),
               ('chunk', '$'),
               ]

    def __init__(self, offset, chunk):
        self.offset = offset
        self.chunk = chunk


class MapProduct(DataType):
    _fields = [('pid', 'H'),   # product ID
               ('fid', 'H'),   # family ID
               ('name', 'n'),  # product name
               ]


class MapSegment(DataType):
    _fields = [('pid', 'H'),           # product ID
               ('fid', 'H'),           # family ID
               ('segment_id', 'I'),    # segment ID
               ('name', 'n'),          # product name
               ('segment_name', 'n'),  # segment name
               ('area_name', 'n'),     # area name
               ('segment_id2', 'I'),   # segment ID
               ('end_token', 'I'),     # always 0x00000000
               ]


class MapUnknown(DataType):
    _fields = [('pid', 'H'),       # product ID
               ('fid', 'H'),       # family ID
               ('unknown1', 'H'),
               ('unknown2', 'I'),
               ]


class MapUnlock(DataType):
    _fields = [('unlock_code', 'n'),  # Length is 25 characters. Characters are
                                      # upper case letters or digits
               ]


class MapSet(DataType):
    _fields = [('mapset_name', 'n'),
               ('auto_name', '?'),
               ]


class MPSRecord(DataType):
    _fields = [('type', 'B'),
               ('length', 'H'),
               ('content', '/1s'),
               ]
    _type = {'F': 'map_product_id',
             'L': 'map_segment_id',
             'P': 'map_unknown_id',
             'U': 'map_unlock_id',
             'V': 'map_set_id',
             }

    def __init__(self, type, length, content):
        self.type = type
        self.length = length
        self.content = content

    def get_type(self):
        """Return the type value.

        The characters shown are translated to numeric values using the ASCII
        character set.

        """
        return self._type.get(chr(self.type))

    def get_content(self):
        type = self.get_type()
        if type == 'map_product_id':
            log.debug(f"Record 'F': Product")
            datatype = MapProduct()
        elif type == 'map_segment_id':
            log.debug(f"Record 'L': Map segment")
            datatype = MapSegment()
        elif type == 'map_unknown_id':
            log.debug(f"Record 'P': Unknown")
            datatype = MapUnknown()
        elif type == 'map_unlock_id':
            log.debug(f"Record 'U': Unlock")
            datatype = MapUnlock()
        elif type == 'map_set_id':
            log.debug(f"Record 'V': Mapset")
            datatype = MapSet()
        datatype.unpack(self.content)
        return datatype


class MPSFile(DataType):
    """MPS file format.

    The Mapsource (MPS) file format contains a list of maps and their
    descriptions.

    The MPS file is used as a subfile in the IMG container file format and by
    MapSource software version 2.xx. Later versions of MapSource use a different
    file format with the same filename extension.

    The file format is reverse engineered by Herbert Oppmann
    (https://www.memotech.franken.de/FileFormats/Garmin_IMG_Subfiles_Format.pdf).

    The file consists of a sequence of variable sized records with the following
    structure:

    General record structure:

    ============= ==================
     Byte Number   Byte Description
    ============= ==================
               0   Record type
               1   Record length
          2 to n   Record content
    ============= ==================

    """
    _mps_record_fmt = MPSRecord.get_format()
    _fields = [('records', f'{{{_mps_record_fmt}}}'),
               ]

    def get_records(self):
        return [ MPSRecord(*record) for record in self.records ]


class RGBA(DataType):
    """RGBA is a sRGB format that uses 32 bits of data per pixel.

    Each channel (red, green, blue, and alpha) is allocated 8 bits per pixel
    (BPP). The alpha channel is unused. Instead, a color is used for
    transparency. Most devices make magenta (255,0,255) transparent.

    """
    _fields = [('red', 'B'),
               ('green', 'B'),
               ('blue', 'B'),
               ('unused', 'B'),
               ]

    def __init__(self, red=0, green=0, blue=0, unused=0):
        self.red = red
        self.green = green
        self.blue = blue
        self.unused = unused


class ImageProp(DataType):
    _fields = [('idx', 'H'),         # image index
               ('writable', '?'),    # writable?
               ('image_type', 'B'),  # image type (0 for screenshot or 2 for icon)
               ]

    def __init__(self, idx=0, writable=False, image_type=0):
        self.idx = idx
        self.writable = writable
        self.image_type = image_type


class ImageList(DataType):
    _image_prop_fmt = ImageProp.get_format()
    _fields = [('images', f'{{{_image_prop_fmt}}}'),
               ]

    def get_images(self):
        return [ ImageProp(*image) for image in self.images ]


class ImageName(DataType):
    _fields = (('name',  'n'),
               )


class ImageInformationHeader(DataType):
    _rgba_fmt = RGBA.get_format()
    _fields = (('unknown1', 'B'),
               ('bpp', 'B'),                 # bits per pixel or color depth
               ('unknown2', 'H'),
               ('height', 'H'),              # heigth in pixels
               ('width', 'H'),               # width in pixels
               ('bytewidth', 'H'),           # width in bytes?
               ('unknown3', 'H'),
               ('color', f'({_rgba_fmt})'),  # transparent color
               )

    def get_dimensions(self):
        return (self.width, self.height)

    def get_size(self):
        return (self.bpp * self.width * self.height) // 8

    def get_colors_used(self):
        if self.bpp <= 8:
            return 1 << self.bpp
        elif self.bpp == 24:
            return 0

    def get_color(self):
        return RGBA(*self.colors)


class ImageId(DataType):
    _fields = (('id',  'I'),
               )


class ImageColorTable(DataType):
    """BMP color table.

    The color table is a block of bytes listing the colors used by the image.
    Each pixel in an indexed color image is described by a number of bits (1, 4,
    or 8) which is an index of a single color described by this table. The
    purpose of the color palette in indexed color bitmaps is to inform the
    application about the actual color that each of these index values
    corresponds to.

    The colors in the color table are specified in the 4-byte per entry RGBA
    format. Each entry in the color table occupies 4 bytes, in the order blue, green,
    red, 0x00.

    """
    _id_fmt = ImageId.get_format()
    _rgba_fmt = RGBA.get_format()
    _fields = [('id', f'{_id_fmt}'),
               ('colors', f'{{{_rgba_fmt}}}'),
               ]

    def get_colors(self):
        return [ RGBA(*color) for color in self.colors ]

    def get_palette(self):
        """Returns the RGB color palette as a list of ints."""
        palette = []
        for color in self.get_colors():
            palette.extend([color.red, color.green, color.blue])
        return palette


class ImageChunk(DataType):
    _id_fmt = ImageId.get_format()
    _fields = [('id', f'{_id_fmt}'),
               ('data', '$'),
               ]

    def __init__(self, id=0, data=b''):
        self.id = id
        self.data = data


class BGR(DataType):
    """BGR is a sRGB format that uses 24 bits of data per per pixel.

    Each color channel (blue, green, and red) is allocated 8 bits per pixel
    (BPP).

    """
    _fields = [('blue', 'B'),
               ('green', 'B'),
               ('red', 'B'),
               ]

    def __init__(self, blue=0, green=0, red=0):
        self.blue = blue
        self.green = green
        self.red = red


class Screenshot(DataType):
    """Screenshot format.

    The data structure seems to be derived from the Microsoft Windows Bitmap
    file format. The format contains three sections: a bitmap information
    header, a color palette, and the bitmap data. This resembles a DIB data
    structure.

    The header isn't one of the known DIB headers. It seems to provide
    information on the screen dimensions and color depth.

    The color table is an array of structures that specify the red, green, and
    blue intensity values of each color in a color palette. Each pixel in the
    bitmap data stores a single value used as an index into the color palette.
    1-, 4-, and 8-bit BMP files are expected to always contain a color palette.
    16-, 24-, and 32-bit BMP files never contain color palettes. 16- and 32-bit
    BMP files contain bitfields mask values in place of the color palette.

    The pixel data is a series of values representing either color palette
    indices or actual RGB color values. Pixels are packed into bytes and
    arranged as scan lines. In a BMP file, each scan line must end on a 4-byte
    boundary, so one, two, or three bytes of padding may follow each scan line.
    Scan lines are stored from the bottom up with the origin in the lower-left
    corner.

    """
    _fields = [('section', 'I'),
               ('offset', 'I'),
               ]

    _section = { 0: 'header',
                 1: 'pixel_data',
                 2: 'color_table',
                }

    def get_section(self):
        return self._section.get(self.section)


class ScreenshotHeader(Screenshot):
    _fields = Screenshot._fields + [('unknown1', 'I'),   # width in bytes?
                                    ('bpp', 'I'),        # bits per pixel or color depth
                                    ('width', 'I'),      # width in pixels
                                    ('height', 'I'),     # heigth in pixels
                                    ('unknown2', 'I'),
                                    ('unknown3', 'I'),
                                    ('unknown4', 'I'),
                                    ]

    def get_dimensions(self):
        return (self.width, self.height)

    def get_size(self):
        return (self.bpp * self.width * self.height) // 8

    def get_colors_used(self):
        if self.bpp <= 8:
            return 1 << self.bpp
        elif self.bpp == 24:
            return 0


class ScreenshotColorTable(Screenshot):
    _bgr_fmt = BGR.get_format()
    _fields = Screenshot._fields + [('color', f'{_bgr_fmt}')]

    def get_colors(self):
        return BGR(*self.color)


class ScreenshotChunk(Screenshot):
    _fields = Screenshot._fields + [('chunk', '$')]


# Garmin models ==============================================

# For reference, here are some of the product ID numbers used by
# different Garmin models. Notice that this is not a one-to-one
# mapping in either direction!

product_ids = {
    7:    ("GPS 50"),
    13:   ("GPS 75"),
    14:   ("GPS 55"),
    15:   ("GPS 55 AVD"),
    18:   ("GPS 65"),
    20:   ("GPS 150"),
    22:   ("GPS 95 AVD"),
    23:   ("GPS 75"),
    24:   ("GPS 95"),
    25:   ("GPS 85"),
    29:   ("GPSMAP 205",
           "GPSMAP 210",
           "GPSMAP 220"),
    31:   ("GPS 40",
           "GPS 45"),
    33:   ("GNC 300"),
    34:   ("GPS 155",
           "GPS 165"),
    35:   ("GPS 95"),
    36:   ("GPS 95 AVD",
           "GPS 95 XL"),
    39:   ("GPS 89"),
    41:   ("GPS 38",
           "GPS 40",
           "GPS 45 XL",
           "GPS 45"),
    42:   ("GPS 75"),
    44:   ("GPSMAP 205"),
    45:   ("GPS 90"),
    47:   ("GPS 120"),
    48:   ("GPSMAP 195"),
    49:   ("GPSMAP 130",
           "GPSMAP 135 Sounder",
           "GPSMAP 175",
           "GPSMAP 230",
           "GPSMAP 235 Sounder"),
    50:   ("GPSCOM 170"),
    52:   ("GNC 250"),
    53:   ("GPSCOM 190"),
    55:   ("GPS 120 Chinese"),
    56:   ("GPS 38 Chinese",
           "GPS 40 Chinese",
           "GPS 45 Chinese"),
    59:   ("GPS II"),
    61:   ("GPS 125 Sounder"),
    62:   ("GPS 38 Japanese",
           "GPS 40 Japanese"),
    64:   ("GNC 250 XL",
           "GPS 150 XL"),
    67:   ("StreetPilot I"),  # gpsman
    71:   ("GPS III Pilot"),
    72:   ("GPS III"),
    73:   ("GPS II Plus"),
    74:   ("GPS 120 XL"),
    76:   ("GPSMAP 130 Chinese",
           "GPSMAP 230 Chinese"),
    77:   ("GPS 12 XL",
           "GPS 12"),
    87:   ("GPS 12"),
    88:   ("GPSMAP 215",
           "GPSMAP 225"),
    89:   ("GPSMAP 180"),  # gpsman
    95:   ("GPS 126",
           "GPS 128"),
    96:   ("GPS 12 XL",
           "GPS 12",
           "GPS 48"),
    97:   ("GPS II Plus"),
    98:   ("GNC 300 XL",
           "GPS 155 XL"),
    100:  ("GPS 126 Chinese",
           "GPS 128 Chinese"),
    103:  ("GPS 12 Arabic"),  # gpsman
    105:  ("GPS 12 XL Japanese"),
    106:  ("GPS 12 XL Chinese"),
    119:  ("GPS III Plus"),  # gpsman
    111:  ("eMap"),  # gpsman
    112:  ("GPS 92"),
    116:  ("GPS 12CX"),  # gpsman
    126:  ("GPSMAP 162"),  # gpsman
    128:  ("GPSMAP 295"),  # gpsman
    129:  ("GPS 12 Map"),  # gpsman
    130:  ("eTrex"),  # gpsman
    136:  ("GPSMAP 176"),  # gpsman
    138:  ("GPS 12"),  # gpsman
    141:  ("eTrex Summit"),  # gpsman
    145:  ("GPSMAP 196"),  # gpsman
    151:  ("StreetPilot 3"),  # gpsman
    154:  ("eTrex Venture",
           "eTrex Mariner"),  # gpsman
    155:  ("GPS 5"),  # gpsman
    156:  ("eTrex Europe"),  # gpsman
    169:  ("eTrex Vista"),  # gpsman
    173:  ("GPS 76"),  # gpsman
    177:  ("GPSMAP 76"),  # gpsman
    179:  ("eTrex Legend"),  # gpsman
    194:  ("GPSMAP 76S"),  # gpsman
    197:  ("Rino 110"),  # gpsman
    209:  ("Rino 120"),  # gpsman
    219:  ("eTrex Legend Japanese"),  # gpsman
    231:  ("Quest"),  # gpsman
    247:  ("GPS 72"),  # gpsman
    248:  ("Geko 201"),  # gpsman
    256:  ("Geko 301"),  # gpsman
    264:  ("Rino 130"),  # gpsman
    273:  ("GPS 18USB"),  # gpsman
    282:  ("Forerunner"),  # gpsman
    283:  ("Forerunner 301"),  # gpsman
    285:  ("GPSmap 276C"),  # gpsman
    289:  ("GPS 60"),  # gpsman
    291:  ("GPSMAP 60CS"),
    292:  ("GPSMAP 60CSx",
           "GPSMAP 76CSx"),  # gpsman
    295:  ("eTrex Summit"),  # gpsman
    308:  ("GPSMAP 60"),  # gpsman
    314:  ("ForeTrex"),  # gpsman
    315:  ("eTrex Legend C",
           "eTrex Vista C"),  # gpsman
    382:  ("StreetPilot c320"),  # gpsman
    404:  ("StreetPilot 2720"),  # gpsman
    411:  ("eTrex Legend"),  # gpsman
    419:  ("eTrex Venture"),  # gpsman
    420:  ("eTrex Vista"),  # gpsman
    421:  ("eTrex Legend Cx"),  # gpsman
    430:  ("GPS 72"),  # gpsman
    439:  ("GPSMAP 76"),  # gpsman
    450:  ("Edge 205",
           "Edge 305"),  # gpsman
    481:  ("StreetPilot c340"),  # gpsman
    484:  ("Forerunner 205",
           "Forerunner 305"),  # gpsman
    497:  ("StreetPilot c320",
           "StreetPilot c330"),  # gpsman
    532:  ("StreetPilot i2"),  # gpsman
    557:  ("GPSMAP 378"),  # gpsman
    574:  ("Geko 201"),  # gpsman
    577:  ("Rino 530HCx"),  # gpsman
    694:  ("eTrex Legend HCx",
           "eTrex Vista HCx"),  # gpsman
    695:  ("eTrex Summit HC",
           "eTrex Venture HC"),  # gpsman
    696:  ("eTrex H"),  # gpsman
    786:  ("eTrex Summit HC",
           "eTrex Venture HC"),  # gpsman
    811:  ("GPS 20x USB"),  # gpsman
    957:  ("eTrex Legend H"),  # gpsman
    1095: ("GPS 72H"),  # gpsman
}

# The table below provides the supported protocols of the devices that do
# not implement the Protocol Capability Protocol. The A000 Product Data
# Protocol, A600 Date and Time Initialization Protocol, and A700 Position
# Initialization Protocol are omitted from the table because all devices
# implement support them.
device_protocol_capabilities = {
    # ID   Version Link      Command   Waypoint          Route                     Track             Proximity         Almanac           Unknown
    112: ((0,     ("L001"), ("A010"), ("A100", "D152"), ("A200", "D201", "D152"), ("A300", "D300"), None,             ("A500", "D501"), ("A903"))),
    106: ((0,     ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501"))),
    105: ((0,     ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501"))),
    100: ((0,     ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501"))),
    98:  ((0,     ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D551"))),
    97:  ((0,     ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), None,             ("A500", "D501"))),
    96:  ((0,     ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501"))),
    95:  ((0,     ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501"))),
    88:  ((0,     ("L001"), ("A010"), ("A100", "D102"), ("A200", "D201", "D102"), ("A300", "D300"), ("A400", "D102"), ("A500", "D501"))),
    87:  ((0,     ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501"))),
    77:  ((3.61,  ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501")),
          (3.50,  ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), None,             ("A500", "D501")),
          (3.01,  ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), ("A400", "D403"), ("A500", "D501")),
          (0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D501"))),
    76:  ((0,     ("L001"), ("A010"), ("A100", "D102"), ("A200", "D201", "D102"), ("A300", "D300"), ("A400", "D102"), ("A500", "D501"))),
    74:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500"))),
    73:  ((0,     ("L001"), ("A010"), ("A100", "D103"), ("A200", "D201", "D103"), ("A300", "D300"), None,             ("A500", "D501"))),
    72:  ((0,     ("L001"), ("A010"), ("A100", "D104"), ("A200", "D201", "D104"), ("A300", "D300"), None,             ("A500", "D501"))),
    71:  ((0,     ("L001"), ("A010"), ("A100", "D155"), ("A200", "D201", "D155"), ("A300", "D300"), None,             ("A500", "D501"))),
    64:  ((0,     ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D551"))),
    62:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500"))),
    61:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500"))),
    59:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500"))),
    56:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500"))),
    55:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500"))),
    53:  ((0,     ("L001"), ("A010"), ("A100", "D152"), ("A200", "D201", "D152"), ("A300", "D300"), None,             ("A500", "D501"), ("A903"))),
    52:  ((0,     ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D550"))),
    50:  ((0,     ("L001"), ("A010"), ("A100", "D152"), ("A200", "D201", "D152"), ("A300", "D300"), None,             ("A500", "D501"))),
    49:  ((0,     ("L001"), ("A010"), ("A100", "D102"), ("A200", "D201", "D102"), ("A300", "D300"), ("A400", "D102"), ("A500", "D501"))),
    48:  ((0,     ("L001"), ("A010"), ("A100", "D154"), ("A200", "D201", "D154"), ("A300", "D300"), None,             ("A500", "D501"), ("A903"))),
    47:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500"))),
    45:  ((0,     ("L001"), ("A010"), ("A100", "D152"), ("A200", "D201", "D152"), ("A300", "D300"), None,             ("A500", "D500"), ("A903"))),
    44:  ((0,     ("L001"), ("A010"), ("A100", "D101"), ("A200", "D201", "D101"), ("A300", "D300"), ("A400", "D101"), ("A500", "D500"))),
    42:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500"))),
    41:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500"))),
    39:  ((0,     ("L001"), ("A010"), ("A100", "D151"), ("A200", "D201", "D151"), ("A300", "D300"), None,             ("A500", "D500"), ("A903"))),
    36:  ((3.00,  ("L001"), ("A010"), ("A100", "D152"), ("A200", "D200", "D152"), ("A300", "D300"), None,             ("A500", "D500"), ("A903")),
          (0,     ("L001"), ("A010"), ("A100", "D152"), ("A200", "D200", "D152"), ("A300", "D300"), ("A400", "D152"), ("A500", "D500"), ("A903"))),
    35:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500"))),
    34:  ((0,     ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D550"))),
    33:  ((0,     ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D550"))),
    31:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D201", "D100"), ("A300", "D300"), None,             ("A500", "D500"))),
    29:  ((4.00,  ("L001"), ("A010"), ("A100", "D102"), ("A200", "D201", "D102"), ("A300", "D300"), ("A400", "D102"), ("A500", "D500")),
          (0,     ("L001"), ("A010"), ("A100", "D101"), ("A200", "D201", "D101"), ("A300", "D300"), ("A400", "D101"), ("A500", "D500"))),
    25:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500"))),
    24:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500"))),
    23:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500"))),
    22:  ((0,     ("L001"), ("A010"), ("A100", "D152"), ("A200", "D200", "D152"), ("A300", "D300"), ("A400", "D152"), ("A500", "D500"), ("A903"))),
    20:  ((0,     ("L002"), ("A011"), ("A100", "D150"), ("A200", "D201", "D150"), None,             ("A400", "D450"), ("A500", "D550"))),
    18:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500"))),
    15:  ((0,     ("L001"), ("A010"), ("A100", "D151"), ("A200", "D200", "D151"), None,             ("A400", "D151"), ("A500", "D500"))),
    14:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), None,             ("A400", "D400"), ("A500", "D500"))),
    13:  ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), ("A300", "D300"), ("A400", "D400"), ("A500", "D500"))),
    7:   ((0,     ("L001"), ("A010"), ("A100", "D100"), ("A200", "D200", "D100"), None,             None,             ("A500", "D500"))),
}


class Garmin:
    """Garmin GPS device object.

    The class provides methods to communicate with the hardware.

    Most GNU/Linux distributions use a kernel module called ``garmin_gps`` to
    make a USB Garmin device accessible via a serial port. In order to
    communicate with a Windows computer via a serial link, Garmin USB drivers
    need to be installed. To communicate with a Garmin device connected to the
    serial port ``/dev/ttyUSB0``, you could try this:

    >>> from garmin import garmin
    >>> port = '/dev/ttyUSB0'
    >>> phys = garmin.SerialLink(port)
    >>> gps = garmin.Garmin(phys)
    >>> print(gps.product_data)

    Alternatively, internal USB support can be used. For this to work on
    GNU/Linux, you probably should remove and blacklist the ``garmin_gps``
    kernel module.

    >>> from garmin import garmin
    >>> phys = garmin.USBLink()
    >>> gps = garmin.Garmin(phys)
    >>> print(gps.product_data)

    """
    protocol_keys = {
        'L000': 'link_protocol',
        'L001': 'link_protocol',
        'L002': 'link_protocol',
        'A000': 'product_data_protocol',
        'A001': 'protocol_capability_protocol',
        'A010': 'device_command_protocol',
        'A011': 'device_command_protocol',
        'T001': 'transmission_protocol',
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
        'A900': 'map_transfer_protocol',
        'A902': 'map_unlock_protocol',
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
        #: Basic Link Protocol
        self.link = L000(self.phys)
        #: Product Data Protocol
        self.product_data_protocol = A000(self.link)
        self.product_data = self.product_data_protocol.get_product_data()
        #: Product ID
        self.product_id = self.product_data.product_id
        #: Software version
        self.software_version = self.product_data.software_version / 100
        #: Product description
        self.product_description = self.product_data.product_description
        self.protocol_capability = A001(self.link)
        #: Protocol capabilities and device-specific data types
        self.supported_protocols = self._get_protocols()
        self.registered_protocols = self._register_protocols(self.supported_protocols)
        #: Link Protocol
        self.link = self._create_protocol('link_protocol', self.phys)
        #: Device Command Protocol
        self.command = self._create_protocol('device_command_protocol', self.link)
        #: Transmission Protocol
        self.transmission = self._create_protocol('transmission_protocol', self.phys, self.link, self.command)
        #: Waypoint Transfer Protocol
        self.waypoint_transfer = self._create_protocol('waypoint_transfer_protocol', self.link, self.command)
        #: Waypoint Category Transfer Protocol
        self.waypoint_category_transfer = self._create_protocol('waypoint_category_transfer_protocol', self.link, self.command)
        #: Route Transfer Protocol
        self.route_transfer = self._create_protocol('route_transfer_protocol', self.link, self.command)
        #: Track Log Transfer Protocol
        self.track_log_transfer = self._create_protocol('track_log_transfer_protocol', self.link, self.command)
        #: Proximity Waypoint Transfer Protocol
        self.proximity_waypoint_transfer = self._create_protocol('proximity_waypoint_transfer_protocol', self.link, self.command)
        #: Almanac Transfer Protocol
        self.almanac_transfer = self._create_protocol('almanac_transfer_protocol', self.link, self.command)
        #: Date And Time Initialization Protocol
        self.date_and_time_initialization = self._create_protocol('date_and_time_initialization_protocol', self.link, self.command)
        #: Flightbook Transfer Protocol
        self.flightbook_transfer = self._create_protocol('flightbook_transfer_protocol', self.link, self.command)
        #: Position Initialization Protocol
        self.position_initialization = self._create_protocol('position_initialization_protocol', self.link, self.command)
        #: PVT Protocol
        self.pvt = self._create_protocol('pvt_protocol', self.link, self.command)
        #: Map Transfer Protocol
        self.map_transfer = self._create_protocol('map_transfer_protocol', self.link, self.command)
        #: Map Unlock Protocol
        self.map_unlock = self._create_protocol('map_unlock_protocol', self.link, self.command)
        #: Lap Transfer Protocol
        self.lap_transfer = self._create_protocol('lap_transfer_protocol', self.link, self.command)
        #: Run Transfer Protocol
        self.run_transfer = self._create_protocol('run_transfer_protocol', self.link, self.command)
        #: Screenshot Transfer Protocol
        self.screenshot_transfer = ScreenshotTransfer(self.link, self.command)
        #: Image Transfer Protocol
        self.image_transfer = ImageTransfer(self.link, self.command)

    @staticmethod
    def _class_by_name(name):
        return globals()[name]

    def _lookup_protocols(self, product_id, software_version):
        log.info("Look up protocols by Product ID and software version...")
        model = device_protocol_capabilities.get(product_id)
        if model is None:
            raise ValueError(f"Unknown Product ID: {product_id}")
        for capabilities in model:
            version = capabilities[0]
            if software_version > version:
                break
            protocols = [protocol for protocol in capabilities[1:] if protocol]
            protocols.append(("P000"))
            protocols.append(("A000"))
            protocols.append(("A600", "D600"))
            protocols.append(("A700", "D700"))

        return protocols

    def _get_protocols(self):
        """Return the protocol capabilities and device-specific data types.

        First wait for the device to report Protocol Capabilities Protocol data.
        If this protocol is not supported, the capabilities are looked up in the
        dictionary device_protocol_capabilities.

        """
        try:
            log.info("Get supported protocols and data types...")
            protocols = self.protocol_capability.get_protocols()
        except LinkError:
            log.info("Protocol Capability Protocol not supported by the device")
            try:
                protocols = self._lookup_protocols(self.product_id, self.software_version)
            except KeyError:
                raise ProtocolError("Couldn't determine protocol capabilities")
        log.debug(f"Supported protocols and data types: {protocols}")

        return protocols

    def _register_protocols(self, supported_protocols):
        """Register the supported protocols."""
        protocols = {}
        for protocol_datatypes in supported_protocols:
            protocol = protocol_datatypes[0]
            datatypes = protocol_datatypes[1:]
            if protocol in self.protocol_keys:
                key = self.protocol_keys[protocol]
                protocol_class = self._class_by_name(protocol)
                protocols[key] = [protocol_class]
                log.info(f"Register protocol {protocol}.")
                if datatypes:
                    datatype_classes = [ self._class_by_name(datatype) for datatype in datatypes ]
                    protocols[key].extend(datatype_classes)
                    log.info(f"Register datatypes {*datatypes, }.")
            else:
                log.info(f"Ignore undocumented protocol {protocol}.")
        log.debug(f"Registered protocols and data types: {protocols}")
        return protocols

    def _create_protocol(self, key, *args):
        protocol_datatypes = self.registered_protocols.get(key)
        if protocol_datatypes:
            log.info(f"Create protocol {key}...")
            protocol = protocol_datatypes[0]
            datatypes = protocol_datatypes[1:]
            if datatypes:
                return protocol(*args, datatypes=datatypes)
            else:
                return protocol(*args)
        else:
            log.info(f"Protocol {key} is not supported.")

    def get_unit_id(self):
        """Return the device’s unit ID.

        This feature is undocumented in the spec. The implementation is derived
        from capturing raw USB traffic from Garmin's proprietary MapSource
        application version 6.16.3
        (https://www8.garmin.com/support/download_details.jsp?id=209).

        """
        log.info("Request Product Id...")
        self.link.send_packet(self.link.pid_command_data,
                              self.command.cmnd_transfer_unit_id)
        log.info("Expect Product Id packet")
        packet = self.link.expect_packet(self.link.pid_unit_id)
        unit_id = int.from_bytes(packet['data'], byteorder='little')

        return unit_id

    def get_waypoints(self, callback=None):
        """Download waypoints.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of waypoint datatypes
        :rtype: list

        """
        return self.waypoint_transfer.get_data(callback)

    def put_waypoints(self, data, callback=None):
        """Upload waypoints.

        :param data: data
        :type data: list of waypoint datatypes
        :param callback: optional callback function
        :type callback: function or None
        :return: None

        """
        return self.waypoint_transfer.put_data(data, callback)

    def get_routes(self, callback=None):
        """Download routes.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of route datatypes
        :rtype: list

        """
        return self.route_transfer.get_data(callback)

    def put_routes(self, data, callback=None):
        """Upload routes.

        :param data: data
        :type data: list of route datatypes
        :param callback: optional callback function
        :type callback: function or None
        :return: None

        """
        return self.route_transfer.put_data(data, callback)

    def get_tracks(self, callback=None):
        """Download tracks.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of track datatypes
        :rtype: list

        """
        if self.track_log_transfer is None:
            raise GarminError("Protocol track_log_transfer_protocol is not supported")
        return self.track_log_transfer.get_data(callback)

    def put_tracks(self, data, callback=None):
        """Upload tracks.

        :param data: data
        :type data: list of track datatypes
        :param callback: optional callback function
        :type callback: function or None
        :return: None

        """
        if self.track_log_transfer is None:
            raise GarminError("Protocol track_log_transfer_protocol is not supported")
        return self.track_log_transfer.put_data(data, callback)

    def get_proximities(self, callback=None):
        """Download proximities.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of proximity datatypes
        :rtype: list

        """
        if self.proximity_waypoint_transfer is None:
            raise GarminError("Protocol proximity_waypoint_transfer_protocol is not supported")
        return self.proximity_waypoint_transfer.get_data(callback)

    def put_proximities(self, data, callback=None):
        """Upload proximities.

        :param data: data
        :type data: list of proximity datatypes
        :param callback: optional callback function
        :type callback: function or None
        :return: None

        """
        if self.proximity_waypoint_transfer is None:
            raise GarminError("Protocol proximity_waypoint_transfer_protocol is not supported")
        return self.proximity_waypoint_transfer.put_data(data, callback)

    def get_laps(self, callback=None):
        """Download laps.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of lap datatypes
        :rtype: list

        """
        if self.lap_transfer is None:
            raise GarminError("Protocol lap_transfer_protocol is not supported")
        return self.lap_transfer.get_data(callback)

    def get_runs(self, callback=None):
        """Download runs.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of run datatypes
        :rtype: list

        """
        if self.run_transfer is None:
            raise GarminError("Protocol run_transfer_protocol is not supported")
        return self.run_transfer.get_data(callback)

    def get_almanac(self, callback=None):
        return self.almanac_transfer.get_data(callback)

    def get_time(self, callback=None):
        return self.date_and_time_initialization.get_data(callback)

    def get_flightbook(self, callback=None):
        """Download flightbooks.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of flightbook datatypes
        :rtype: list

        """
        if self.flightbook_transfer is None:
            raise GarminError("Protocol flightbook_transfer_protocol is not supported")
        return self.flightbook_transfer.get_data(callback)

    def get_position(self, callback=None):
        return self.position_initialization.get_data(callback)

    def pvt_on(self):
        """Turn on PVT mode.

        In PVT mode the device will transmit packets approximately once per
        second

        """
        log.info(f"Start transmitting PVT data")
        return self.pvt.data_on()

    def pvt_off(self):
        """Turn off PVT mode."""
        log.info("Stop transmitting PVT data")
        return self.pvt.data_off()

    def get_pvt(self, callback=None):
        """Get real-time position, velocity, and time (PVT).

        :param callback: optional callback function
        :type callback: function or None
        :return: PVT datatype
        :rtype: garmin.PVT

        """
        return self.pvt.get_data(callback)

    def del_map(self):
        """Delete map."""
        if self.map_transfer is None:
            raise GarminError("Protocol map_transfer_protocol is not supported")
        return self.map_transfer._write_memory(None)

    def get_map(self, callback=None):
        """Download map.

        The map is received as raw data and is in Garmin IMG format.

        :param callback: optional callback function
        :type callback: function or None
        :raise GarminError: if the map_transfer_protocol is not supported.
        :return: map
        :rtype: bytes

        """
        if self.map_transfer is None:
            raise GarminError("Protocol map_transfer_protocol is not supported")
        return self.map_transfer.get_map(callback)

    def put_map(self, data, key=None, callback=None):
        """Upload map.

        The map is sent as raw data and should be in Garmin IMG format. Multiple
        IMG files should be merged into one file called ``"gmapsupp.img"``. To
        upload a locked map, the encryption key has to be specified.

        :param data: Garmin IMG
        :type data: str or io.BufferedReader or bytes
        :param key: optional encryption key
        :type key: str or None
        :param callback: optional callback function
        :type callback: function or None
        :raise GarminError: if the map_transfer_protocol is not supported.
        :return: None

        """
        if self.map_transfer is None:
            raise GarminError("Protocol map_transfer_protocol is not supported")
        if isinstance(data, str):
            map_size = os.path.getsize(data)
        elif isinstance(data, io.BufferedReader):
            map_size = os.stat(data.fileno()).st_size
        elif isinstance(data, bytes):
            map_size = len(data)
        mem_size = self.map_transfer.memory_properties.mem_size
        log.info(f"Map size: {map_size} bytes")
        if map_size > mem_size:
            raise GarminError("Insufficient memory to upload map")
        if key:
            self.map_unlock.send_unlock_key(key)
        # Maximize the baudrate if supported
        if isinstance(self.phys, SerialLink) and self.transmission:
            current_baudrate = self.transmission.get_baudrate()
            baudrates = self.transmission.get_supported_baudrates()
            self.transmission.set_baudrate(baudrates[0])
        # The maximum data size differs between the serial and USB protocol: 255
        # for serial (maximum value of 8-bit unsigned integer) and 4084 for USB
        # (maximum buffer size - header size = 4096 - 12). So, in theory a chunk
        # size of 251 (maximum data size - offset size = 255 - 4) would work.
        # However, the maximum chunk size apparently is 250 bytes, because
        # transfers with a larger chunk size don't work in practice. The old map
        # on the device is deleted, but the new map isn't shown on the device.
        # This is surprising, because when the map is transferred from the
        # device to the computer, the expected maximum data size of 255 is used.
        chunk_size = 250
        self.map_transfer._write_memory(data, chunk_size, callback)
        # Restore the baudrate to the original value
        if isinstance(self.phys, SerialLink) and self.transmission:
            self.transmission.set_baudrate(current_baudrate)

    def get_screenshot(self, callback=None):
        """Capture screenshot.

        The map is received as raw data and is in Garmin IMG format.

        :param callback: optional callback function
        :type callback: function or None
        :return: image file of the device's display
        :rtype: PIL.Image

        """
        return self.screenshot_transfer.get_image(callback)

    def get_image_types(self):
        """Get image types.

        Return a list of image types that are allowed to be retrieved or
        updated. Each image type is represented as a dict of the index and name
        of the image type.

        :return: supported image types
        :rtype: list[dict]

        """
        return self.image_transfer.get_image_types()

    def get_image_list(self):
        """Get image list.

        Return a list of images that are allowed to be retrieved or updated.
        Each image is represented as a dict of the image type index, image
        index, writable status, and image name. The image type name the image
        belongs to can be looked up with :func:`Garmin.get_image_types`.

        :return: supported images
        :rtype: list[dict]

        """
        return self.image_transfer.get_image_list()

    def get_image(self, idx, callback=None):
        """Download image.

        It is possible to get a screenshot from most GPS models. Certain newer
        models also allow you to get other image types, like the splash screen
        or waypoint symbols.

        The index of the image can be looked up with
        :func:`Garmin.get_image_list`.

        :param idx: index of image to download
        :type idx: int
        :param callback: optional callback function
        :type callback: function or None
        :return: image file of the device's display
        :rtype: PIL.Image

        """
        return self.image_transfer.get_image(idx, callback)

    def put_image(self, idx, data, callback=None):
        """Upload image.

        The index of the image can be looked up with
        :func:`Garmin.get_image_list`.

        :param idx: index of image to upload
        :type idx: int
        :param data: image data to upload
        :type data: PIL.Image
        :param callback: optional callback function
        :type callback: function or None

        """
        with PIL.Image.open(data) as image:
            self.image_transfer.put_image(idx, image, callback)

    def abort_transfer(self):
        """Abort transfer"""
        log.info("Abort transfer")
        self.command.abort_transfer()

    def turn_power_off(self):
        """Turn power off"""
        log.info("Turn power off")
        self.command.turn_power_off()
