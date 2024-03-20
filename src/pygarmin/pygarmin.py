#!/usr/bin/env python3
"""Pygarmin

   This is a console user application for communicating with Garmin GPS
   receivers.

   This file is part of the pygarmin distribution
   (https://github.com/quentinsf/pygarmin).

   Copyright 2022 Folkert van der Beek <folkertvanderbeek@gmail.com>

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

import argparse
import base64
import json
import logging
from microbmp import MicroBMP
import os
import pathlib
from PIL import Image, ImagePalette, UnidentifiedImageError
import re
import signal
import sys
from tabulate import tabulate
from tqdm import tqdm
import io
from . import __version__
from . import garmin as mod_garmin
from . import error as mod_error
from . import link as mod_link
from . import logger as mod_logger
from . import datatype as mod_datatype
from . import gpsd as GPSD
from . import gpx as GPX
from . import fit as FIT

logging_levels = {
    0: logging.NOTSET,
    1: logging.WARNING,
    2: logging.INFO,
    3: logging.DEBUG,
}

mod_logger.log.addHandler(logging.StreamHandler())

def _print(data):
    if type(data) == str:
        data = str.encode(data)
    sys.stdout.buffer.write(data)

def _write(path, data):
    if type(data) == bytes:
        path.write_bytes(data)
    elif type(data) == str:
        path.write_text(data)

def to_pixel_data(pixel_values, bpp):
    """Returns the pixel array of the image.

    :param pixel_values: the pixel values of the image
    :type pixel_values: list[int]
    :param bpp: the color depth of the image, must be in (1, 2, 4, 8)
    :type bpp: int
    :return: pixel_array
    :rtype: bytearray

    """
    if 8 % bpp != 0:
        sys.exit(f"{bpp}-bit color depth is not supported")
    ppb = 8 // bpp
    pixel_array = list()
    for pos in range(0, len(pixel_values), ppb):
        values = pixel_values[pos:pos+ppb]
        pixels = 0
        # Pixels are stored from left to right, so the bits of the first pixel
        # are shifted to the far left
        for idx, value in enumerate(reversed(values)):
            if value.bit_length() > bpp:
                sys.exit(f"Integer {value} cannot be represented by {bpp} bits")
            offset = idx * bpp
            pixels = pixels + (value << offset)
        pixel_array.append(pixels)
    return bytearray(pixel_array)

def to_pixel_values(pixel_array, bpp):
    """Returns the contents of this image as a list of pixel values.

    :param pixel_array: the pixel array of the image
    :type pixel_array: bytes or bytearray
    :param bpp: the color depth of the image, must be in (1, 2, 4, 8)
    :type bpp: int
    :return: list of pixel values
    :rtype: list[int]

    """
    if 8 % bpp != 0:
        sys.exit(f"{bpp}-bit color depth is not supported")
    pixel_values = []
    # Calculate the bitmask, that is the maximum integer that can be
    # represented by the number of bits per pixel
    mask = pow(2, bpp) - 1
    for byte in pixel_array:
        for offset in reversed(range(0, 8, bpp)):
            value = byte >> offset & mask
            pixel_values.append(value)
    return pixel_values

def bmp_to_pil(bmp):
    """Converts BMP to PIL image.

    :param bmp: BMP image
    :type bmp: BMP
    :return: PIL image
    :rtype: Image.Image

    """
    mod_logger.log.info("Converting BMP to PIL image")
    # PIL supports images of 1/8/24/32-bit color depth
    bpp = bmp.DIB_depth
    if bpp == 1:
        mod_logger.log.info("Using black and white mode (1)")
        mode = '1'
    elif bpp in (1, 2, 4):
        # Convert BMP to 8-bit PIL image
        mod_logger.log.info(f"Converting {bpp} bpp image to 8 bpp color depth")
        pixel_values = to_pixel_values(bmp.parray, bpp)
        pixel_data = to_pixel_data(pixel_values, 8)
        mod_logger.log.info("Using palette mode (P)")
        mode = 'P'
    elif bpp == 8:
        pixel_data = bmp.parray
        mod_logger.log.info("Using palette mode (P)")
        mode = 'P'
    elif bpp == 24:
        pixel_data = bmp.parray
        mod_logger.log.info("Using true color mode (RGB)")
        mode = 'RGB'
    else:
        sys.exit(f"{bpp}-bit color depth is not supported")
    image = Image.frombytes(mode=mode,
                                size=(bmp.DIB_w, bmp.DIB_h),
                                data=pixel_data,
                                decoder_name='raw')
    if mode == 'P':
        mod_logger.log.info("Attaching palette to image")
        # The BMP palette is a list of bytearrays, but the PIL palette must be a
        # flat list of integers (or a single bytearray)
        palette = [ channel for color in bmp.palette for channel in color ]
        mod_logger.log.debug(f"RGB color palette: {*[ tuple(color) for color in bmp.palette ], }")
        image.putpalette(palette, rawmode='RGB')
    return image


class BytesEncoder(json.JSONEncoder):
    """Custom encoder to serialize bytes by decoding them to a string."""

    def default(self, o):
        if isinstance(o, bytes):
            return base64.b64encode(o).decode('ascii')
        else:
            return super().default(o)


class BytesDecoder(json.JSONDecoder):
    """Custom decoder to deserialize bytes by decoding them from a string."""

    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, dct):
        if any(isinstance(v, str) for v in dct.values()):
            return {k: (base64.b64decode(v) if isinstance(v, str) else v) for (k, v) in dct.items()}
        return dct


class ProgressBar(tqdm):

    def update_to(self, object, current, total):
        self.total = total
        self.update(current - self.n)


class Pygarmin:
    protocol_names = {
        'L000': 'Basic Link Protocol',
        'L001': 'Link Protocol 1',
        'L002': 'Link Protocol 2',
        'A000': 'Product Data Protocol',
        'A001': 'Protocol Capability Protocol',
        'A010': 'Device Command Protocol 1',
        'A011': 'Device Command Protocol 2',
        'T001': 'Transmission Protocol',
        'A100': 'Waypoint Transfer Protocol',
        'A101': 'Waypoint Category Transfer Protocol',
        'A200': 'Route Transfer Protocol',
        'A201': 'Route Transfer Protocol',
        'A300': 'Track Log Transfer Protocol',
        'A301': 'Track Log Transfer Protocol',
        'A302': 'Track Log Transfer Protocol',
        'A400': 'Proximity Waypoint Transfer Protocol',
        'A500': 'Almanac Transfer Protocol',
        'A600': 'Date And Time Initialization Protocol',
        'A650': 'Flightbook Transfer Protocol',
        'A700': 'Position Initialization Protocol',
        'A800': 'PVT Protocol',
        'A900': 'Map Transfer Protocol',
        'A902': 'Map Unlock Protocol',
        'A906': 'Lap Transfer Protocol',
        'A1000': 'Run Transfer Protocol',
        'A1002': 'Workout Transfer Protocol',
        'A1004': 'Fitness User Profile Transfer Protocol',
        'A1005': 'Workout Limits Transfer Protocol',
        'A1006': 'Course Transfer Protocol',
        'A1009': 'Course Limits Transfer Protocol',
        'A1051': 'External Time Data Sync Protocol',
    }

    def __init__(self, port='usb:'):
        self.port = port
        self.gps = self.get_gps(self.port)


    def get_gps(self, port):
        phys = mod_link.USBLink() if port == 'usb:' else mod_link.SerialLink(port)
        mod_logger.log.info(f"Listening on port {port}")
        return mod_garmin.Garmin(phys)

    def info(self, args):
        info = "Product information\n"
        info += "===================\n"
        info += f"Product ID: {self.gps.product_id}\n"
        info += f"Software version: {self.gps.software_version:.2f}\n"
        info += f"Product description: {self.gps.product_description}\n"
        info += f"Unit ID: {self.gps.unit_id}\n"
        args.filename.write(info)

    def protocols(self, args):
        info = "Supported protocols and data types\n"
        info += "==================================\n"
        for protocol_datatypes in self.gps.supported_protocols:
            protocol = protocol_datatypes[0]
            datatypes = protocol_datatypes[1:]
            protocol_name = self.protocol_names.get(protocol, "Unknown Protocol")
            info += "\n"
            info += f"{protocol_name}\n"
            info += f"{'-' * len(protocol_name)}\n"
            if datatypes:
                info += f"{protocol}: {', '.join(datatypes)}\n"
            else:
                info += f"{protocol}\n"
        args.filename.write(info)

    def memory(self, args):
        try:
            data = self.gps.get_memory_properties()
            info = "Memory information\n"
            info += "==================\n"
            info += f"Memory region: {data.mem_region}\n"
            info += f"Maximum number of tiles: {data.max_tiles}\n"
            info += f"Memory size: {data.mem_size}\n"
            args.filename.write(info)
        except mod_error.GarminError as e:
            sys.exit(f"{e}")

    def map_info(self, args):
        try:
            records = self.gps.get_map_properties()
            if records is None:
                mod_logger.log.warning("Map not found")
            else:
                info = "Map information\n"
                info += "===============\n"
                for record in records:
                    if isinstance(record, mod_datatype.MapSegment):
                        info += "Map segment description\n"
                        info += "-----------------------\n"
                        info += f"Product ID: {record.pid}\n"
                        info += f"Family ID: {record.fid}\n"
                        info += f"Segment ID: {record.segment_id}\n"
                        info += f"Family name: {str(record.name, 'latin_1')}\n"
                        info += f"Segment name: {str(record.segment_name, 'latin_1')}\n"
                        info += f"Area name: {str(record.area_name, 'latin_1')}\n"
                        info += "\n"
                    elif isinstance(record, mod_datatype.MapSet):
                        info += "Map set description\n"
                        info += "-------------------\n"
                        info += f"Mapset name: {str(record.mapset_name, 'latin_1')}\n"
                        info += "\n"
                    elif isinstance(record, mod_datatype.MapUnlock):
                        info += "Map unlock description\n"
                        info += "----------------------\n"
                        info += f"Unlock code: {str(unlock_code, 'latin_1')}\n"
                        info += "\n"
                    elif isinstance(record, mod_datatype.MapProduct):
                        info += "Map product description\n"
                        info += "-----------------------\n"
                        info += f"Product ID: {record.pid}\n"
                        info += f"Family ID: {record.fid}\n"
                        info += f"Family name: {str(record.name, 'latin_1')}\n"
                        info += "\n"
                args.filename.write(info)
        except mod_error.GarminError as e:
            sys.exit(f"{e}")

    def get_waypoints(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                datatypes = self.gps.get_waypoints(callback=progress_bar.update_to)
        else:
            datatypes = self.gps.get_waypoints()
        if args.format == 'txt':
            for datatype in datatypes:
                args.filename.write(f"{str(datatype)}\n")
        elif args.format == 'garmin':
            for datatype in datatypes:
                args.filename.write(f"{repr(datatype)}\n")
        elif args.format == 'json':
            waypoints = [datatype.get_dict() for datatype in datatypes]
            json.dump(waypoints, args.filename, cls=BytesEncoder)
        elif args.format == 'gpx':
            gpx_waypoints = GPX.GPXWaypoints(datatypes)
            args.filename.write(f"{gpx_waypoints.gpx.to_xml()}\n")
        else:
            sys.exit(f"Output format {args.format} is not supported")

    def put_waypoints(self, args):
        if args.format == 'garmin':
            data = []
            for line in args.filename:
                object = eval('mod_datatype.' + line)
                data.append(object)
        elif args.format == 'json':
            data = json.load(args.filename, cls=BytesDecoder)
        elif args.format == 'gpx':
            datatypes = self.gps.waypoint_transfer.datatypes
            gpx = GPX.GarminWaypoints(args.filename, datatypes)
            data = gpx.waypoints
        else:
            sys.exit(f"Output format {args.format} is not supported")
        if args.progress:
            with ProgressBar() as progress_bar:
                self.gps.put_waypoints(data, callback=progress_bar.update_to)
        else:
            self.gps.put_waypoints(data)

    def get_routes(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                datatypes = self.gps.get_routes(callback=progress_bar.update_to)
        else:
            datatypes = self.gps.get_routes()
        if args.format == 'txt':
            for datatype in datatypes:
                args.filename.write(f"{str(datatype)}\n")
        elif args.format == 'garmin':
            for datatype in datatypes:
                args.filename.write(f"{repr(datatype)}\n")
        else:
            if any(isinstance(datatype, mod_datatype.RteHdr) for datatype in datatypes):
                # Route headers and associated points are grouped
                routes = []
                for datatype in datatypes:
                    if isinstance(datatype, mod_datatype.RteHdr):
                        routes.append([datatype])
                    elif isinstance(datatype, mod_datatype.Wpt):
                        routes[-1].append(datatype)
            else:
                routes = [datatypes]
            if args.format == 'json':
                json.dump([[datatype.get_dict() for datatype in route] for route in routes], args.filename, cls=BytesEncoder)
            elif args.format == 'gpx':
                gpx_routes = GPX.GPXRoutes(routes)
                args.filename.write(f"{gpx_routes.gpx.to_xml()}\n")
            else:
                sys.exit(f"Output format {args.format} is not supported")

    def put_routes(self, args):
        if args.format == 'garmin':
            data = []
            for line in args.filename:
                object = eval('mod_datatype.' + line)
                data.append(object)
        elif args.format == 'json':
            data = json.load(args.filename, cls=BytesDecoder)
        elif args.format == 'gpx':
            datatypes = self.gps.route_transfer.datatypes
            gpx = GPX.GarminRoutes(args.filename, datatypes)
            data = gpx.routes
        else:
            sys.exit(f"Output format {args.format} is not supported")
        if args.progress:
            with ProgressBar() as progress_bar:
                self.gps.put_routes(data, callback=progress_bar.update_to)
        else:
            self.gps.put_routes(data)

    def get_tracks(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                datatypes = self.gps.get_tracks(callback=progress_bar.update_to)
        else:
            datatypes = self.gps.get_tracks()
        if args.format == 'txt':
            for point in datatypes:
                args.filename.write(f"{str(point)}\n")
        elif args.format == 'garmin':
            for point in datatypes:
                args.filename.write(f"{repr(point)}\n")
        else:
            if any(isinstance(datatype, mod_datatype.TrkHdr) for datatype in datatypes):
                # Track headers and associated points are grouped
                tracks = []
                for datatype in datatypes:
                    if isinstance(datatype, mod_datatype.TrkHdr):
                        tracks.append([datatype])
                    elif isinstance(datatype, mod_datatype.TrkPoint):
                        tracks[-1].append(datatype)
            else:
                tracks = [datatypes]
        if args.format == 'json':
                json.dump([[datatype.get_dict() for datatype in track] for track in tracks], args.filename, cls=BytesEncoder)
        elif args.format == 'gpx':
            gpx_tracks = GPX.GPXTracks(tracks)
            args.filename.write(f"{gpx_tracks.gpx.to_xml()}\n")
        else:
            sys.exit(f"Output format {args.format} is not supported")

    def put_tracks(self, args):
        if args.format == 'garmin':
            data = []
            for line in args.filename:
                object = eval('mod_datatype.' + line)
                data.append(object)
        elif args.format == 'json':
            data = json.load(args.filename, cls=BytesDecoder)
        elif args.format == 'gpx':
            datatypes = self.gps.track_log_transfer.datatypes
            gpx = GPX.GarminTracks(args.filename, datatypes)
            data = gpx.tracks
        else:
            sys.exit(f"Output format {args.format} is not supported")
        if args.progress:
            with ProgressBar() as progress_bar:
                self.gps.put_tracks(data, callback=progress_bar.update_to)
        else:
            self.gps.put_tracks(data)

    def get_proximities(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                datatypes = self.gps.get_proximities(callback=progress_bar.update_to)
        else:
            datatypes = self.gps.get_proximities()
        if args.format == 'txt':
            for datatype in datatypes:
                args.filename.write(f"{str(datatype)}\n")
        elif args.format == 'garmin':
            for datatype in datatypes:
                args.filename.write(f"{repr(datatype)}\n")
        elif args.format == 'json':
            proximities = [datatype.get_dict() for datatype in datatypes]
            json.dump(proximities, args.filename, cls=BytesEncoder)
        elif args.format == 'gpx':
            gpx_proximities = GPX.GPXWaypoints(datatypes)
            args.filename.write(f"{gpx_proximities.gpx.to_xml()}\n")
        else:
            sys.exit(f"Output format {args.format} is not supported")

    def put_proximities(self, args):
        if args.format == 'garmin':
            data = []
            for line in args.filename:
                object = eval(line)
                data.append(object)
        elif args.format == 'json':
            data = json.load(args.filename, cls=BytesDecoder)
        elif args.format == 'gpx':
            datatypes = self.gps.proximity_waypoint_transfer.datatypes
            gpx = GPX.GarminWaypoints(args.filename, datatypes)
            data = gpx.waypoints
        else:
            sys.exit(f"Output format {args.format} is not supported")
        if args.progress:
            with ProgressBar() as progress_bar:
                self.gps.put_proximities(data, callback=progress_bar.update_to)
        else:
            self.gps.put_proximities(data)

    def get_almanac(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                datatypes = self.gps.get_almanac(callback=progress_bar.update_to)
        else:
            datatypes = self.gps.get_almanac()
        if args.format == 'txt':
            for datatype in datatypes:
                args.filename.write(f"{str(datatype)}\n")
        elif args.format == 'garmin':
            for datatype in datatypes:
                args.filename.write(f"{repr(datatype)}\n")
        elif args.format == 'json':
            almanacs = [datatype.get_dict() for datatype in datatypes]
            json.dump(almanacs, args.filename, cls=BytesEncoder)
        else:
            sys.exit(f"Output format {args.format} is not supported")

    def get_time(self, args):
        time = self.gps.get_time()
        if args.format == 'txt':
            args.filename.write(f"{time.get_datetime()}\n")
        elif args.format == 'garmin':
            args.filename.write(f"{repr(time)}\n")
        elif args.format == 'json':
            json.dump(time.get_dict(), args.filename, cls=BytesEncoder)
        else:
            sys.exit(f"Output format {args.format} is not supported")

    def get_position(self, args):
        position = self.gps.get_position()
        if args.format == 'txt':
            args.filename.write(f"{str(position.as_degrees())}\n")
        elif args.format == 'garmin':
            args.filename.write(f"{repr(position)}\n")
        elif args.format == 'json':
            json.dump(position.get_dict(), args.filename, cls=BytesEncoder)
        else:
            sys.exit(f"Output format {args.format} is not supported")

    def pvt(self, args):
        def signal_handler(signal, frame):
            self.gps.pvt_off()
            sys.exit(0)
        mod_logger.log.warning("Press Ctrl-C to quit")
        # Catch interrupt from keyboard (Control-C)
        signal.signal(signal.SIGINT, signal_handler)
        self.gps.pvt_on()
        # In PVT mode the device will transmit packets approximately once per
        # second, but the default timeout of 1 second will lead to a timeout
        # error frequently
        self.gps.phys.set_timeout(2)
        while True:
            pvt = self.gps.get_pvt()
            if args.format == 'txt':
                args.filename.write(f"{str(pvt)}\n")
            elif args.format == 'garmin':
                args.filename.write(f"{repr(pvt)}\n")
            elif args.format == 'gpsd':
                if isinstance(pvt, mod_datatype.D800):
                    args.filename.write(f"{GPSD.TPV(pvt)}\n")
                elif isinstance(pvt, mod_datatype.Satellite):
                    args.filename.write(f"{GPSD.SKY(pvt)}\n")
                else:
                    mod_logger.log.warning(f"Unknown datatype {type(pvt).__name__}")
            else:
                sys.exit(f"Output format {args.format} is not supported")
            args.filename.flush()

    def get_laps(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                laps = self.gps.get_laps(callback=progress_bar.update_to)
        else:
            laps = self.gps.get_laps()
        for lap in laps:
            if args.format == 'txt':
                args.filename.write(f"{str(lap)}\n")
            elif args.format == 'garmin':
                args.filename.write(f"{repr(lap)}\n")
            else:
                sys.exit(f"Output format {args.format} is not supported")

    def get_runs(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                datatypes = self.gps.get_runs(callback=progress_bar.update_to)
        else:
            datatypes = self.gps.get_runs()
        runs = []
        laps = []
        tracks = []
        # First, separate the datatypes by type
        for datatype in datatypes:
            if isinstance(datatype, mod_datatype.Run):
                runs.append(datatype)
            elif isinstance(datatype, mod_datatype.Lap):
                laps.append(datatype)
                # Track headers and associated points are grouped
            elif isinstance(datatype, mod_datatype.TrkHdr):
                tracks.append([datatype])
            elif isinstance(datatype, mod_datatype.TrkPoint):
                tracks[-1].append(datatype)
        # Second, gather the datatypes per run
        result = []
        for idx, run in enumerate(runs):
            mod_logger.log.info(f"Adding run {idx}")
            lap_indices = range(run.first_lap_index, run.last_lap_index + 1)
            track_index = run.track_index
            laps = [lap for lap in laps if lap.index in lap_indices]
            for track in tracks:
                if track[0].index == track_index:
                    track = track
                    break
            result.append([run, laps, track])
        for idx, run in enumerate(result):
            if args.format == 'txt':
                datatypes = []
                datatypes.append(str(run[0]))
                datatypes.extend([str(lap) for lap in run[1]])
                datatypes.extend([str(point) for point in run[2]])
                data = '\n'.join(datatypes)
            elif args.format == 'garmin':
                datatypes = []
                datatypes.append(repr(run[0]))
                datatypes.extend([repr(lap) for lap in run[1]])
                datatypes.extend([repr(point) for point in run[2]])
                data = '\n'.join(datatypes)
            elif args.format == 'fit':
                activity = [run]
                fit = FIT.FITActivity(self.gps, activity)
                fit_file = fit.build()
                data = fit_file.to_bytes()
            else:
                sys.exit(f"Output format {args.format} is not supported")
            if args.filename == sys.stdout:
                _print(data)
            else:
                single_modulo = '(?<!%)%(?!%)'  # match a single % character
                if os.path.isdir(args.filename):
                    # No filename is given, so use the start time by default
                    track = run[2]
                    stem = track[1].get_datetime().astimezone().isoformat()
                    if args.format == 'fit':
                        suffix = '.fit'
                    elif args.format == 'txt' or args.format == 'garmin':
                        suffix = '.txt'
                    filename = stem + suffix
                    path = os.path.join(args.filename, filename)
                elif re.search(single_modulo, args.filename) is not None:
                    # filename is a formatting string
                    path = str(args.filename % idx)
                else:
                    # filename doesn't contain a single % and therefore isn't a pattern
                    path = args.filename
                    if len(result) > 1:
                        stem = pathlib.Path(path).stem
                        suffix = pathlib.Path(path).suffix
                        path = f"{stem}-{idx}{suffix}"
                mod_logger.log.info(f"Saving {path}")
                _write(pathlib.Path(path), data)

    def get_workouts(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                datatypes = self.gps.get_workouts(callback=progress_bar.update_to)
        else:
            datatypes = self.gps.get_workouts()
        for idx, datatype in enumerate(datatypes):
            if args.format == 'txt':
                data = str(datatype) + '\n'
            elif args.format == 'garmin':
                data = repr(datatype) + '\n'
            elif args.format == 'fit':
                fit = FIT.FITWorkout(self.gps, datatype)
                fit_file = fit.build()
                data = fit_file.to_bytes()
            else:
                sys.exit(f"Output format {args.format} is not supported")
            if args.filename == sys.stdout:
                _print(data)
            else:
                single_modulo = '(?<!%)%(?!%)'  # match a single % character
                if os.path.isdir(args.filename):
                    # No filename is given, so use the workout name by default
                    stem = datatype.get_name()
                    if args.format == 'fit':
                        suffix = '.fit'
                    elif args.format == 'txt' or args.format == 'garmin':
                        suffix = '.txt'
                    filename = stem + suffix
                    path = os.path.join(args.filename, filename)
                elif re.search(single_modulo, args.filename) is not None:
                    # filename is a formatting string
                    path = str(args.filename % idx)
                else:
                    # filename doesn't contain a single % and therefore isn't a pattern
                    path = args.filename
                    if len(datatypes) > 1:
                        stem = pathlib.Path(path).stem
                        suffix = pathlib.Path(path).suffix
                        path = f"{stem}-{idx}{suffix}"
                mod_logger.log.info(f"Saving {path}")
                _write(pathlib.Path(path), data)

    def get_courses(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                datatypes = self.gps.get_courses(callback=progress_bar.update_to)
        else:
            datatypes = self.gps.get_courses()
        courses = []
        laps = []
        tracks = []
        points = []
        # First, separate the datatypes
        for datatype in datatypes:
            if isinstance(datatype, mod_datatype.Course):
                courses.append(datatype)
            elif isinstance(datatype, mod_datatype.CourseLap):
                laps.append(datatype)
                # Track headers and associated points are grouped
            elif isinstance(datatype, mod_datatype.TrkHdr):
                tracks.append([datatype])
            elif isinstance(datatype, mod_datatype.TrkPoint):
                tracks[-1].append(datatype)
            elif isinstance(datatype, mod_datatype.CoursePoint):
                points.append(datatype)
        # Second, gather the datatypes per course
        result = []
        for course in courses:
            mod_logger.log.info(f"Adding course {course.get_course_name()}")
            course_index = course.index
            track_index = course.track_index
            course_laps = [ lap for lap in laps if lap.course_index == course_index ]
            for track in tracks:
                if track[0].index == track_index:
                    course_track = track
                    break
            course_points = [ point for point in points if point.course_index == course_index ]
            result.append([course, course_laps, course_track, course_points])
        for idx, course in enumerate(result):
            if args.format == 'txt':
                datatypes = []
                datatypes.append(str(course[0]))
                datatypes.extend([str(lap) for lap in course[1]])
                datatypes.append(str(course[2]))
                datatypes.extend([str(point) for point in course[3]])
                data = '\n'.join(datatypes)
            elif args.format == 'garmin':
                datatypes = []
                datatypes.append(repr(course[0]))
                mod_logger.log.info(f"{repr(course[0])}")
                datatypes.extend([repr(lap) for lap in course[1]])
                mod_logger.log.info(f"{[repr(lap) for lap in course[1]]}")
                datatypes.append(repr(course[2]))
                datatypes.extend([repr(point) for point in course[3]])
                data = '\n'.join(datatypes)
            elif args.format == 'fit':
                fit = FIT.FITCourse(self.gps, course)
                fit_file = fit.build()
                data = fit_file.to_bytes()
            else:
                sys.exit(f"Output format {args.format} is not supported")
            if args.filename == sys.stdout:
                _print(data)
            else:
                single_modulo = '(?<!%)%(?!%)'  # match a single % character
                if os.path.isdir(args.filename):
                    # No filename is given, so use the course name by default
                    stem = course[0].get_course_name()
                    if args.format == 'fit':
                        suffix = '.fit'
                    elif args.format == 'txt' or args.format == 'garmin':
                        suffix = '.txt'
                    else:
                        sys.exit(f"Output format {args.format} is not supported")
                    filename = stem + suffix
                    path = os.path.join(args.filename, filename)
                elif re.search(single_modulo, args.filename) is not None:
                    # filename is a formatting string
                    path = str(args.filename % idx)
                else:
                    # filename doesn't contain a single % and therefore isn't a pattern
                    path = args.filename
                    if len(result) > 1:
                        stem = pathlib.Path(path).stem
                        suffix = pathlib.Path(path).suffix
                        path = f"{stem}-{idx}{suffix}"
                mod_logger.log.info(f"Saving {path}")
                _write(pathlib.Path(path), data)

    def get_fitness_user_profile(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                fitness_user_profile = self.gps.get_fitness_user_profile(callback=progress_bar.update_to)
        else:
            fitness_user_profile = self.gps.get_fitness_user_profile()
        if args.format == 'txt':
            args.filename.write(f"{str(fitness_user_profile)}\n")
        elif args.format == 'garmin':
            args.filename.write(f"{repr(fitness_user_profile)}\n")
        else:
            sys.exit(f"Output format {args.format} is not supported")

    def get_activities(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                datatypes = self.gps.get_runs(callback=progress_bar.update_to)
        else:
            datatypes = self.gps.get_runs()
        runs = []
        laps = []
        tracks = []
        # First, separate the datatypes by type
        for datatype in datatypes:
            if isinstance(datatype, mod_datatype.Run):
                runs.append(datatype)
            elif isinstance(datatype, mod_datatype.Lap):
                laps.append(datatype)
                # Track headers and associated points are grouped
            elif isinstance(datatype, mod_datatype.TrkHdr):
                tracks.append([datatype])
            elif isinstance(datatype, mod_datatype.TrkPoint):
                tracks[-1].append(datatype)
        # Second, gather the datatypes per run
        result = []
        for idx, run in enumerate(runs):
            mod_logger.log.info(f"Adding run {idx}")
            lap_indices = range(run.first_lap_index, run.last_lap_index + 1)
            track_index = run.track_index
            run_laps = [lap for lap in laps if lap.index in lap_indices]
            for track in tracks:
                if track[0].index == track_index:
                    run_track = track
                    break
            result.append([run, run_laps, run_track])
        # Third, aggregate multisport runs
        activities = []
        multisport_session = False
        for run in result:
            multisport = run[0].get_multisport()
            if multisport == 'no':
                activities.append([run])
            elif multisport == 'yes' and multisport_session is False:
                activities.append([run])
                multisport_session = True
            elif multisport == 'yes' and multisport_session is True:
                activities[-1].append(run)
            elif multisport == 'yesAndLastInGroup':
                activities[-1].append(run)
                multisport_session = False
            else:
                mod_logger.log.warning(f"Unknown multisport value {multisport}. Ignoring...")
        if args.format == 'fit':
            for idx, activity in enumerate(activities):
                fit = FIT.FITActivity(self.gps, activity)
                fit_file = fit.build()
                data = fit_file.to_bytes()
                if args.filename == sys.stdout:
                    _print(data)
                else:
                    single_modulo = '(?<!%)%(?!%)'  # match a single % character
                    if os.path.isdir(args.filename):
                        # No filename is given, so use the start time by default
                        first_session = activity[0]
                        track = first_session[2]
                        stem = track[1].get_datetime().astimezone().isoformat()
                        suffix = '.fit'
                        filename = stem + suffix
                        path = os.path.join(args.filename, filename)
                    elif re.search(single_modulo, args.filename) is not None:
                        # filename is a formatting string
                        path = str(args.filename % idx)
                    else:
                        # filename doesn't contain a single % and therefore isn't a pattern
                        path = args.filename
                        if len(activities) > 1:
                            stem = pathlib.Path(path).stem
                            suffix = pathlib.Path(path).suffix
                            path = f"{stem}-{idx}{suffix}"
                    mod_logger.log.info(f"Saving {path}")
                    _write(pathlib.Path(path), data)
        else:
            sys.exit(f"Output format {args.format} is not supported")

    def get_map(self, args):
        try:
            if args.progress:
                with ProgressBar() as progress_bar:
                    data = self.gps.get_map(callback=progress_bar.update_to)
            else:
                data = self.gps.get_map()
            if data is None:
                mod_logger.log.warning("Map not found")
            else:
                with open(args.filename, 'wb') as f:
                    f.write(data)
        except mod_error.GarminError as e:
            sys.exit(f"{e}")

    def put_map(self, args):
        try:
            with open(args.filename, 'rb') as f:
                if args.progress:
                    with ProgressBar(unit='B', unit_scale=True, unit_divisor=1024, miniters=1) as progress_bar:
                        self.gps.put_map(f, callback=progress_bar.update_to)
                else:
                    self.gps.put_map(f)
        except mod_error.GarminError as e:
            sys.exit(f"{e}")

    def del_map(self, args):
        try:
            self.gps.del_map()
        except mod_error.GarminError as e:
            sys.exit(f"{e}")

    def get_screenshot(self, args):
        mod_logger.log.info(f"Downloading screenshot")
        if args.progress:
            with ProgressBar() as progress_bar:
                bmp = self.gps.get_screenshot(callback=progress_bar.update_to)
        else:
            bmp = self.gps.get_screenshot()
        mod_logger.log.info(f"Received BMP image of {bmp.DIB_w}x{bmp.DIB_h} pixels and {bmp.DIB_depth} bpp")
        if args.filename is None:
            if args.format is None:
                # No format is given, so use the BMP format by default
                mod_logger.log.info(f"Using the BMP format")
                filename = "Screenshot.bmp"
            else:
                # Determine the filename extension
                mod_logger.log.debug(f"Supported formats: {*Image.registered_extensions().values(), }")
                mod_logger.log.info(f"Trying to find an extension matching the {args.format.upper()} format")
                extensions = [ extension for (extension, format) in Image.registered_extensions().items() if format == args.format.upper() ]
                if len(extensions) == 0:
                    sys.exit(f"Image format {args.format.upper()} is not supported")
                elif len(extensions) == 1:
                    mod_logger.log.info(f"Found extension {extensions[0]}")
                    filename = "Screenshot" + extensions[0]
                elif len(extensions) > 1:
                    mod_logger.log.info(f"Found extensions {*extensions, }")
                    # If a format has multiple extensions, prefer the
                    # extension with the same name as the format.
                    preferred_extension = [ extension for extension in extensions if extension == '.' + args.format.lower() ]
                    if preferred_extension:
                        mod_logger.log.info(f"Prefer extension {preferred_extension[0]}")
                        filename = "Screenshot" + preferred_extension[0]
                    else:
                        sys.exit("The extension could not be determined")
        else:
            filename = args.filename
        if args.format is not None and not path.endswith(args.format.lower()):
            mod_logger.log.warning(f"Override format by saving {path} as {args.format.upper()}")
        mod_logger.log.info(f"Saving {path}")
        if args.format == 'bmp' or path.endswith('bmp'):
            # BMP supports images of 1/2/4/8/24-bit color depth
            bmp.save(path)
        else:
            image = bmp_to_pil(bmp)
            image.save(path, format=args.format)

    def get_image_types(self, args):
        image_types = self.gps.get_image_types()
        info = "Image types\n"
        info += "===========\n"
        args.filename.write(info)
        print(tabulate(image_types, headers='keys', tablefmt='plain'))

    def get_image_list(self, args):
        image_list = self.gps.get_image_list()
        info = "Image list\n"
        info += "===========\n"
        args.filename.write(info)
        print(tabulate(image_list, headers='keys', tablefmt='plain'))

    def get_image(self, args):
        image_list = self.gps.get_image_list()
        if args.index is None:
            indices = [ image['idx'] for image in image_list ]
            mod_logger.log.info("Download all images")
        else:
            indices = args.index
            mod_logger.log.info(f"Download image {*[idx for idx in indices],}")
        for idx in indices:
            basename = image_list[idx].get('name')
            mod_logger.log.info(f"Downloading {basename}")
            if args.progress:
                with ProgressBar() as progress_bar:
                    bmp = self.gps.get_image(idx, callback=progress_bar.update_to)
            else:
                bmp = self.gps.get_image(idx)
            mod_logger.log.info(f"Received BMP image of {bmp.DIB_w}x{bmp.DIB_h} pixels and {bmp.DIB_depth} bpp")
            single_modulo = '(?<!%)%(?!%)'  # match a single % character
            # Determine filename
            if args.filename is None or os.path.isdir(args.filename):
                # No filename is given, so use the basename by default
                if args.format is None:
                    # No format is given, so use the BMP format by default
                    mod_logger.log.info(f"Using the BMP format")
                    filename = basename + '.bmp'
                else:
                    # Determine the filename extension
                    mod_logger.log.debug(f"Supported formats: {*Image.registered_extensions().values(), }")
                    mod_logger.log.info(f"Trying to find an extension matching the {args.format.upper()} format")
                    extensions = [ extension for (extension, format) in Image.registered_extensions().items() if format == args.format.upper() ]
                    if len(extensions) == 0:
                        sys.exit(f"Image format {args.format.upper()} is not supported")
                    elif len(extensions) == 1:
                        mod_logger.log.info(f"Found extension {extensions[0]}")
                        filename = basename + extensions[0]
                    elif len(extensions) > 1:
                        mod_logger.log.info(f"Found extensions {*extensions, }")
                        # If a format has multiple extensions, prefer the
                        # extension with the same name as the format.
                        preferred_extension = [ extension for extension in extensions if extension == '.' + args.format.lower() ]
                        if preferred_extension:
                            mod_logger.log.info(f"Prefer extension {preferred_extension[0]}")
                            filename = basename + preferred_extension[0]
                        else:
                            sys.exit("The extension could not be determined")
                if args.filename is None:
                    path = filename
                else:
                    path = os.path.join(args.filename, filename)
            elif re.search(single_modulo, args.filename) is not None:
                # filename is a formatting string
                path = str(args.filename % idx)
            else:
                # filename doesn't contain a single % and therefore isn't a pattern
                path = args.filename
                if len(indices) > 1:
                    sys.exit(f"Cannot download {len(indices)} files to 1 filename")
            if args.format is not None and not path.endswith(args.format.lower()):
                mod_logger.log.warning(f"Override format by saving {path} as {args.format.upper()}")
            mod_logger.log.info(f"Saving {path}")
            if args.format == 'bmp' or path.endswith('bmp'):
                # BMP supports images of 1/2/4/8/24-bit color depth
                bmp.save(path)
            else:
                image = bmp_to_pil(bmp)
                image.save(path, format=args.format)

    def put_image(self, args):
        files = args.filename
        image_list = self.gps.get_image_list()
        if args.index is None:
            indices = [ image['idx'] for image in image_list if image['writable'] is True ]
        else:
            indices = args.index
        if len(files) != len(indices):
            sys.exit(f"Cannot upload {len(files)} files to {len(indices)} indices")
        for idx, filename in zip(indices, files):
            basename = image_list[idx].get('name')
            mod_logger.log.info(f"{image_list[idx]['writable']}")
            if not image_list[idx]['writable']:
                sys.exit(f"Image {basename} with index {idx} is not writable")
            # If the file is a BMP with the correct color depth, dimensions, and
            # color table it can be uploaded as is
            try:
                mod_logger.log.info(f"Trying to load {filename} image as a BMP image")
                bmp = MicroBMP().load(filename)
                props = self.gps.image_transfer.get_image_properties(idx)
                bpp = props.bpp
                width = props.width
                height = props.height
                colors_used = props.get_colors_used()
                if bpp != bmp.DIB_depth:
                    raise Exception(f"Image has wrong color depth: expected {bpp} bpp, got {bmp.DIB_depth} bpp")
                if width != bmp.DIB_w or height != bmp.DIB_h:
                    raise Exception(f"Image has wrong dimensions: expected {width}x{height} pixels, got {bmp.DIB_w}x{bmp.DIB_h} pixels")
                # Images with a color depth of 1, 2, 4, or 8 bpp have a color table
                if bpp <= 8:
                    image_id = self.gps.image_transfer.get_image_id(idx)
                    color_table = self.gps.image_transfer.get_color_table(image_id)
                    palette = color_table.get_palette()[:colors_used]
                    if bmp.palette != palette:
                        raise Exception("Image has the wrong color palette")
            # If the file is not a BMP image or it has the wrong attributes, it
            # has to be converted before uploading
            except Exception as e:
                mod_logger.log.info(e)
                try:
                    mod_logger.log.info(f"Trying to load {filename} image as a PIL image")
                    image = Image.open(filename)
                    # Convert PIL image to BMP
                    image_id = self.gps.image_transfer.get_image_id(idx)
                    # PIL images with the modes RGBA, LA, and PA have an alpha
                    # channel. Garmin images use magenta (255, 0, 255) as a transparency
                    # color, so it doesn't display.
                    if image.mode in ('RGBA', 'LA', 'PA'):
                        transparency = props.get_color().get_rgb()
                        mod_logger.log.info(f"Replacing the alpha channel with the transparency color {transparency}")
                        # Create a mask with the transparent pixels converted to black
                        alpha = image.getchannel('A')
                        mask = alpha.convert(mode='1')
                        # Create a background image with the transparency color
                        background = Image.new('RGB', image.size, transparency)
                        # Paste the original image onto  the background image, using the
                        # transparency mask
                        background.paste(image, mask=mask)
                        # Now we have a RGB image the alpha channel of which is replaced
                        # by the transparency color
                        image = background
                    if image.width!= width or image.height != height:
                        mod_logger.log.info(f"Resizing image to {width}x{height} pixels")
                        image = image.resize((width, height))
                    mod_logger.log.info(f"Creating BMP image of {width}x{height} pixels and {bpp} bpp")
                    bmp = MicroBMP(width, height, bpp)
                    # Images with a color depth of 1, 2, 4, or 8 bpp have a palette
                    if bpp in (1, 2, 4, 8):
                        if image.mode != 'P':
                            mod_logger.log.info("Converting image to palette mode (P)")
                            image = image.convert(mode='P')
                        # The palette must be the same as Garmin's
                        color_table = self.gps.image_transfer.get_color_table(image_id)
                        palette = color_table.get_palette()[:colors_used]
                        # The BMP palette is a list of bytearray, and the PIL palette is a byte object
                        if image.palette.palette != b''.join(palette):
                            mod_logger.log.info(f"Quantizing image to the received color palette")
                            image = image.convert(mode='RGB')
                            new_image = Image.new('P', (width, height))
                            new_palette = ImagePalette.ImagePalette(palette=b''.join(palette))
                            new_image.putpalette(new_palette)
                            image = image.quantize(colors=colors_used, palette=new_image)
                        bmp.palette = palette
                        pixel_data = image.tobytes()
                        if bpp != 8:
                            mod_logger.log.info(f"Converting 8 bpp image to {bpp} bpp color depth")
                            pixel_values = to_pixel_values(pixel_data, 8)
                            pixel_data = to_pixel_data(pixel_values, bpp)
                        bmp.parray = pixel_data
                    # Images with a color depth of 24 bpp
                    elif bpp == 24:
                        if image.mode != 'RGB':
                            mod_logger.log.info("Converting image to true color mode (RGB)")
                            image = image.convert(mode='RGB')
                        pixel_data = image.tobytes()
                        bmp.parray = pixel_data
                    else:
                        sys.exit(f"Images of {bpp} bpp are not supported")
                except UnidentifiedImageError as e:
                    mod_logger.log.info(e)
                    sys.exit(f"Unknown image file format")
            mod_logger.log.info(f"Uploading {basename}")
            if args.progress:
                with ProgressBar() as progress_bar:
                    self.gps.put_image(idx, bmp, callback=progress_bar.update_to)
            else:
                self.gps.put_image(idx, bmp)

parser = argparse.ArgumentParser(prog='pygarmin',
                                 description=
"""Command line application to communicate with a Garmin GPS device.

