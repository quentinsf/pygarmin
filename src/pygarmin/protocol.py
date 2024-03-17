from functools import cached_property
import math
from microbmp import MicroBMP
import os
import rawutil
from . import datatype as mod_datatype
from . import error as mod_error
from . import logger as mod_logger

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
                mod_logger.log.info(f"Got packet type {self.pid_ext_product_data}. Ignoring...")
                datatype = mod_datatype.ExtProductData()
                datatype.unpack(packet['data'])
                for property in datatype.properties:
                    mod_logger.log.debug(f"Extra Product Data: {property[0].decode('ascii')}")
            else:
                break
        return packet

    def expect_packet(self, pid):
        """Expect and read a particular packet type. Return data."""
        packet = self.read_packet()
        if packet['id'] != pid:
            raise mod_error.ProtocolError(f"Expected {pid:3}, got {packet['id']:3}")
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
    pid_satellite_data = 114
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
        mod_logger.log.info("Request product data...")
        self.link.send_packet(self.link.pid_product_rqst, None)
        mod_logger.log.info("Expect product data")
        packet = self.link.expect_packet(self.link.pid_product_data)
        datatype = mod_datatype.ProductData()
        datatype.unpack(packet['data'])
        mod_logger.log.info(f"Product ID: {datatype.product_id}")
        mod_logger.log.info(f"Software version: {datatype.software_version:.2f}")
        mod_logger.log.info(f"Product description: {datatype.product_description.decode('ascii')}")
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
        mod_logger.log.info("Read protocols using Protocol Capability Protocol")
        packet = self.link.expect_packet(self.link.pid_protocol_array)
        protocols = []
        mod_logger.log.info("Parse supported protocols and datatypes...")
        # The order of array elements is used to associate data types with
        # protocols. For example, a protocol that requires two data types <D0>
        # and <D1> is indicated by a tag-encoded protocol ID followed by two
        # tag-encoded data type IDs, where the first data type ID identifies
        # <D0> and the second data type ID identifies <D1>.
        datatype = mod_datatype.ProtocolArray()
        datatype.unpack(packet['data'])
        for protocol_data in datatype.get_protocol_data():
            # Format the record to a string consisting of the tag and 3-digit number
            protocol_datatype = str(protocol_data)
            tag = protocol_data.get_tag()
            # Create a list of lists with supported protocols and associated datatypes
            if tag == 'tag_phys_prot_id':
                # We ignore the physical protocol, because it is initialized
                # already
                mod_logger.log.info(f"Got physical protocol '{protocol_datatype}'. Ignoring...")
            elif tag == 'tag_tx_prot_id':
                # Append new list with protocol.
                mod_logger.log.info(f"Got transmission protocol '{protocol_datatype}'. Adding...")
                protocols.append([protocol_datatype])
            elif tag == 'tag_link_prot_id':
                # Append new list with protocol.
                mod_logger.log.info(f"Got link protocol '{protocol_datatype}'. Adding...")
                protocols.append([protocol_datatype])
            elif tag == 'tag_appl_prot_id':
                # Append new list with protocol.
                mod_logger.log.info(f"Got application protocol '{protocol_datatype}'. Adding...")
                protocols.append([protocol_datatype])
            elif tag == 'tag_data_type_id':
                # Append datatype to list of previous protocol
                mod_logger.log.info(f"Got datatype '{protocol_datatype}'. Adding...")
                protocols[-1].append(protocol_datatype)
            else:
                mod_logger.log.info(f"Got unknown protocol or datatype '{protocol_datatype}'. Ignoring...")
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

    def __init__(self, gps):
        self.gps = gps

    def abort_transfer(self):
        self.gps.link.send_packet(self.gps.link.pid_command_data,
                             self.cmnd_abort_transfer)

    def turn_power_off(self):
        self.gps.link.send_packet(self.gps.link.pid_command_data,
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

    def __init__(self, gps):
        self.gps = gps

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
        mod_logger.log.info("Get supported baudrates...")
        self.gps.link.send_packet(self.gps.link.pid_command_data,
                                  self.gps.command.cmnd_transfer_baud)
        packet = self.gps.link.expect_packet(self.gps.link.pid_baud_data)
        baudrates = []
        for baudrate, in rawutil.iter_unpack('<I', packet['data']):
            baudrate = self.desired_baudrate(baudrate)
            if baudrate:
                baudrates.append(baudrate)
        mod_logger.log.info(f"Supported baudrates: {*baudrates, }.")
        return baudrates

    def set_baudrate(self, baudrate):
        """Change the baudrate of the device."""
        mod_logger.log.info(f"Change baudrate to {baudrate}...")
        mod_logger.log.info("Turn off async mode")
        self.gps.link.send_packet(self.gps.link.pid_enable_async_events, b'\x00\x00')
        mod_logger.log.info("Request baudrate change")
        data = baudrate.to_bytes(4, byteorder='little')
        self.gps.link.send_packet(self.gps.link.pid_baud_rqst_data, data)
        # The device will respond by sending a packet with the highest
        # acceptable baudrate closest to what was requested
        packet = self.gps.link.expect_packet(self.gps.link.pid_baud_acpt_data)
        baudrate = int.from_bytes(packet['data'], byteorder='little')
        mod_logger.log.info(f"Accepted baudrate: {baudrate}")
        # Determine the desired baudrate value from accepted baudrate
        desired_baudrate = self.desired_baudrate(baudrate)
        if desired_baudrate:
            mod_logger.log.info(f"Desired baudrate: {desired_baudrate}")
            # Set the new baudrate
            mod_logger.log.info(f"Set the baudrate to {desired_baudrate}")
            self.gps.phys.set_baudrate(desired_baudrate)
            try:
                # Immediately after setting the baudrate, transmit an Ack ping packet
                self.gps.link.send_packet(self.gps.link.pid_command_data,
                                          self.gps.command.cmnd_ack_ping)
                # Transmit the same packet again
                self.gps.link.send_packet(self.gps.link.pid_command_data,
                                          self.gps.command.cmnd_ack_ping)
                # The baudrate has been successfully changed upon acknowledging the
                # above two ping packets. If the device does not receive these two
                # packets within two seconds, it will reset its baudrate to the default
                # 9600.
                mod_logger.log.info(f"Baudrate successfully changed to {desired_baudrate}")
            except:
                mod_logger.log.info("Failed to change baudrate")
        else:
            mod_logger.log.warning("Unsupported baudrate {baudrate}")

    def get_baudrate(self):
        return self.gps.phys.get_baudrate()


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

    def __init__(self, gps, datatypes):
        self.gps = gps
        self.datatypes = datatypes

    def get_data(self, cmd, *pids, callback=None):
        self.gps.link.send_packet(self.gps.link.pid_command_data, cmd)
        packet = self.gps.link.expect_packet(self.gps.link.pid_records)
        datatype = mod_datatype.Records()
        datatype.unpack(packet['data'])
        packet_count = datatype.records
        mod_logger.log.info(f"{type(self).__name__}: Expecting {packet_count} records")
        result = []
        for idx in range(packet_count):
            packet = self.gps.link.read_packet()
            pid = packet['id']
            data = packet['data']
            i = pids.index(pid)
            datatype = self.datatypes[i]()
            mod_logger.log.info(f"Datatype {type(datatype).__name__}")
            datatype.unpack(data)
            mod_logger.log.info(f"{str(datatype)}")
            if pid in pids:
                result.append(datatype)
            else:
                raise mod_error.ProtocolError(f"Expected one of {*pids,}, got {pid}")
            if callback:
                callback(datatype, idx+1, packet_count)
        self.gps.link.expect_packet(self.gps.link.pid_xfer_cmplt)
        return result

    def put_data(self, cmd, packets, callback=None):
        packet_count = len(packets)
        mod_logger.log.info(f"{type(self).__name__}: Sending {packet_count} records")
        self.gps.link.send_packet(self.gps.link.pid_records, packet_count)
        for idx, packet in enumerate(packets):
            pid = packet['id']
            datatype = packet['data']
            datatype.pack()
            mod_logger.log.info(f"{str(datatype)}")
            data = datatype.get_data()
            mod_logger.log.debug(f"> packet {pid:3}: {bytes.hex(data, sep=' ')}")
            self.gps.link.send_packet(pid, data)
            if callback:
                callback(datatype, idx+1, packet_count)
        self.gps.link.send_packet(self.gps.link.pid_xfer_cmplt, cmd)


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
                                         self.gps.command.cmnd_transfer_wpt,
                                         self.gps.link.pid_wpt_data,
                                         callback=callback)

    def put_data(self, waypoints, callback=None):
        packets = []
        mod_logger.log.info(f"Datatypes: {*[datatype.__name__ for datatype in self.datatypes],}")
        for waypoint in waypoints:
            pid = self.gps.link.pid_wpt_data
            if isinstance(waypoint, mod_datatype.Wpt):
                datatype = waypoint
            elif isinstance(waypoint, dict):
                datatype = self.datatypes[0](**waypoint)
            else:
                raise mod_error.ProtocolError("Invalid class type: expected dict or {self.datatypes[0].__name__}")
            packet = {'id': pid, 'data': datatype}
            packets.append(packet)
        return TransferProtocol.put_data(self,
                                         self.gps.command.cmnd_transfer_wpt,
                                         packets,
                                         callback=callback)


