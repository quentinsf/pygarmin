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
from functools import cached_property
import io
from microbmp import MicroBMP
import os
from . import capabilities as mod_capabilities
from . import datatype as mod_datatype
from . import error as mod_error
from . import link as mod_link
from . import logger as mod_logger
from . import protocol as mod_protocol


class Garmin():
    """Garmin GPS device object.

    The class provides methods to communicate with the hardware.

    Most GNU/Linux distributions use a kernel module called ``garmin_gps`` to
    make a USB Garmin device accessible via a serial port. In order to
    communicate with a Windows computer via a serial link, Garmin USB drivers
    need to be installed. To communicate with a Garmin device connected to the
    serial port ``/dev/ttyUSB0``, you could try this:

    >>> from garmin import garmin, link
    >>> port = '/dev/ttyUSB0'
    >>> phys = link.SerialLink(port)
    >>> gps = garmin.Garmin(phys)
    >>> print(gps.product_data)

    Alternatively, internal USB support can be used. For this to work on
    GNU/Linux, you probably should remove and blacklist the ``garmin_gps``
    kernel module.

    >>> from garmin import garmin, link
    >>> phys = link.USBLink()
    >>> gps = garmin.Garmin(phys)
    >>> print(gps.product_data)

    """
    _protocols = {
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
        'A1003': 'workout_occurrence_transfer_protocol',
        'A1004': 'fitness_user_profile_transfer_protocol',
        'A1005': 'workout_limits_transfer_protocol',
        'A1006': 'course_transfer_protocol',
        'A1007': 'course_lap_transfer_protocol',
        'A1008': 'course_point_transfer_protocol',
        'A1009': 'course_limits_transfer_protocol',
        'A1012': 'course_track_transfer_protocol',
        'A1051': 'external_time_data_sync_protocol',
    }

    def __init__(self, physicalLayer):
        self.phys = physicalLayer
        #: Basic Link Protocol
        self.link = mod_protocol.L000(self.phys)
        #: Product Data Protocol
        self.product_data_protocol = mod_protocol.A000(self.link)
        self.product_data = self.product_data_protocol.get_product_data()
        #: Product ID
        self.product_id = self.product_data.product_id
        #: Software version
        self.software_version = self.product_data.software_version / 100
        #: Product description
        self.product_description = self.product_data.product_description.decode('ascii')
        self.protocol_capability = mod_protocol.A001(self.link)
        #: Protocol capabilities and device-specific data types
        self.supported_protocols = self._get_protocols()
        self.registered_protocols = self._register_protocols(self.supported_protocols)
        #: Link Protocol
        self.link = self._create_protocol('link_protocol', self.phys)

    @cached_property
    def command(self):
        """Device Command Protocol."""
        return self._create_protocol('device_command_protocol', self)

    @cached_property
    def transmission(self):
        """Transmission Protocol."""
        return self._create_protocol('transmission_protocol', self)

    @cached_property
    def waypoint_transfer(self):
        """Waypoint Transfer Protocol."""
        return self._create_protocol('waypoint_transfer_protocol', self)

    @cached_property
    def waypoint_category_transfer(self):
        """Waypoint Category Transfer Protocol."""
        return self._create_protocol('waypoint_category_transfer_protocol', self)

    @cached_property
    def route_transfer(self):
        """Route Transfer Protocol."""
        return self._create_protocol('route_transfer_protocol', self)

    @cached_property
    def track_log_transfer(self):
        """Track Log Transfer Protocol."""
        return self._create_protocol('track_log_transfer_protocol', self)

    @cached_property
    def proximity_waypoint_transfer(self):
        """Proximity Waypoint Transfer Protocol."""
        return self._create_protocol('proximity_waypoint_transfer_protocol', self)

    @cached_property
    def almanac_transfer(self):
        """Almanac Transfer Protocol."""
        return self._create_protocol('almanac_transfer_protocol', self)

    @cached_property
    def date_and_time_initialization(self):
        """Date And Time Initialization Protocol."""
        return self._create_protocol('date_and_time_initialization_protocol', self)

    @cached_property
    def flightbook_transfer(self):
        """Flightbook Transfer Protocol."""
        return self._create_protocol('flightbook_transfer_protocol', self)

    @cached_property
    def position_initialization(self):
        """Position Initialization Protocol."""
        return self._create_protocol('position_initialization_protocol', self)

    @cached_property
    def pvt(self):
        """PVT Protocol."""
        return self._create_protocol('pvt_protocol', self)

    @cached_property
    def map_transfer(self):
        """Map Transfer Protocol."""
        return self._create_protocol('map_transfer_protocol', self)

    @cached_property
    def map_unlock(self):
        """Map Unlock Protocol."""
        return self._create_protocol('map_unlock_protocol', self)

    @cached_property
    def lap_transfer(self):
        """Lap Transfer Protocol."""
        return self._create_protocol('lap_transfer_protocol', self)

    @cached_property
    def run_transfer(self):
        """Run Transfer Protocol."""
        return self._create_protocol('run_transfer_protocol', self)

    @cached_property
    def workout_transfer(self):
        """Workout Transfer Protocol."""
        return self._create_protocol('workout_transfer_protocol', self)

    @cached_property
    def workout_occurrence_transfer(self):
        """Workout Occurrence Transfer Protocol."""
        return self._create_protocol('workout_occurrence_transfer_protocol', self)

    @cached_property
    def fitness_user_profile_transfer(self):
        """Fitness User Profile Transfer Protocol."""
        return self._create_protocol('fitness_user_profile_transfer_protocol', self)

    @cached_property
    def workout_limits_transfer(self):
        """Workout Limits Transfer Protocol."""
        return self._create_protocol('workout_limits_transfer_protocol', self)

    @cached_property
    def course_transfer(self):
        """Course Transfer Protocol."""
        return self._create_protocol('course_transfer_protocol', self)

    @cached_property
    def course_lap_transfer(self):
        """Course Lap Transfer Protocol."""
        return self._create_protocol('course_lap_transfer_protocol', self)

    @cached_property
    def course_point_transfer(self):
        """Course Point Transfer Protocol."""
        return self._create_protocol('course_point_transfer_protocol', self)

    @cached_property
    def course_limits_transfer(self):
        """Course Limits Transfer Protocol."""
        return self._create_protocol('course_limits_transfer_protocol', self)

    @cached_property
    def course_track_transfer(self):
        """Course Track Transfer Protocol."""
        return self._create_protocol('course_track_transfer_protocol', self)

    @cached_property
    def screenshot_transfer(self):
        """Screenshot Transfer Protocol."""
        return ScreenshotTransfer(self)

    @cached_property
    def image_transfer(self):
        """Image Transfer Protocol."""
        return ImageTransfer(self)

    def _lookup_protocols(self, product_id, software_version):
        mod_logger.log.info("Look up protocols by Product ID and software version...")
        model = mod_capabilities.device_protocol_capabilities.get(product_id)
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
            mod_logger.log.info("Get supported protocols and data types...")
            protocols = self.protocol_capability.get_protocols()
            mod_logger.log.debug(f"Supported protocols and data types: {protocols}")
        except mod_error.LinkError:
            mod_logger.log.info("Protocol Capability Protocol not supported by the device")
            try:
                protocols = self._lookup_protocols(self.product_id, self.software_version)
            except KeyError:
                raise mod_error.ProtocolError("Couldn't determine protocol capabilities")
        return protocols

    def _register_protocols(self, supported_protocols):
        """Register the supported protocols."""
        protocols = {}
        for protocol_datatypes in supported_protocols:
            protocol = protocol_datatypes[0]
            datatypes = protocol_datatypes[1:]
            if protocol in self._protocols:
                protocol_name = self._protocols[protocol]
                protocol_class = getattr(mod_protocol, protocol)
                protocols[protocol_name] = [protocol_class]
                mod_logger.log.info(f"Register protocol {protocol}.")
                if datatypes:
                    datatype_classes = [getattr(mod_datatype, datatype) for datatype in datatypes]
                    protocols[protocol_name].extend(datatype_classes)
                    mod_logger.log.info(f"Register datatypes {*datatypes, }.")
            else:
                mod_logger.log.info(f"Ignore undocumented protocol {protocol}.")
        mod_logger.log.debug(f"Registered protocols and data types: {protocols}")
        return protocols

    def _create_protocol(self, key, *args):
        protocol_datatypes = self.registered_protocols.get(key)
        if protocol_datatypes:
            mod_logger.log.info(f"Create protocol {key}...")
            protocol = protocol_datatypes[0]
            datatypes = protocol_datatypes[1:]
            if datatypes:
                return protocol(*args, datatypes=datatypes)
            else:
                return protocol(*args)
        else:
            mod_logger.log.info(f"Protocol {key} is not supported.")

    @cached_property
    def unit_id(self):
        """Return the device’s unit ID.

        This feature is undocumented in the spec. The implementation is derived
        from capturing raw USB traffic from Garmin's proprietary MapSource
        application version 6.16.3
        (https://www8.garmin.com/support/download_details.jsp?id=209).

        """
        mod_logger.log.info("Request Product Id...")
        self.link.send_packet(self.link.pid_command_data,
                              self.command.cmnd_transfer_unit_id)
        mod_logger.log.info("Expect Product Id packet")
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

    def get_waypoint_categories(self, callback=None):
        """Download waypoint categories.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of waypoint category datatypes
        :rtype: list

        """
        return self.waypoint_category_transfer.get_data(callback)

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
        :type data: list of route datatypes or list of lists of dicts
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
            raise mod_error.GarminError("Protocol track_log_transfer_protocol is not supported")
        return self.track_log_transfer.get_data(callback)

    def put_tracks(self, data, callback=None):
        """Upload tracks.

        :param data: data
        :type data: list of track datatypes or list of lists of dicts
        :param callback: optional callback function
        :type callback: function or None
        :return: None

        """
        if self.track_log_transfer is None:
            raise mod_error.GarminError("Protocol track_log_transfer_protocol is not supported")
        return self.track_log_transfer.put_data(data, callback)

    def get_proximities(self, callback=None):
        """Download proximities.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of proximity datatypes
        :rtype: list

        """
        if self.proximity_waypoint_transfer is None:
            raise mod_error.GarminError("Protocol proximity_waypoint_transfer_protocol is not supported")
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
            raise mod_error.GarminError("Protocol proximity_waypoint_transfer_protocol is not supported")
        return self.proximity_waypoint_transfer.put_data(data, callback)

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
            raise mod_error.GarminError("Protocol flightbook_transfer_protocol is not supported")
        return self.flightbook_transfer.get_data(callback)

    def get_position(self, callback=None):
        return self.position_initialization.get_data(callback)

    def pvt_on(self):
        """Turn on PVT mode.

        In PVT mode the device will transmit packets approximately once per
        second

        """
        mod_logger.log.info(f"Start transmitting PVT data")
        return self.pvt.data_on()

    def pvt_off(self):
        """Turn off PVT mode."""
        mod_logger.log.info("Stop transmitting PVT data")
        return self.pvt.data_off()

    def get_pvt(self, callback=None):
        """Get real-time position, velocity, and time (PVT).

        :param callback: optional callback function
        :type callback: function or None
        :return: PVT datatype
        :rtype: garmin.PVT

        """
        return self.pvt.get_data(callback)

    def get_memory_properties(self):
        """Return memory info."""
        if self.map_transfer is None:
            raise mod_error.GarminError("Protocol map_transfer_protocol is not supported")
        return self.map_transfer.get_memory_properties()

    def get_map_properties(self):
        """Return map info."""
        if self.map_transfer is None:
            raise mod_error.GarminError("Protocol map_transfer_protocol is not supported")
        return self.map_transfer.get_map_properties()

    def del_map(self):
        """Delete map."""
        if self.map_transfer is None:
            raise mod_error.GarminError("Protocol map_transfer_protocol is not supported")
        return self.map_transfer._write_memory(None)

    def get_map(self, callback=None):
        """Download map.

        The map is received as raw data and is in Garmin IMG format.

        :param callback: optional callback function
        :type callback: function or None
        :raise error.GarminError: if the map_transfer_protocol is not supported.
        :return: map
        :rtype: bytes

        """
        if self.map_transfer is None:
            raise mod_error.GarminError("Protocol map_transfer_protocol is not supported")
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
        :raise error.GarminError: if the map_transfer_protocol is not supported.
        :return: None

        """
        if self.map_transfer is None:
            raise mod_error.GarminError("Protocol map_transfer_protocol is not supported")
        if isinstance(data, str):
            map_size = os.path.getsize(data)
        elif isinstance(data, io.BufferedReader):
            map_size = os.stat(data.fileno()).st_size
        elif isinstance(data, bytes):
            map_size = len(data)
        mem_size = self.map_transfer.memory_properties.mem_size
        mod_logger.log.info(f"Map size: {map_size} bytes")
        if map_size > mem_size:
            raise mod_error.GarminError("Insufficient memory to upload map")
        if key:
            self.map_unlock.send_unlock_key(key)
        # Maximize the baudrate if supported
        if isinstance(self.phys, mod_link.SerialLink) and self.transmission:
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
        if isinstance(self.phys, mod_link.SerialLink) and self.transmission:
            self.transmission.set_baudrate(current_baudrate)

    def get_laps(self, callback=None):
        """Download laps.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of lap datatypes
        :rtype: list

        """
        if self.lap_transfer is None:
            raise mod_error.GarminError("Protocol lap_transfer_protocol is not supported")
        return self.lap_transfer.get_data(callback)

    def get_runs(self, callback=None):
        """Download runs.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of run datatypes
        :rtype: list

        """
        if self.run_transfer is None:
            raise mod_error.GarminError("Protocol run_transfer_protocol is not supported")
        return self.run_transfer.get_data(callback)

    def get_workouts(self, callback=None):
        """Download workouts.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of workout datatypes
        :rtype: list

        """
        if self.workout_transfer is None:
            raise mod_error.GarminError("Protocol workout_transfer_protocol is not supported")
        return self.workout_transfer.get_data(callback)

    def get_workout_occurrences(self, callback=None):
        """Download workout occurrences.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of workout occurrence datatypes
        :rtype: list

        """
        if self.workout_occurrence_transfer is None:
            raise mod_error.GarminError("Protocol workout_occurrence_transfer_protocol is not supported")
        return self.workout_occurrence_transfer.get_data(callback)

    def get_fitness_user_profile(self, callback=None):
        """Download fitness user profile.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of workout occurrence datatypes
        :rtype: list

        """
        if self.fitness_user_profile_transfer is None:
            raise mod_error.GarminError("Protocol fitness_user_profile_transfer_protocol is not supported")
        return self.fitness_user_profile_transfer.get_data(callback)

    def get_workout_limits(self, callback=None):
        """Download workout limits.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of workout limits datatypes
        :rtype: list

        """
        if self.workout_limits_transfer is None:
            raise mod_error.GarminError("Protocol workout_limits_transfer_protocol is not supported")
        return self.workout_limits_transfer.get_data(callback)

    def get_courses(self, callback=None):
        """Download workout occurrences.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of workout occurrence datatypes
        :rtype: list

        """
        if self.course_transfer is None:
            raise mod_error.GarminError("Protocol course_transfer_protocol is not supported")
        return self.course_transfer.get_data(callback)

    def get_course_laps(self, callback=None):
        """Download workout occurrences.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of workout occurrence datatypes
        :rtype: list

        """
        if self.course_lap_transfer is None:
            raise mod_error.GarminError("Protocol course_lap_transfer_protocol is not supported")
        return self.course_lap_transfer.get_data(callback)

    def get_course_points(self, callback=None):
        """Download workout occurrences.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of workout occurrence datatypes
        :rtype: list

        """
        if self.course_point_transfer is None:
            raise mod_error.GarminError("Protocol course_point_transfer_protocol is not supported")
        return self.course_point_transfer.get_data(callback)

    def get_course_limits(self, callback=None):
        """Download course limits.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of course limits datatypes
        :rtype: list

        """
        if self.course_limits_transfer is None:
            raise mod_error.GarminError("Protocol course_limits_transfer_protocol is not supported")
        return self.course_limits_transfer.get_data(callback)

    def get_course_tracks(self, callback=None):
        """Download workout occurrences.

        :param callback: optional callback function
        :type callback: function or None
        :return: list of workout occurrence datatypes
        :rtype: list

        """
        if self.course_track_transfer is None:
            raise mod_error.GarminError("Protocol course_track_transfer_protocol is not supported")
        return self.course_track_transfer.get_data(callback)

    def get_screenshot(self, callback=None):
        """Capture screenshot.

        The map is received as raw data and is in Garmin IMG format.

        :param callback: optional callback function
        :type callback: function or None
        :return: image file of the device's display
        :rtype: MicroBMP

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
        :rtype: MicroBMP

        """
        return self.image_transfer.get_image(idx, callback)

    def put_image(self, idx, data, callback=None):
        """Upload image.

        The index of the image can be looked up with
        :func:`Garmin.get_image_list`.

        :param idx: index of image to upload
        :type idx: int
        :param data: image data to upload
        :type data: MicroBMP or str or io.BufferedReader
        :param callback: optional callback function
        :type callback: function or None

        """
        if data is None:
            raise mod_error.GarminError("No image")
        elif isinstance(data, MicroBMP):
            bmp = data
        elif isinstance(data, str):
            bmp = MicroBMP().load(data)
        elif isinstance(data, io.BufferedReader):
            bmp = MicroBMP().read_io(data)
        else:
            raise mod_error.GarminError("Invalid image")
        self.image_transfer.put_image(idx, bmp, callback)

    def abort_transfer(self):
        """Abort transfer"""
        mod_logger.log.info("Abort transfer")
        self.command.abort_transfer()

    def turn_power_off(self):
        """Turn power off"""
        mod_logger.log.info("Turn power off")
        self.command.turn_power_off()