Pygarmin can retrieve information from the device, such as the product
description including the unit ID, the supported protocols, memory properties,
and information on the installed maps. supports bi-directional transfer of
waypoints, routes, track logs, proximity waypoints, maps and images such as
custom waypoint icons. It is able to receive laps, runs, satellite almanac,
current time, current position, and screenshots. It can continuously receive
real-time position, velocity, and time (PVT).

The port is specified with the -p PORT option. To communicate with a Garmin GPS
serially, use the name of that serial port such as /dev/ttyUSB0, /dev/cu.serial,
or COM1. To communicate via USB use usb: as the port on all OSes.
""")
parser.add_argument('-v',
                    '--verbosity',
                    action='count',
                    default=0,
                    help="Increase output verbosity")
parser.add_argument('-D',
                    '--debug',
                    action='store_const',
                    const=3,
                    default=0,
                    help="Enable debugging")
parser.add_argument('--version',
                    action='store_true',
                    help="Dump version and exit")
parser.add_argument('--progress',
                    action=argparse.BooleanOptionalAction,
                    default=True,
                    help="Show progress bar")
parser.add_argument('-p',
                    '--port',
                    default='usb:',
                    help="Set the device name (default: usb:)")
subparsers = parser.add_subparsers(help="Command help")
info = subparsers.add_parser('info', help="Return product description")
info.set_defaults(command='info')
info.add_argument('filename',
                  nargs='?',
                  type=argparse.FileType(mode='w'),
                  default=sys.stdout,
                  # Write output to <file> instead of stdout.
                  help="Set output file")
protocols = subparsers.add_parser('protocols', help="Return protocol capabilities")
protocols.set_defaults(command='protocols')
protocols.add_argument('filename',
                       nargs='?',
                       type=argparse.FileType(mode='w'),
                       default=sys.stdout,
                       help="Set output file")
memory = subparsers.add_parser('memory', help="Return memory info")
memory.set_defaults(command='memory')
memory.add_argument('filename',
                    nargs='?',
                    type=argparse.FileType(mode='w'),
                    default=sys.stdout,
                    help="Set output file")
map_info = subparsers.add_parser('map', help="Return map info")
map_info.set_defaults(command='map_info')
map_info.add_argument('filename',
                 nargs='?',
                 type=argparse.FileType(mode='w'),
                 default=sys.stdout,
                 help="Set output file")
get_waypoints = subparsers.add_parser('get-waypoints', help="Download waypoints")
get_waypoints.set_defaults(command='get_waypoints')
get_waypoints.add_argument('-t',
                           '--format',
                           choices=['txt', 'garmin', 'json', 'gpx'],
                           default='garmin',
                           help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``json`` returns a JSON string of the datatypes. ``gpx`` returns a string in GPS Exchange Format (GPX).")
get_waypoints.add_argument('filename',
                           nargs='?',
                           type=argparse.FileType(mode='w'),
                           default=sys.stdout,
                           help="Set output file")
put_waypoints = subparsers.add_parser('put-waypoints', help="Upload waypoints")
put_waypoints.set_defaults(command='put_waypoints')
put_waypoints.add_argument('-t',
                           '--format',
                           choices=['garmin', 'json', 'gpx'],
                           default='garmin',
                           help="Set input format. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``json`` returns a JSON string of the datatypes. ``gpx`` returns a string in GPS Exchange Format (GPX).")
put_waypoints.add_argument('filename',
                           nargs='?',
                           type=argparse.FileType(mode='r'),
                           default=sys.stdin,
                           help="Set input file")
get_routes = subparsers.add_parser('get-routes', help="Download routes")
get_routes.set_defaults(command='get_routes')
get_routes.add_argument('-t',
                        '--format',
                        choices=['txt', 'garmin', 'json', 'gpx'],
                        default='garmin',
                        help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``json`` returns a JSON string of the datatypes. ``gpx`` returns a string in GPS Exchange Format (GPX).")
get_routes.add_argument('filename',
                        nargs='?',
                        type=argparse.FileType(mode='w'),
                        default=sys.stdout,
                        help="Set output file")
put_routes = subparsers.add_parser('put-routes', help="Upload routes")
put_routes.set_defaults(command='put_routes')
put_routes.add_argument('-t',
                        '--format',
                        choices=['garmin', 'json', 'gpx'],
                        default='garmin',
                        help="Set input format. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``json`` returns a JSON string of the datatypes. ``gpx`` returns a string in GPS Exchange Format (GPX).")
put_routes.add_argument('filename',
                        nargs='?',
                        type=argparse.FileType(mode='r'),
                        default=sys.stdin,
                        help="Set input file")
get_tracks = subparsers.add_parser('get-tracks', help="Download tracks")
get_tracks.set_defaults(command='get_tracks')
get_tracks.add_argument('-t',
                        '--format',
                        choices=['txt', 'garmin', 'json', 'gpx'],
                        default='garmin',
                        help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``json`` returns a JSON string of the datatypes. ``gpx`` returns a string in GPS Exchange Format (GPX).")
get_tracks.add_argument('filename',
                        nargs='?',
                        type=argparse.FileType(mode='w'),
                        default=sys.stdout,
                        help="Set output file")
put_tracks = subparsers.add_parser('put-tracks', help="Upload tracks")
put_tracks.set_defaults(command='put_tracks')
put_tracks.add_argument('-t',
                        '--format',
                        choices=['garmin', 'json', 'gpx'],
                        default='garmin',
                        help="Set input format. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``json`` returns a JSON string of the datatypes. ``gpx`` returns a string in GPS Exchange Format (GPX).")
put_tracks.add_argument('filename',
                        nargs='?',
                        type=argparse.FileType(mode='r'),
                        default=sys.stdin,
                        help="Set input file")
get_proximities = subparsers.add_parser('get-proximities', help="Download proximities")
get_proximities.set_defaults(command='get_proximities')
get_proximities.add_argument('-t',
                             '--format',
                             choices=['txt', 'garmin', 'json', 'gpx'],
                             default='garmin',
                             help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``json`` returns a JSON string of the datatypes. ``gpx`` returns a string in GPS Exchange Format (GPX).")
get_proximities.add_argument('filename',
                             nargs='?',
                             type=argparse.FileType(mode='w'),
                             default=sys.stdout,
                             help="Set output file")
put_proximities = subparsers.add_parser('put-proximities', help="Upload proximities")
put_proximities.set_defaults(command='put_proximities')
put_proximities.add_argument('-t',
                             '--format',
                             choices=['garmin', 'json', 'gpx'],
                             default='garmin',
                             help="Set input format. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``json`` returns a JSON string of the datatypes. ``gpx`` returns a string in GPS Exchange Format (GPX).")
put_proximities.add_argument('filename',
                             nargs='?',
                             type=argparse.FileType(mode='r'),
                             default=sys.stdin,
                             help="Set input file")
get_almanac = subparsers.add_parser('get-almanac', help="Download almanac")
get_almanac.set_defaults(command='get_almanac')
get_almanac.add_argument('-t',
                         '--format',
                         choices=['txt', 'garmin', 'json'],
                         default='garmin',
                         help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``json`` returns a JSON string of the datatypes.")
get_almanac.add_argument('filename',
                         nargs='?',
                         type=argparse.FileType(mode='w'),
                         default=sys.stdout,
                         help="Set output file")
get_time = subparsers.add_parser('get-time', help="Download current date and time")
get_time.set_defaults(command='get_time')
get_time.add_argument('-t',
                      '--format',
                      choices=['txt', 'garmin', 'json'],
                      default='garmin',
                      help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``json`` returns a JSON string of the datatypes.")
get_time.add_argument('filename',
                      nargs='?',
                      type=argparse.FileType(mode='w'),
                      default=sys.stdout,
                      help="Set output file")
get_position = subparsers.add_parser('get-position', help="Download current position")
get_position.set_defaults(command='get_position')
get_position.add_argument('-t',
                          '--format',
                          choices=['txt', 'garmin', 'json'],
                          default='garmin',
                          help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``json`` returns a JSON string of the datatypes.")
get_position.add_argument('filename',
                          nargs='?',
                          type=argparse.FileType(mode='w'),
                          default=sys.stdout,
                          help="Set output file")
pvt = subparsers.add_parser('pvt', help="Download pvt")
pvt.set_defaults(command='pvt')
pvt.add_argument('-t',
                 '--format',
                 choices=['txt', 'garmin', 'gpsd'],
                 default='garmin',
                 help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``gpsd`` returns a GPSD JSON object.")
pvt.add_argument('filename',
                 nargs='?',
                 type=argparse.FileType(mode='w'),
                 default=sys.stdout,
                 help="Set output file")
get_laps = subparsers.add_parser('get-laps', help="Download laps")
get_laps.set_defaults(command='get_laps')
get_laps.add_argument('-t',
                      '--format',
                      choices=['txt', 'garmin'],
                      default='garmin',
                      help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype.")
get_laps.add_argument('filename',
                      nargs='?',
                      type=argparse.FileType(mode='w'),
                      default=sys.stdout,
                      help="Set output file")
get_runs = subparsers.add_parser('get-runs', help="Download runs")
get_runs.set_defaults(command='get_runs')
get_runs.add_argument('-t',
                      '--format',
                      choices=['txt', 'garmin', 'fit'],
                      default='garmin',
                      help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``fit`` returns the binary FIT file format.")
get_runs.add_argument('filename',
                      nargs='?',
                      default=sys.stdout,
                      help="Filename or directory to save runs (default is stdout). A filename pattern can contain %%d (or any formatting string using the %% operator), since %%d is replaced by the image index. Example: run%%03d.fit. By default, runs are written to filenames named by the start date and time.")
get_workouts = subparsers.add_parser('get-workouts', help="Download workouts")
get_workouts.set_defaults(command='get_workouts')
get_workouts.add_argument('-t',
                          '--format',
                          choices=['txt', 'garmin', 'fit'],
                          default='garmin',
                          help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``fit`` returns the binary FIT file format.")
get_workouts.add_argument('filename',
                          nargs='?',
                          default=sys.stdout,
                          help="Filename or directory to save workouts (default is stdout). A filename pattern can contain %%d (or any formatting string using the %% operator), since %%d is replaced by the image index. Example: workout%%03d.fit. By default, the workout name is used as filename.")
get_courses = subparsers.add_parser('get-courses', help="Download courses")
get_courses.set_defaults(command='get_courses')
get_courses.add_argument('-t',
                         '--format',
                         choices=['txt', 'garmin', 'fit'],
                         default='garmin',
                         help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``fit`` returns the binary FIT file format.")
get_courses.add_argument('filename',
                         nargs='?',
                         default=sys.stdout,
                         help="Filename or directory to save courses (default is stdout). A filename pattern can contain %%d (or any formatting string using the %% operator), since %%d is replaced by the image index. Example: course%%03d.fit. By default, the course name is used as filename.")
get_fitness_user_profile = subparsers.add_parser('get-fitness-user-profile', help="Download fitness user profile")
get_fitness_user_profile.set_defaults(command='get_fitness_user_profile')
get_fitness_user_profile.add_argument('-t',
                                      '--format',
                                      choices=['txt', 'garmin'],
                                      default='garmin',
                                      help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype.")
get_fitness_user_profile.add_argument('filename',
                                      nargs='?',
                                      type=argparse.FileType(mode='w'),
                                      default=sys.stdout,
                                      help="Set output file")
get_activities = subparsers.add_parser('get-activities', help="Download activities. Activities are runs that are grouped by multisport session.")
get_activities.set_defaults(command='get_activities')
get_activities.add_argument('-t',
                            '--format',
                            choices=['fit'],
                            default='fit',
                            help="Set output format. ``txt`` returns a human readable string of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``fit`` returns the binary FIT file format.")
get_activities.add_argument('filename',
                            nargs='?',
                            default=sys.stdout,
                            help="Filename or directory to save activities (default is stdout). A filename pattern can contain %%d (or any formatting string using the %% operator), since %%d is replaced by the image index. Example: activity%%03d.fit. By default, activities are written to filenames named by the start date and time.")
get_map = subparsers.add_parser('get-map', help="Download map")
get_map.set_defaults(command='get_map')
get_map.add_argument('filename',
                     nargs='?',
                     default='gmapsupp.img',
                     help="Set output file")
put_map = subparsers.add_parser('put-map', help="Upload map")
put_map.set_defaults(command='put_map')
put_map.add_argument('filename',
                     help="Set input file")
del_map = subparsers.add_parser('del-map', help="Delete map")
del_map.set_defaults(command='del_map')
get_screenshot = subparsers.add_parser('get-screenshot', help="Capture screenshot")
get_screenshot.set_defaults(command='get_screenshot')
get_screenshot.add_argument('-t',
                            '--format',
                            help="Set image file format")
get_screenshot.add_argument('filename',
                            nargs='?',
                            help="Set image filename or directory")
get_image_types = subparsers.add_parser('get-image-types', help="List image types")
get_image_types.add_argument('filename',
                             nargs='?',
                             type=argparse.FileType(mode='w'),
                             default=sys.stdout,
                             help="Set output file")
get_image_types.set_defaults(command='get_image_types')
get_image_list = subparsers.add_parser('get-image-list', help="List images")
get_image_list.add_argument('filename',
                             nargs='?',
                             type=argparse.FileType(mode='w'),
                             default=sys.stdout,
                             help="Set output file")
get_image_list.set_defaults(command='get_image_list')
get_image = subparsers.add_parser('get-image', help="Download image")
get_image.add_argument('-t',
                       '--format',
                       help="Set image file format")
get_image.add_argument('-i',
                       '--index',
                       type=int,
                       nargs='*',
                       help="Indices of the image list to get")
get_image.add_argument('filename',
                       nargs='?',
                       help="Filename or directory to save images. A filename pattern can contain %%d (or any formatting string using the %% operator), since %%d is replaced by the image index. Example: waypoint%%03d.png")
get_image.set_defaults(command='get_image')
put_image = subparsers.add_parser('put-image', help="Upload image")
put_image.add_argument('-i',
                       '--index',
                       type=int,
                       nargs='*',
                       help="Indices of the image list to put")
put_image.add_argument('filename',
                       nargs='+',
                       help="Set input file")
put_image.set_defaults(command='put_image')

def main():
    args = parser.parse_args()
    logging_level = logging_levels.get(max(args.verbosity, args.debug))
    mod_logger.log.setLevel(logging_level)
    mod_logger.log.info(f"Version {__version__}")
    if hasattr(args, 'command'):
        app = Pygarmin(args.port)
        command = getattr(app, args.command)
        command(args)
    elif args.version:
        print(f"pygarmin version {__version__}")
    else:
        parser.print_usage()

if __name__ == '__main__':
    main()