class A101(TransferProtocol):
    """Waypoint Category Transfer Protocol.

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
                                         self.gps.command.cmnd_transfer_wpt_cats,
                                         self.gps.link.pid_wpt_cat,
                                         callback=callback)

    def put_data(self, categories, callback=None):
        packets = []
        mod_logger.log.info(f"Datatypes: {*[datatype.__name__ for datatype in self.datatypes],}")
        for category in categories:
            pid = self.gps.link.pid_wpt_cat
            if isinstance(point, mod_datatype.WptCat):
                datatype = point
            elif isinstance(point, dict):
                datatype = self.datatypes[0](**point)
            else:
                raise mod_error.ProtocolError("Invalid class type: expected dict or {self.datatypes[0].__name__}")
            packet = {'id': pid, 'data': datatype}
            packets.append(packet)
        return TransferProtocol.put_data(self,
                                         self.gps.command.cmnd_transfer_wpt_cats,
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
                                         self.gps.command.cmnd_transfer_rte,
                                         self.gps.link.pid_rte_hdr,
                                         self.gps.link.pid_rte_wpt_data,
                                         callback=callback)

    def put_data(self, routes, callback=None):
        packets = []
        if all(isinstance(datatype, mod_datatype.DataType) for datatype in routes):
            for datatype in routes:
                if isinstance(datatype, mod_datatype.RteHdr):
                    pid = self.gps.link.pid_rte_hdr
                elif isinstance(datatype, mod_datatype.mod_datatype.Wpt):
                    pid = self.gps.link.pid_rte_wpt_data
                else:
                    raise mod_error.ProtocolError("Invalid datatype: expected {self.datatypes[0].__name__} or {self.datatypes[1].__name__}")
                packet = {'id': pid, 'data': datatype}
                packets.append(packet)
        elif all(isinstance(datatype, dict) for route in routes for datatype in route):
            for route in routes:
                header = route[0]
                points = route[1:]
                pid = self.gps.link.pid_rte_hdr
                datatype = self.datatypes[0](**header)
                packet = {'id': pid, 'data': datatype}
                packets.append(packet)
                for point in points:
                    pid = self.gps.link.pid_rte_wpt_data
                    datatype = self.datatypes[0](**point)
                    packet = {'id': pid, 'data': datatype}
                    packets.append(packet)
        return TransferProtocol.put_data(self,
                                         self.gps.command.cmnd_transfer_rte,
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
                                         self.gps.command.cmnd_transfer_rte,
                                         self.gps.link.pid_rte_hdr,
                                         self.gps.link.pid_rte_wpt_data,
                                         self.gps.link.pid_rte_link_data,
                                         callback=callback)

    def put_data(self, routes, callback=None):
        packets = []
        if all(isinstance(datatype, mod_datatype.DataType) for datatype in routes):
            for datatype in routes:
                if isinstance(datatype, mod_datatype.RteHdr):
                    pid = self.gps.link.pid_rte_hdr
                elif isinstance(datatype, mod_datatype.Wpt):
                    pid = self.gps.link.pid_rte_wpt_data
                elif isinstance(datatype, mod_datatype.RteLink):
                    pid = self.gps.link.pid_rte_link_data
                else:
                    raise mod_error.ProtocolError("Invalid datatype: expected {self.datatypes[0].__name__}, {self.datatypes[1].__name__}, or {self.datatypes[2].__name__}")
                packet = {'id': pid, 'data': datatype}
                packets.append(packet)
        elif all(isinstance(datatype, dict) for route in routes for datatype in route):
            for route in routes:
                header = route[0]
                points = route[1:]
                pid = self.gps.link.pid_rte_hdr
                datatype = self.datatypes[0](**header)
                packet = {'id': pid, 'data': datatype}
                packets.append(packet)
                is_even = lambda x: x % 2 == 0
                for idx, point in enumerate(points):
                    if is_even(idx):
                        pid = self.gps.link.pid_rte_wpt_data
                        datatype = self.datatypes[1](**point)
                    else:
                        pid = self.gps.link.pid_rte_link_data
                        datatype = self.datatypes[2](**point)
                    packet = {'id': pid, 'data': datatype}
                    packets.append(packet)
        else:
            raise mod_error.ProtocolError("Invalid class types: expected dict or datatypes {*[datatype.__name__ for datatype in self.datatypes],}")
        return TransferProtocol.put_data(self,
                                         self.gps.command.cmnd_transfer_rte,
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
                                         self.gps.command.cmnd_transfer_trk,
                                         self.gps.link.pid_trk_data,
                                         callback=callback)

    def put_data(self, points, callback=None):
        packets = []
        for point in points:
            pid = self.gps.link.pid_trk_data
            if isinstance(point, mod_datatype.TrkPoint):
                datatype = point
            elif isinstance(point, dict):
                datatype = self.datatypes[0](**point)
            else:
                raise mod_error.ProtocolError("Invalid class type: expected dict or {self.datatypes[0].__name__}")
            packet = (pid, datatype)
            packets.append(packet)
        return TransferProtocol.put_data(self,
                                         self.gps.command.cmnd_transfer_trk,
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
                                         self.gps.command.cmnd_transfer_trk,
                                         self.gps.link.pid_trk_hdr,
                                         self.gps.link.pid_trk_data,
                                         callback=callback)

    def put_data(self, tracks, callback=None):
        packets = []
        for track in tracks:
            header = track[0]
            points = track[1:]
            pid = self.gps.link.pid_trk_hdr
            if isinstance(header, mod_datatype.TrkHdr):
                datatype = header
            elif isinstance(header, dict):
                datatype = self.datatypes[0](**header)
            else:
                raise mod_error.ProtocolError("Invalid class type: expected dict or {self.datatypes[0].__name__}")
            packet = (pid, datatype)
            packets.append(packet)
            for point in points:
                pid = self.gps.link.pid_trk_data
                if isinstance(point, mod_datatype.TrkPoint):
                    datatype = point
                elif isinstance(point, dict):
                    datatype = self.datatypes[1](**point)
                else:
                    raise mod_error.ProtocolError("Invalid class type: expected dict or {self.datatypes[1].__name__}")
                packet = (pid, datatype)
                packets.append(packet)
        return TransferProtocol.put_data(self,
                                         self.gps.command.cmnd_transfer_trk,
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
                                         self.gps.command.cmnd_transfer_prx,
                                         self.gps.link.pid_prx_wpt_data,
                                         callback=callback)

    def put_data(self, waypoints, callback=None):
        packets = []
        for waypoint in waypoints:
            pid = self.gps.link.pid_prx_wpt_data
            if isinstance(waypoint, mod_datatype.PrxWpt):
                datatype = waypoint
            elif isinstance(waypoint, dict):
                datatype = self.datatypes[0](**waypoint)
            else:
                raise mod_error.ProtocolError("Invalid class type: expected dict or {self.datatypes[0].__name__}")
            packet = {'id': pid, 'data': datatype}
            packets.append(packet)
        return TransferProtocol.put_data(self,
                                         self.gps.command.cmnd_transfer_prx,
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
                                         self.gps.command.cmnd_transfer_alm,
                                         self.gps.link.pid_almanac_data,
                                         callback=callback)

    def put_data(self, almanac_data, callback=None):
        packets = []
        for satellite in almanac_data:
            pid = self.gps.link.pid_almanac_data
            if isinstance(satellite, Almanac):
                datatype = satellite
            elif isinstance(satellite, dict):
                datatype = self.datatypes[0](**satellite)
            else:
                raise mod_error.ProtocolError("Invalid class type: expected dict or {self.datatypes[0].__name__}")
            packet = (pid, datatype)
            packets.append(packet)
        return TransferProtocol.put_data(self,
                                         self.gps.command.cmnd_transfer_alm,
                                         packets,
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
        self.gps.link.send_packet(self.gps.link.pid_command_data,
                                  self.gps.command.cmnd_transfer_time)
        packet = self.gps.link.expect_packet(self.gps.link.pid_date_time_data)
        datatype = self.datatypes[0]()
        datatype.unpack(packet['data'])
        if callback:
            callback(datatype, 1, 1)
        return datatype

    def put_data(self, date_time, callback=None):
        pid = self.gps.link.pid_almanac_data
        if isinstance(date_time, Almanac):
            datatype = date_time
        elif isinstance(date_time, dict):
            datatype = self.datatypes[0](**date_time)
        else:
            raise mod_error.ProtocolError("Invalid class type: expected dict or {self.datatypes[0].__name__}")
        packet = (pid, datatype)
        return TransferProtocol.put_data(self,
                                         self.gps.command.cmnd_transfer_time,
                                         packets,
                                         callback=callback)


class A601(TransferProtocol):
    """Undocumented application protocol."""


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
                                         self.gps.command.cmnd_flightbook_transfer,
                                         self.gps.link.pid_flightbook_record,
                                         callback=callback)

    def put_data(self, records, callback=None):
        packets = []
        for record in records:
            pid = self.gps.link.pid_record
            if isinstance(record, Almanac):
                datatype = record
            elif isinstance(record, dict):
                datatype = self.datatypes[0](**record)
            else:
                raise mod_error.ProtocolError("Invalid class type: expected dict or {self.datatypes[0].__name__}")
            packet = (pid, datatype)
            packets.append(packet)
        return TransferProtocol.put_data(self,
                                         self.gps.command.cmnd_flightbook_transfer,
                                         packets,
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
        self.gps.link.send_packet(self.gps.link.pid_command_data,
                                  self.gps.command.cmnd_transfer_posn)
        packet = self.gps.link.expect_packet(self.gps.link.pid_position_data)
        datatype = self.datatypes[0]()
        datatype.unpack(packet['data'])
        if callback:
            callback(datatype, 1, 1)
        return datatype

    def put_data(self, position, callback=None):
        pid = self.gps.link.pid_position_data
        if isinstance(position, Almanac):
            datatype = position
        elif isinstance(position, dict):
            datatype = self.datatypes[0](**position)
        else:
            raise mod_error.ProtocolError("Invalid class type: expected dict or {self.datatypes[0].__name__}")
        packet = (pid, datatype)
        return TransferProtocol.put_data(self,
                                         self.gps.command.cmnd_transfer_posn,
                                         packets,
                                         callback=callback)


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

    The Garmin Forerunner 305 only reports the D800 datatype, but in practice
    transmits the D800 and an undocumented Satellite datatype alternately.

    """

    def data_on(self):
        self.gps.link.send_packet(self.gps.link.pid_command_data,
                                  self.gps.command.cmnd_start_pvt_data)

    def data_off(self):
        self.gps.link.send_packet(self.gps.link.pid_command_data,
                                  self.gps.command.cmnd_stop_pvt_data)

    def get_data(self, callback=None):
        pids = [self.gps.link.pid_pvt_data,
                self.gps.link.pid_satellite_data]
        self.datatypes.append(mod_datatype.Satellite)
        packet = self.gps.link.read_packet()
        pid = packet['id']
        if pid in pids:
            i = pids.index(pid)
            datatype = self.datatypes[i]()
            mod_logger.log.info(f"Datatype {type(datatype).__name__}")
            datatype.unpack(packet['data'])
            mod_logger.log.info(f"{str(datatype)}")
            if callback:
                callback(datatype, 1, 1)
            return datatype
        else:
            raise mod_error.ProtocolError(f"Expected one of {*pids,}, got {pid}")


