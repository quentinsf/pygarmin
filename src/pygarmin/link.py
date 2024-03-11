from functools import cached_property
import serial
import usb
from . import error as mod_error
from . import logger as mod_logger

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
            raise mod_error.LinkError(e.strerror)

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
        mod_logger.log.debug("Unpack packet...")
        # Only the size, data, and checksum fields have to be unescaped, but
        # unescaping the whole packet doesn't hurt
        packet = self.unescape(buffer)
        id = packet[1]
        size = packet[2]
        data = packet[3:-3]
        checksum = packet[-3]
        if size != len(data):
            raise mod_error.LinkError("Invalid packet: wrong size of packet data")
        # 2's complement of the sum of all bytes from byte 1 to byte n-3
        if checksum != self.checksum(packet[1:-3]):
            raise mod_error.LinkError("Invalid packet: checksum failed")
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
        mod_logger.log.debug("Pack packet...")
        if 0 < pid < 256:
            pass
        else:
            raise mod_error.ProtocolError("Serial link doesn't support PIDs higher than 255. Try USB link instead.")
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
            raise mod_error.ProtocolError(f"Invalid data type: should be 'bytes' or 'int', but is {datatype}")
        size = len(data)
        mod_logger.log.debug(f"Packet data size: {size}")
        checksum = self.checksum(bytes([pid])
                                 + bytes([size])
                                 + data)
        mod_logger.log.debug(f"Packet data checksum: {checksum}")
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
                raise mod_error.LinkError(e.strerror)
            if not buffer:
                raise mod_error.LinkError("Reading packet timed out")
            elif len(buffer) != 2:
                raise mod_error.LinkError("Invalid packet: unexpected end")
            elif len(packet) == 0:
                # Packet header
                if buffer.startswith(dle):
                    packet += bytes([buffer.pop(0)])
                else:
                    raise mod_error.LinkError("Invalid packet: doesn't start with DLE character")
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
                    raise mod_error.LinkError("Invalid packet: doesn't end with DLE and ETX character")
            else:
                packet += bytes([buffer.pop(0)])
        return bytes(packet)

    def write(self, buffer):
        try:
            self.ser.write(buffer)
        except serial.SerialException as e:
            raise mod_error.LinkError(e.strerror)

    def read_packet(self, acknowledge=True):
        retries = 0
        while retries <= self.max_retries:
            try:
                buffer = self.read()
                mod_logger.log.debug(f"> {bytes.hex(buffer, sep=' ')}")
                packet = self.unpack(buffer)
                if acknowledge:
                    self.send_ack(packet['id'])
                break
            except mod_error.LinkError as e:
                mod_logger.log.info(e)
                self.send_nak()
                retries += 1
        if retries > self.max_retries:
            raise mod_error.LinkError("Maximum retries exceeded")
        return packet

    def send_packet(self, pid, data, acknowledge=True):
        """Send a packet."""
        buffer = self.pack(pid, data)
        mod_logger.log.debug(f"< {bytes.hex(buffer, sep=' ')}")
        retries = 0
        while retries <= self.max_retries:
            try:
                self.write(buffer)
                if acknowledge:
                    self.read_ack(pid)
                break
            except mod_error.LinkError as e:
                mod_logger.log.error(e)
                retries += 1
        if retries > self.max_retries:
            raise mod_error.LinkError("Maximum retries exceeded")

    def read_ack(self, pid):
        """Read a ACK/NAK packet.

        If an ACK packet is received the packet was received correctly and
        communication may continue. If a NAK packet is received, the data packet was not
        received correctly and should be sent again.

        """
        mod_logger.log.debug("Read ACK/NAK")
        packet = self.read_packet(acknowledge=False)
        expected_pid = pid
        received_pid = int.from_bytes(packet['data'], byteorder='little')

        if packet['id'] == self.pid_ack_byte:
            mod_logger.log.debug("Received ACK packet")
            if expected_pid != received_pid:
                raise mod_error.ProtocolError(f"Device expected {expected_pid}, got {received_pid}")
        elif packet['id'] == self.pid_nak_byte:
            mod_logger.log.debug("Received NAK packet")
            raise mod_error.LinkError("Packet was not received correctly")
        else:
            raise GarminError("Received neither ACK nor NAK packet")

    def send_ack(self, pid):
        """Send an ACK packet."""
        mod_logger.log.debug("Send ACK packet")
        data = pid.to_bytes(2, byteorder='little')
        self.send_packet(self.pid_ack_byte, data, acknowledge=False)

    def send_nak(self):
        """Send a NAK packet.

        NAKs are used only to indicate errors in the communications link, not
        errors in any higher-layer protocol.

        """
        mod_logger.log.debug("Send NAK packet")
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
        device = usb.core.find(idVendor=self.idVendor)
        if device is None:
            raise mod_error.LinkError("Garmin device not found")
        for cfg in device:
            for intf in cfg:
                if device.is_kernel_driver_active(intf.bInterfaceNumber):
                    try:
                        device.detach_kernel_driver(intf.bInterfaceNumber)
                    except usb.core.USBError as e:
                        raise mod_error.LinkError(f"Could not detach kernel driver from interface({intf.bInterfaceNumber}): {e}")
        return device

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
        ep = usb.util.find_descriptor(self.intf, bEndpointAddress=self.Interrupt_IN)
        return ep

    @cached_property
    def ep_out(self):
        """Return the Bulk OUT instance.

        This property will cause some USB traffic the first time it is accessed
        and cache the resulting value for future use.

        """

        ep = usb.util.find_descriptor(self.intf, bEndpointAddress=self.Bulk_OUT)
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
            raise mod_error.ProtocolError("Invalid packet: wrong size of packet data")
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
        mod_logger.log.debug("Pack packet")
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
            raise mod_error.ProtocolError(f"Invalid data type: should be 'bytes' or 'int', but is {datatype}")
        size = len(data)
        mod_logger.log.debug(f"Data size: {size}")
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
            raise mod_error.LinkError(e.strerror)
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
            raise mod_error.LinkError(e.strerror)

    def read_packet(self):
        """Read a packet."""
        retries = 0
        while retries <= self.max_retries:
            try:
                buffer = self.read()
                mod_logger.log.debug(f"> {bytes.hex(buffer, sep=' ')}")
                packet = self.unpack(buffer)
                break
            except mod_error.LinkError as e:
                mod_logger.log.info(e)
                retries += 1
        if retries > self.max_retries:
            raise mod_error.LinkError("Maximum retries exceeded")
        return packet

    def send_packet(self, pid, data):
        """Send a packet."""
        buffer = self.pack(self.Application_Layer, pid, data)
        mod_logger.log.debug(f"< {bytes.hex(buffer, sep=' ')}")
        retries = 0
        while retries <= self.max_retries:
            try:
                self.write(buffer)
                break
            except mod_error.LinkError as e:
                mod_logger.log.error(e)
                retries += 1
        if retries > self.max_retries:
            raise mod_error.LinkError("Maximum retries exceeded")

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
        mod_logger.log.info("Send Start Session packet")
        buffer = self.pack(self.USB_Protocol_Layer, self.pid_start_session)
        mod_logger.log.debug(f"< packet {self.pid_start_session}: {bytes.hex(b'')}")
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
        mod_logger.log.info("Read Session Started packet")
        while True:
            packet = self.read_packet()
            if packet['id'] == self.pid_session_started:
                mod_logger.log.info("Received Session Started packet")
                break

    def start_session(self):
        """Start USB session and return the unit ID.

        """
        mod_logger.log.info("Start USB session")
        self.send_start_session_packet()
        self.read_session_started_packet()