class A801:
    """Undocumented application protocol."""


class A802:
    """Undocumented application protocol."""


class A900:
    """Map transfer protocol.

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

    def __init__(self, gps):
        self.gps = gps

    @cached_property
    def memory_properties(self):
        return self.get_memory_properties()

    def get_memory_properties(self):
        mod_logger.log.info("Request capacity data...")
        self.gps.link.send_packet(self.gps.link.pid_command_data,
                                  self.gps.command.cmnd_transfer_mem)
        mod_logger.log.info("Expect capacity data")
        packet = self.gps.link.expect_packet(self.gps.link.pid_capacity_data)
        datatype = mod_datatype.MemProperties()
        datatype.unpack(packet['data'])
        mem_size = datatype.mem_size
        mod_logger.log.info(f"Memory size: {mem_size} bytes")
        return datatype

    def _read_memory(self, filename='', callback=None):
        mod_logger.log.info("Get memory data...")
        mem_region = self.memory_properties.mem_region
        datatype = mod_datatype.MemFile(mem_region=mem_region, subfile=filename)
        datatype.pack()
        data = datatype.get_data()
        self.gps.link.send_packet(self.gps.link.pid_mem_read, data)
        packet = self.gps.link.read_packet()
        pid = packet['id']
        if pid == self.gps.link.pid_mem_data:
            datatype = mod_datatype.MemData()
            datatype.unpack(packet['data'])
            if int.from_bytes(datatype.data, byteorder='little') == 0:
                mod_logger.log.info("Data not found")
            else:
                mod_logger.log.info(f"Got unknown data {datatype.data}. Ignoring...")
        elif pid == self.gps.link.pid_mem_records:
            # The Records contains a 32-bit integer that indicates the number
            # of data packets to follow.
            datatype = mod_datatype.Records()
            datatype.unpack(packet['data'])
            packet_count = datatype.records
            mod_logger.log.info(f"{type(self).__name__}: Expecting {packet_count} records")
            data = bytes()
            for idx in range(packet_count):
                packet = self.gps.link.expect_packet(self.gps.link.pid_mem_chunk)
                datatype = mod_datatype.MemRecord()
                datatype.unpack(packet['data'])
                data += datatype.chunk
                if callback:
                    callback(datatype, idx+1, packet_count)
            return data

    def _write_file(self, file, chunk_size=250, callback=None):
        mod_logger.log.info(f"Upload map {file}")
        file_size = os.path.getsize(file)
        with open(file, 'rb') as f:
            while True:
                offset = f.tell()
                chunk = f.read(chunk_size)
                if not chunk:  # EOF reached
                    break
                datatype = mod_datatype.MemChunk(offset, chunk)
                datatype.pack()
                data = datatype.get_data()
                mod_logger.log.debug(f"Upload {offset+len(chunk)}/{file_size} bytes")
                self.gps.link.send_packet(self.gps.link.pid_mem_write, data)
                if callback:
                    callback(datatype, offset+len(chunk), file_size)

    def _write_handle(self, handle, chunk_size=250, callback=None):
        mod_logger.log.info(f"Upload map {handle.name}")
        handle.seek(0, os.SEEK_END)
        file_size = handle.tell()
        handle.seek(0, os.SEEK_SET)
        while True:
            offset = handle.tell()
            chunk = handle.read(chunk_size)
            if not chunk:  # EOF reached
                break
            datatype = mod_datatype.MemChunk(offset, chunk)
            datatype.pack()
            data = datatype.get_data()
            mod_logger.log.debug(f"Upload {offset+len(chunk)}/{file_size} bytes")
            self.gps.link.send_packet(self.gps.link.pid_mem_write, data)
            if callback:
                callback(datatype, offset+len(chunk), file_size)

    def _write_bytes(self, bytes, chunk_size=250, callback=None):
        mod_logger.log.info(f"Upload map")
        file_size = len(bytes)
        offsets = range(0, file_size, chunk_size)
        for offset in offsets:
            chunk = bytes[offset:offset+chunk_size]
            datatype = mod_datatype.MemChunk(offset, chunk)
            datatype.pack()
            data = datatype.get_data()
            mod_logger.log.debug(f"Upload {offset+len(chunk)}/{file_size} bytes")
            self.gps.link.send_packet(self.gps.link.pid_mem_write, data)
            if callback:
                callback(datatype, offset+len(chunk), file_size)

    def _write_memory(self, data, chunk_size=250, callback=None):
        mem_region = self.memory_properties.mem_region
        mod_logger.log.info("Turn off async mode")
        self.gps.link.send_packet(self.gps.link.pid_enable_async_events, b'\x00\x00')
        mod_logger.log.info("Enable write")
        self.gps.link.send_packet(self.gps.link.pid_mem_wren, mem_region)
        self.gps.link.expect_packet(self.gps.link.pid_mem_wel)
        mod_logger.log.info("Write enabled")
        if data is None:
            mod_logger.log.info("Delete map...")
            pass
        elif isinstance(data, str):
            self._write_file(data, chunk_size, callback)
        elif isinstance(data, io.BufferedReader):
            self._write_handle(data, chunk_size, callback)
        elif isinstance(data, bytes):
            self._write_bytes(data, chunk_size, callback)
        mod_logger.log.info("Disable write")
        self.gps.link.send_packet(self.gps.link.pid_mem_wrdi, mem_region)

    def get_map_properties(self):
        mod_logger.log.info("Get map properties...")
        filenames = ("MAKEGMAP.MPS", "MAPSOURC.MPS", "BLUCHART.MPS")
        for filename in filenames:
            data = self._read_memory(filename=filename)
            if data is not None:
                datatype = mod_datatype.MPSFile()
                datatype.unpack(data)
                records = datatype.get_records()
                result = [ record.get_content() for record in records ]
                return result

    def get_map(self, callback=None):
        mod_logger.log.info("Download map...")
        data = self._read_memory(filename='', callback=callback)
        if data is not None:
            return data


class A902:
    """Map unlock protocol.

    This protocol is undocumented, but it appears to be a map unlock protocol.
    The implementation is derived from the GarminDev drivers of the abandoned
    QLandkarteGT application (https://sourceforge.net/projects/qlandkartegt/)
    and the also abandoned sendmap application included with the cGPSmapper
    application (https://sourceforge.net/projects/cgpsmapper/).

    """

    def __init__(self, gps):
        self.gps = gps

    def send_unlock_key(self, key):
        data = bytes(key)
        mod_logger.log.info("Send unlock key")
        self.gps.link.send_packet(self.gps.link.pid_tx_unlock_key, data)
        mod_logger.log.info("Acknowledge unlock key")
        self.gps.link.expect_packet(self.gps.link.pid_ack_unlock_key)
        # TODO: read data


class A903:
    """Undocumented application protocol."""


class A904:
    """Undocumented application protocol

    This protocol is undocumented, but it appears to be a routable protocol. No
    implementation as of yet.

    """


class A905(TransferProtocol):
    """Undocumented application protocol

    This protocol is undocumented, but it is called an unlock code communication
    protocol in the changelogs of the Garmin eTrex Legend Cx/Vista Cx/Venture
    Cx/Venture HC, and the Garmin GPSMAP 60Cx/60CSx/76Cx/76CSx. No
    implementation as of yet.

    """


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
                                         self.gps.command.cmnd_transfer_laps,
                                         self.gps.link.pid_lap,
                                         callback=callback)


class A907(TransferProtocol):
    """Undocumented application protocol."""


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
        runs = TransferProtocol.get_data(self,
                                         self.gps.command.cmnd_transfer_runs,
                                         self.gps.link.pid_run,
                                         callback=callback)
        laps = self.gps.lap_transfer.get_data(callback)
        tracks = self.gps.track_log_transfer.get_data(callback)
        return runs + laps + tracks


class A1002(TransferProtocol):
    """Workout Transfer Protocol.

    Packet sequence:

    ===== ==================== ======================== ==================
       N   Direction            Packet ID                Packet Data Type
    ===== ==================== ======================== ==================
       0   Device1 to Device2   pid_command_data         Command
       1   Device2 to Device1   pid_records              Records
       2   Device2 to Device1   pid_workout              <D0>
     …     …                    …                        …
     m-2   Device2 to Device1   pid_workout              <D0>
     m-1   Device2 to Device1   pid_xfer_cmplt           Command
       m   Device1 to Device2   pid_command_data         Command
     m+1   Device2 to Device1   pid_records              Records
     m+2   Device2 to Device1   pid_workout_occurrence   Workout
     …     …                    …                        …
     n-2   Device2 to Device1   pid_workout_occurrence   Workout
     n-1   Device2 to Device1   pid_xfer_cmplt           Command
    ===== ==================== ======================== ==================

    """
    def get_data(self, callback=None):
        workouts = TransferProtocol.get_data(self,
                                             self.gps.command.cmnd_transfer_workouts,
                                             self.gps.link.pid_workout,
                                             callback=callback)
        workout_occurrences = self.gps.workout_occurrence_transfer.get_data(callback)
        return workouts + workout_occurrences


class A1003(TransferProtocol):
    """Workout Occurrence Transfer Protocol."""

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.gps.command.cmnd_transfer_workout_occurrences,
                                         self.gps.link.pid_workout_occurrence,
                                         callback=callback)


class A1004(TransferProtocol):
    """Fitness User Profile Transfer Protocol.

    Packet sequence:

    === ==================== ========================== ==================
     N   Direction            Packet ID                  Packet Data Type
    === ==================== ========================== ==================
     0   Device1 to Device2   pid_command_data           Command
     1   Device2 to Device1   pid_fitness_user_profile   <D0>
    === ==================== ========================== ==================

    """

    def get_data(self, callback=None):
        self.gps.link.send_packet(self.gps.link.pid_command_data,
                                  self.gps.command.cmnd_transfer_fitness_user_profile)
        packet = self.gps.link.expect_packet(self.gps.link.pid_fitness_user_profile)
        datatype = self.datatypes[0]()
        datatype.unpack(packet['data'])
        if callback:
            callback(datatype, 1, 1)
        return datatype


class A1005(TransferProtocol):
    """Workout Limits Transfer Protocol.

    === ================ ==================== ==================
     N   Direction        Packet ID            Packet Data Type
    === ================ ==================== ==================
     0   Host to Device   pid_command_data     Command
     1   Device to Host   pid_workout_limits   <D0>
    === ================ ==================== ==================

    """

    def get_data(self, callback=None):
        self.gps.link.send_packet(self.gps.link.pid_command_data,
                                  self.gps.command.cmnd_transfer_workout_limits)
        packet = self.gps.link.expect_packet(self.gps.link.pid_workout_limits)
        datatype = self.datatypes[0]()
        datatype.unpack(packet['data'])
        if callback:
            callback(datatype, 1, 1)
        return datatype


class A1006(TransferProtocol):
    """Course Transfer Protocol.

    Packet sequence:

    ===== ==================== ===================== ==================
       N    Direction            Packet ID             Packet Data Type
    ===== ==================== ===================== ==================
       0    Device1 to Device2   pid_command_data      Command
       1    Device2 to Device1   pid_records           Records
       2    Device2 to Device1   pid_course            <D0>
       …    …                    …                     …
     j-2    Device2 to Device1   pid_course            <D0>
     j-1    Device2 to Device1   pid_xfer_cmplt        Command
       j    Device1 to Device2   pid_command_data      Command
     j+1    Device2 to Device1   pid_records           Records
     j+2    Device2 to Device1   pid_course_lap        CourseLap
       …    …                    …                     …
     k-2    Device2 to Device1   pid_course_lap        CourseLap
     k-1    Device2 to Device1   pid_xfer_cmplt        Command
       k    Device1 to Device2   pid_command_data      Command
     k+1    Device2 to Device1   pid_records           Records
     k+2    Device2 to Device1   pid_course_trk_hdr    Course_TrkHdr
     k+3    Device2 to Device1   pid_course_trk_data   Course_TrkPoint
       …    …                    …                     …
     m-2    Device2 to Device1   pid_course_trk_data   Course_TrkPoint
     m-1    Device2 to Device1   pid_xfer_cmplt        Command
       m    Device1 to Device2   pid_command_data      Command
     m+1    Device2 to Device1   pid_records           Records
     m+2    Device2 to Device1   pid_course_point      CoursePoint
       …    …                    …                     …
     n-2    Device2 to Device1   pid_course_point      CoursePoint
     n-1    Device2 to Device1   pid_xfer_cmplt        Command
    ===== ==================== ===================== ==================

    """

    def get_data(self, callback=None):
        courses = TransferProtocol.get_data(self,
                                            self.gps.command.cmnd_transfer_courses,
                                            self.gps.link.pid_course,
                                            callback=callback)
        course_laps = self.gps.course_lap_transfer.get_data(callback)
        # If the A1012 Course Track Transfer Protocol is supported, then the associated
        # datatypes are used. Otherwise the datatypes used by the A302 Track Log
        # Transfer Protocol are used.
        if self.gps.registered_protocols.get('course_track_transfer_protocol') is not None:
            course_tracks = self.gps.course_track_transfer.get_data(callback)
        else:
            datatypes = self.gps.registered_protocols['track_log_transfer_protocol'][1:]
            protocol = TransferProtocol(self.gps, datatypes)
            course_tracks = protocol.get_data(self.gps.command.cmnd_transfer_course_tracks,
                                              self.gps.link.pid_course_trk_hdr,
                                              self.gps.link.pid_course_trk_data,
                                              callback=callback)
        course_points = self.gps.course_point_transfer.get_data(callback)
        return courses + course_laps + course_tracks + course_points


class A1007(TransferProtocol):
    """Course Lap Transfer Protocol."""

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.gps.command.cmnd_transfer_course_laps,
                                         self.gps.link.pid_course_lap,
                                         callback=callback)


class A1008(TransferProtocol):
    """Course Point Transfer Protocol."""

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.gps.command.cmnd_transfer_course_points,
                                         self.gps.link.pid_course_point,
                                         callback=callback)


class A1009(TransferProtocol):
    """Course Limits Transfer Protocol.

    Packet sequence:

    === ================ =================== ==================
     N   Direction        Packet ID           Packet Data Type
    === ================ =================== ==================
     0   Host to Device   pid_command_data    Command
     1   Device to Host   pid_course_limits   <D0>
    === ================ =================== ==================

    """

    def get_data(self, callback=None):
        self.gps.link.send_packet(self.gps.link.pid_command_data,
                                  self.gps.command.cmnd_transfer_course_limits)
        packet = self.gps.link.expect_packet(self.gps.link.pid_course_limits)
        datatype = self.datatypes[0]()
        datatype.unpack(packet['data'])
        if callback:
            callback(datatype, 1, 1)
        return datatype


class A1012(TransferProtocol):
    """Course Track Transfer Protocol."""

    def get_data(self, callback=None):
        return TransferProtocol.get_data(self,
                                         self.gps.command.cmnd_transfer_course_tracks,
                                         self.gps.link.pid_course_trk_hdr,
                                         self.gps.link.pid_course_trk_data,
                                         callback=callback)


class A1013(TransferProtocol):
    """Undocumented application protocol."""


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

    def __init__(self, gps):
        self.gps = gps

    def get_image_types(self):
        mod_logger.log.info("Request image types")
        self.gps.link.send_packet(self.gps.link.pid_image_type_idx_rx, None)
        packet = self.gps.link.expect_packet(self.gps.link.pid_image_type_idx_tx)
        indices = list(packet['data'])
        mod_logger.log.info("Request image type names")
        image_types = list()
        for idx in indices:
            self.gps.link.send_packet(self.gps.link.pid_image_type_name_rx, idx)
            packet = self.gps.link.expect_packet(self.gps.link.pid_image_type_name_tx)
            datatype = mod_datatype.ImageName()
            datatype.unpack(packet['data'])
            name = datatype.name.decode('ascii')
            mod_logger.log.info(f"Image type name: {name}")
            image_types.append({'idx': idx, 'name': name})
        return image_types

    def get_image_list(self):
        mod_logger.log.info("Request image list")
        self.gps.link.send_packet(self.gps.link.pid_image_list_rx, None)
        packet = self.gps.link.expect_packet(self.gps.link.pid_image_list_tx)
        datatype = mod_datatype.ImageList()
        datatype.unpack(packet['data'])
        images = list()
        for image in datatype.get_images():
            idx = image.idx
            image_dict = image.get_dict()
            mod_logger.log.info("Request image name")
            self.gps.link.send_packet(self.gps.link.pid_image_name_rx, idx)
            packet = self.gps.link.expect_packet(self.gps.link.pid_image_name_tx)
            datatype = mod_datatype.ImageName()
            datatype.unpack(packet['data'])
            name = datatype.name.decode('ascii')
            mod_logger.log.info(f"Image name: {name}")
            image_dict['name'] = name
            images.append(image_dict)
        return images

    def get_image_properties(self, idx=None):
        mod_logger.log.info("Request image properties")
        self.gps.link.send_packet(self.gps.link.pid_image_props_rx, idx)
        packet = self.gps.link.expect_packet(self.gps.link.pid_image_props_tx)
        if not packet['data']:
            raise ValueError(f"Invalid symbol index {idx}")
        datatype = mod_datatype.ImageInformationHeader()
        datatype.unpack(packet['data'])
        color = datatype.get_color()
        mod_logger.log.info(f"Dimensions: {datatype.width}x{datatype.height} pixels")
        mod_logger.log.info(f"Color depth: {datatype.bpp} bits per pixel")
        mod_logger.log.info(f"Transparency color: {(color.red, color.green, color.blue) if color else None}")
        return datatype

    def get_image_id(self, idx=None):
        mod_logger.log.info("Request image ID")
        self.gps.link.send_packet(self.gps.link.pid_image_id_rx, idx)
        packet = self.gps.link.expect_packet(self.gps.link.pid_image_id_tx)
        datatype = mod_datatype.ImageId()
        datatype.unpack(packet['data'])
        mod_logger.log.info(f"Image ID: {datatype.id}")
        return datatype

    def get_color_table(self, image_id):
        mod_logger.log.info(f"Request color table for image ID {image_id.id}")
        self.gps.link.send_packet(self.gps.link.pid_color_table_rx, image_id.get_data())
        packet = self.gps.link.expect_packet(self.gps.link.pid_color_table_tx)
        datatype = mod_datatype.ImageColorTable()
        datatype.unpack(packet['data'])
        colors = [(color.red, color.green, color.blue) for color in datatype.get_colors()]
        mod_logger.log.info(f"Color table: {*colors,}")
        return datatype

    def put_color_table(self, color_table):
        # The color table is sent in one packet, consisting of 4 bytes for the
        # id, and 4 bytes per color.
        mod_logger.log.info(f"Send color table for image ID {color_table.id}")
        self.gps.link.send_packet(self.gps.link.pid_color_table_tx, color_table.get_data())
        packet = self.gps.link.expect_packet(self.gps.link.pid_color_table_rx)
        datatype = mod_datatype.ImageId()
        datatype.unpack(packet['data'])
        if datatype.id != color_table.id:
            raise mod_error.ProtocolError(f"Expected {color_table.id}, got {datatype.id}")

    def get_image(self, idx, callback=None):
        mod_logger.log.info(f"Request image {idx}...")
        props = self.get_image_properties(idx)
        bpp = props.bpp
        height = props.height
        width = props.width
        bytewidth = props.bytewidth
        bytesize = props.get_bytesize()
        colors_used = props.get_colors_used()
        row_size = props.get_row_size()
        bmp = MicroBMP(width, height, bpp)
        image_id = self.get_image_id(idx)
        if colors_used is None:
            raise mod_error.GarminError(f"Unsupported color depth {bpp} bpp")
        elif colors_used == 0:
            mod_logger.log.info(f"{bpp}-bit color depth has no color table")
        else:
            color_table = self.get_color_table(image_id)
            # The color table can contain more colors than the number of colors
            # used
            bmp.palette = color_table.get_palette()[:colors_used]
        # The pixel array is sent in chunks, with a packet data size of maximum
        # 500 bytes, consisting of 4 bytes for the id and maximum 496 bytes for
        # the chunk of pixel array.
        max_chunk_size = 496
        chunk_count = math.ceil(bytesize / max_chunk_size)
        mod_logger.log.info(f"Image: Expecting {chunk_count} chunks")
        pixel_array = bytearray()
        for idx in range(chunk_count):
            self.gps.link.send_packet(self.gps.link.pid_image_data_rx, image_id.get_data())
            packet = self.gps.link.expect_packet(self.gps.link.pid_image_data_tx)
            datatype = mod_datatype.ImageChunk()
            datatype.unpack(packet['data'])
            pixel_array.extend(datatype.chunk)
            if callback:
                callback(datatype, idx+1, chunk_count)
        self.gps.link.send_packet(self.gps.link.pid_image_data_cmplt, image_id.get_data())
        mod_logger.log.info(f"Completed request pixel array for image ID {image_id.id}")
        # The pixels are stored "bottom-up", starting in the lower left corner,
        # going from left to right, and then row by row from the bottom to the
        # top of the image. The bits are packed in rows (also known as strides
        # or scan lines). The size of each row is rounded up to a multiple of 4
        # bytes (a 32-bit DWORD) by padding. For images with a height above 1,
        # multiple padded rows are stored consecutively, forming a pixel array.
        # Rearrange the pixel array from bottom-up to top-down and remove padding
        bmp.parray = bytearray()
        for pos in range(0, len(pixel_array), bytewidth):
            row = pixel_array[::-1][pos:pos+row_size]
            bmp.parray.extend(row)
        return bmp

    def put_image(self, idx, bmp, callback=None):
        props = self.get_image_properties(idx)
        bpp = props.bpp
        height = props.height
        width = props.width
        bytewidth = props.bytewidth
        bytesize = props.get_bytesize()
        colors_used = props.get_colors_used()
        row_size = props.get_row_size()
        if bpp != bmp.DIB_depth:
            raise mod_error.GarminError(f"Image has wrong color depth: expected {bpp} bpp, got {bmp.DIB_depth} bpp")
        if width != bmp.DIB_w or height != bmp.DIB_h:
            raise mod_error.GarminError(f"Image has wrong dimensions: expected {width}x{height} pixels, got {bmp.DIB_w}x{bmp.DIB_h} pixels")
        image_id = self.get_image_id(idx)
        if colors_used is None:
            raise mod_error.ProtocolError(f"Unsupported color depth {bpp} bpp")
        elif colors_used == 0:
            mod_logger.log.info(f"{bpp}-bit color depth has no color table")
        else:
            color_table = self.get_color_table(image_id)
            # The color table can contain more colors than the number of colors
            # used
            palette = color_table.get_palette()[:colors_used]
            if bmp.palette != palette:
                raise mod_error.GarminError("Image has the wrong color palette")
            self.put_color_table(color_table)
        pixel_array = bytes(bmp.parray)
        mod_logger.log.info(f"Send pixel array for image ID {image_id.id}")
        # The pixel array is sent in chunks, with a packet data size of maximum
        # 500 bytes, consisting of 4 bytes for the id and maximum 496 bytes for
        # the chunk of pixel array. After every chunk a packet with only the 4
        # byte ID is received.
        max_chunk_size = 496
        chunk_count = math.ceil(bytesize / max_chunk_size)
        mod_logger.log.info(f"Image: Sending {chunk_count} chunks")
        padding = bytes(bytewidth - row_size)
        for idx, pos in enumerate(range(0, len(pixel_array), row_size)):
            chunk = pixel_array[::-1][pos:pos+row_size]
            chunk += bytes(padding)
            datatype = mod_datatype.ImageChunk(image_id.id, chunk)
            datatype.pack()
            self.gps.link.send_packet(self.gps.link.pid_image_data_tx, datatype.get_data())
            if callback:
                callback(datatype, idx+1, chunk_count)
            packet = self.gps.link.expect_packet(self.gps.link.pid_image_data_rx)
            datatype = mod_datatype.ImageId()
            datatype.unpack(packet['data'])
            if datatype.id != image_id.id:
                raise mod_error.ProtocolError(f"Expected {image_id.id}, got {datatype.id}")
        self.gps.link.send_packet(self.gps.link.pid_image_data_cmplt, image_id.get_data())
        mod_logger.log.info(f"Completed send pixel array for image ID {image_id.id}")


class ScreenshotTransfer:

    def __init__(self, gps):
        self.gps = gps

    def get_image(self, callback=None):
        mod_logger.log.info("Request screenshot...")
        self.gps.link.send_packet(self.gps.link.pid_command_data, self.gps.command.cmnd_transfer_screen)
        mod_logger.log.info("Expect screen data")
        packet = self.gps.link.expect_packet(self.gps.link.pid_screen_data)
        datatype = mod_datatype.ScreenshotHeader()
        datatype.unpack(packet['data'])
        bpp = datatype.bpp
        height = datatype.height
        width = datatype.width
        bytesize = datatype.get_bytesize()
        colors_used = datatype.get_colors_used()
        row_size = datatype.get_row_size()
        # Each row is padded to a multiple of 4 bytes in size. The bytewidth can
        # be calculated with the formula below, but the bytewidth is also given
        # in the header.
        # bytewidth = math.ceil(row_size / 4) * 4
        bytewidth = datatype.bytewidth
        mod_logger.log.info(f"Dimensions: {datatype.width}x{datatype.height} pixels")
        mod_logger.log.info(f"Color depth: {datatype.bpp} bits per pixel")
        bmp = MicroBMP(width, height, bpp)
        # The data is sent in chunks of maximum 128 bytes, so larger rows are
        # split up to multiple packets
        max_chunk_size = 128
        pixel_array_size = math.ceil(bytewidth / max_chunk_size) * height
        start = 0
        if bpp not in [1, 2, 4, 8, 16, 24, 32]:
            raise mod_error.GarminError(f"Unsupported color depth {bpp} bpp")
        elif bpp > 8:
            # A color table is mandatory for bitmaps with color depths ≤ 8 bits
            mod_logger.log.info(f"{bpp}-bit color depth has no color table")
            chunk_count = pixel_array_size
        elif bpp == 2:
            # For some reason the Screenshot Transfer Protocol doesn't send a
            # color table for the 2 bpp format. The palette should contain the
            # grayscale colors (255, 255, 255), (192, 192, 192), (128, 128,
            # 128), (0, 0, 0).
            bmp.palette = [bytearray((255, 255, 255)), bytearray((192, 192, 192)), bytearray((128, 128, 128)), bytearray((0, 0, 0))]
            chunk_count = pixel_array_size
        else:
            mod_logger.log.info("Expect color table")
            # The color table is sent per color, so each packet data size is 11
            # bytes, consisting of 4 bytes for the section, 4 bytes for the
            # offset, and 3 bytes for the color.
            color_table_size = colors_used
            chunk_count = color_table_size + pixel_array_size
            color_table = []
            for idx in range(chunk_count):
                packet = self.gps.link.expect_packet(self.gps.link.pid_screen_data)
                start += 1
                datatype = mod_datatype.ScreenshotColor()
                datatype.unpack(packet['data'])
                section = datatype.get_section()
                if section != 'color_table':
                    raise mod_error.ProtocolError(f"Invalid section: expected color_table, got {section}")
                color = datatype.get_color().get_bytearray()
                color_table.append(color)
                bmp.palette = color_table
                if callback:
                    callback(datatype, idx+1, chunk_count)
        mod_logger.log.info("Expect pixel array")
        # The pixel array is sent per row, "bottom-up", with a packet data size
        # of maximum 136 bytes, consisting of 4 bytes for the section, 4 bytes
        # for the offset, and maximum 128 bytes for the chunk of pixel array.
        pixel_array = bytearray()
        for idx in range(start, chunk_count):
            packet = self.gps.link.expect_packet(self.gps.link.pid_screen_data)
            datatype = mod_datatype.ScreenshotChunk()
            datatype.unpack(packet['data'])
            if datatype.get_section() != 'pixel_array':
                raise mod_error.ProtocolError(f"Invalid section: expected pixel_array, got {section}")
            pixel_array.extend(datatype.chunk)
            if callback:
                callback(datatype, idx+1, chunk_count)
        # Rearrange the pixel array from bottom-up to top-down and remove padding
        bmp.parray = bytearray()
        for pos in range(0, len(pixel_array), bytewidth):
            row = pixel_array[::-1][pos:pos+row_size]
            bmp.parray.extend(row)
        return bmp
