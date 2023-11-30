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
__version__ = '0.1'

import argparse
import gpxpy
import json
import logging
import os
import PIL.Image
import re
import signal
import sys
from tabulate import tabulate
from tqdm import tqdm
import xml.etree.ElementTree as ET
import io
import garmin

logging_levels = {
    0: logging.NOTSET,
    1: logging.WARNING,
    2: logging.INFO,
    3: logging.DEBUG,
}

log = logging.getLogger('garmin')
log.addHandler(logging.StreamHandler())


class ProgressBar(tqdm):

    def update_to(self, object, current, total):
        self.total = total
        self.update(current - self.n)


class GPX:
    _display_mode = {
        'dspl_smbl_none': "SymbolOnly",
        'dspl_smbl_only': "SymbolOnly",
        'dspl_smbl_name': "SymbolAndName",
        'dspl_smbl_cmnt': "SymbolAndDescription",
    }

    _display_color = {
        'clr_default': None,
        'clr_default_color': None,
        'clr_black': 'Black',
        'clr_dark_red': 'DarkRed',
        'clr_dark_green': 'DarkGreen',
        'clr_dark_yellow': 'DarkYellow',
        'clr_dark_blue': 'DarkBlue',
        'clr_dark_magenta': 'DarkMagenta',
        'clr_dark_cyan': 'DarkCyan',
        'clr_light_gray': 'LightGray',
        'clr_dark_gray': 'DarkGray',
        'clr_red': 'Red',
        'clr_green': 'Green',
        'clr_yellow': 'Yellow',
        'clr_blue': 'Blue',
        'clr_magenta': 'Magenta',
        'clr_cyan': 'Cyan',
        'clr_white': 'White',
        'clr_transparent': 'Transparent',
    }

    # The list of garmin waypoint symbols is retrieved from the printable
    # characters in the Garmin MapSource binary version 6.16.3
    _symbol = {
        'smbl_dot': 'Dot, White',
        'smbl_house': 'Residence',
        'smbl_gas': 'Gas Station',
        'smbl_car': 'Car',
        'smbl_fish': 'Fishing Area',
        'smbl_boat': 'Boat Ramp',
        'smbl_anchor': 'Anchor',
        'smbl_wreck': 'Shipwreck',
        'smbl_exit': 'Exit',
        'smbl_skull': 'Skull and Crossbones',
        'smbl_flag': 'Flag',
        'smbl_camp': 'Campground',
        'smbl_circle_x': 'Circle with X',
        'smbl_deer': 'Hunting Area',
        'smbl_1st_aid': 'Medical Facility',
        'smbl_back_track': 'TracBack Point',
        'sym_anchor': 'Anchor',
        'sym_bell': 'Bell',
        'sym_diamond_grn': 'Diamond, Green',
        'sym_diamond_red': 'Diamond, Red',
        'sym_dive1': 'Diver Down Flag 1',
        'sym_dive2': 'Diver Down Flag 2',
        'sym_dollar': 'Bank',
        'sym_fish': 'Fishing Area',
        'sym_fuel': 'Gas Station',
        'sym_horn': 'Horn',
        'sym_house': 'Residence',
        'sym_knife': 'Restaurant',
        'sym_light': 'Light',
        'sym_mug': 'Bar',
        'sym_skull': 'Skull and Crossbones',
        'sym_square_grn': 'Square, Green',
        'sym_square_red': 'Square, Red',
        'sym_wbuoy': 'Buoy, White',
        'sym_wpt_dot': 'Waypoint',
        'sym_wreck': 'Shipwreck',
        'sym_mob': 'Man Overboard',
        'sym_buoy_ambr': 'Navaid, Amber',
        'sym_buoy_blck': 'Navaid, Black',
        'sym_buoy_blue': 'Navaid, Blue',
        'sym_buoy_grn': 'Navaid, Green',
        'sym_buoy_grn_red': 'Navaid, Green/Red',
        'sym_buoy_grn_wht': 'Navaid, Green/White',
        'sym_buoy_orng': 'Navaid, Orange',
        'sym_buoy_red': 'Navaid, Red',
        'sym_buoy_red_grn': 'Navaid, Red/Green',
        'sym_buoy_red_wht': 'Navaid, Red/White',
        'sym_buoy_violet': 'Navaid, Violet',
        'sym_buoy_wht': 'Navaid, White',
        'sym_buoy_wht_grn': 'Navaid, White/Green',
        'sym_buoy_wht_red': 'Navaid, White/Red',
        'sym_dot': 'Dot, White',
        'sym_rbcn': 'Radio Beacon',
        'sym_boat_ramp': 'Boat Ramp',
        'sym_camp': 'Campground',
        'sym_restrooms': 'Restroom',
        'sym_showers': 'Shower',
        'sym_drinking_wtr': 'Drinking Water',
        'sym_phone': 'Telephone',
        'sym_1st_aid': 'Medical Facility',
        'sym_info': 'Information',
        'sym_parking': 'Parking Area',
        'sym_park': 'Park',
        'sym_picnic': 'Picnic Area',
        'sym_scenic': 'Scenic Area',
        'sym_skiing': 'Skiing Area',
        'sym_swimming': 'Swimming Area',
        'sym_dam': 'Dam',
        'sym_controlled': 'Controlled Area',
        'sym_danger': 'Danger Area',
        'sym_restricted': 'Restricted Area',
        'sym_ball': 'Ball Park',
        'sym_car': 'Car',
        'sym_deer': 'Hunting Area',
        'sym_shpng_cart': 'Shopping Center',
        'sym_lodging': 'Lodging',
        'sym_mine': 'Mine',
        'sym_trail_head': 'Trail Head',
        'sym_truck_stop': 'Truck Stop',
        'sym_user_exit': 'Exit',
        'sym_flag': 'Flag',
        'sym_circle_x': 'Circle with X',
        'sym_mi_mrkr': 'Mile Marker',
        'sym_trcbck': 'TracBack Point',
        'sym_golf': 'Golf Course',
        'sym_sml_cty': 'City (Small)',
        'sym_med_cty': 'City (Medium)',
        'sym_lrg_cty': 'City (Large)',
        'sym_cap_cty': 'City (Capitol)',
        'sym_amuse_pk': 'Amusement Park',
        'sym_bowling': 'Bowling',
        'sym_car_rental': 'Car Rental',
        'sym_car_repair': 'Car Repair',
        'sym_fastfood': 'Fast Food',
        'sym_fitness': 'Fitness Center',
        'sym_movie': 'Movie Theater',
        'sym_museum': 'Museum',
        'sym_pharmacy': 'Pharmacy',
        'sym_pizza': 'Pizza',
        'sym_post_ofc': 'Post Office',
        'sym_rv_park': 'RV Park',
        'sym_school': 'School',
        'sym_stadium': 'Stadium',
        'sym_store': 'Department Store',
        'sym_zoo': 'Zoo',
        'sym_gas_plus': 'Convenience Store',
        'sym_faces': 'Live Theater',
        'sym_weigh_sttn': 'Scales',
        'sym_toll_booth': 'Toll Booth',
        'sym_bridge': 'Bridge',
        'sym_building': 'Building',
        'sym_cemetery': 'Cemetery',
        'sym_church': 'Church',
        'sym_civil': 'Civil',
        'sym_crossing': 'Crossing',
        'sym_hist_town': 'Ghost Town',
        'sym_levee': 'Levee',
        'sym_military': 'Military',
        'sym_oil_field': 'Oil Field',
        'sym_tunnel': 'Tunnel',
        'sym_beach': 'Beach',
        'sym_forest': 'Forest',
        'sym_summit': 'Summit',
        'sym_airport': 'Airport',
        'sym_heliport': 'Heliport',
        'sym_private': 'Private Field',
        'sym_soft_fld': 'Soft Field',
        'sym_tall_tower': 'Tall Tower',
        'sym_short_tower': 'Short Tower',
        'sym_glider': 'Glider Area',
        'sym_ultralight': 'Ultralight Area',
        'sym_parachute': 'Parachute Area',
        'sym_seaplane': 'Seaplane Base',
        'sym_geocache': 'Geocache',
        'sym_geocache_fnd': 'Geocache Found',
        'sym_cntct_afro': 'Contact, Afro',
        'sym_cntct_alien': 'Contact, Alien',
        'sym_cntct_ball_cap': 'Contact, Ball Cap',
        'sym_cntct_big_ears': 'Contact, Big Ears',
        'sym_cntct_biker': 'Contact, Biker',
        'sym_cntct_bug': 'Contact, Bug',
        'sym_cntct_cat': 'Contact, Cat',
        'sym_cntct_dog': 'Contact, Dog',
        'sym_cntct_dreads': 'Contact, Dreadlocks',
        'sym_cntct_female1': 'Contact, Female1',
        'sym_cntct_female2': 'Contact, Female2',
        'sym_cntct_female3': 'Contact, Female3',
        'sym_cntct_goatee': 'Contact, Goatee',
        'sym_cntct_kung_fu': 'Contact, Kung Fu',
        'sym_cntct_pig': 'Contact, Pig',
        'sym_cntct_pirate': 'Contact, Pirate',
        'sym_cntct_ranger': 'Contact, Ranger',
        'sym_cntct_smiley': 'Contact, Smiley',
        'sym_cntct_spike': 'Contact, Spike',
        'sym_cntct_sumo': 'Contact, Sumo',
        'sym_cntct_blond_woman': 'Contact, Blonde',
        'sym_cntct_clown': 'Contact, Clown',
        'sym_cntct_glasses_boy': 'Contact, Glasses',
        'sym_cntct_panda': 'Contact, Panda',
        'sym_hydrant': 'Water Hydrant',
        'sym_flag_red': 'Flag, Red',
        'sym_flag_blue': 'Flag, Blue',
        'sym_flag_green': 'Flag, Green',
        'sym_pin_red': 'Pin, Red',
        'sym_pin_blue': 'Pin, Blue',
        'sym_pin_green': 'Pin, Green',
        'sym_block_red': 'Block, Red',
        'sym_block_blue': 'Block, Blue',
        'sym_block_green': 'Block, Green',
        'sym_bike_trail': 'Bike Trail',
        'sym_fhs_facility': 'Fishing Hot Spot Facility',
        'sym_badge': 'Police Station',
        'sym_snowski': 'Ski Resort',
        'sym_iceskate': 'Ice Skating',
        'sym_wrecker': 'Wrecker',
        'sym_anchor_prohib': 'Anchor Prohibited',
        'sym_beacon': 'Beacon',
        'sym_coast_guard': 'Coast Guard',
        'sym_reef': 'Reef',
        'sym_weedbed': 'Weed Bed',
        'sym_dropoff': 'Dropoff',
        'sym_dock': 'Dock',
        'sym_marina': 'Marina',
        'sym_bait_tackle': 'Bait and Tackle',
        'sym_stump': 'Stump',
        'sym_circle_red': 'Circle, Red',
        'sym_circle_green': 'Circle, Green',
        'sym_circle_blue': 'Circle, Blue',
        'sym_diamond_blue': 'Diamond, Blue',
        'sym_oval_red': 'Oval, Red',
        'sym_oval_green': 'Oval, Green',
        'sym_oval_blue': 'Oval, Blue',
        'sym_rect_red': 'Rectangle, Red',
        'sym_rect_green': 'Rectangle, Green',
        'sym_rect_blue': 'Rectangle, Blue',
        'sym_square_blue': 'Square, Blue',
        'sym_letter_a_red': 'Letter A, Red',
        'sym_letter_a_green': 'Letter A, Green',
        'sym_letter_a_blue': 'Letter A, Blue',
        'sym_letter_b_red': 'Letter B, Red',
        'sym_letter_b_green': 'Letter B, Green',
        'sym_letter_b_blue': 'Letter B, Blue',
        'sym_letter_c_red': 'Letter C, Red',
        'sym_letter_c_green': 'Letter C, Green',
        'sym_letter_c_blue': 'Letter C, Blue',
        'sym_letter_d_red': 'Letter D, Red',
        'sym_letter_d_green': 'Letter D, Green',
        'sym_letter_d_blue': 'Letter D, Blue',
        'sym_number_0_red': 'Number 0, Red',
        'sym_number_0_green': 'Number 0, Green',
        'sym_number_0_blue': 'Number 0, Blue',
        'sym_number_1_red': 'Number 1, Red',
        'sym_number_1_green': 'Number 1, Green',
        'sym_number_1_blue': 'Number 1, Blue',
        'sym_number_2_red': 'Number 2, Red',
        'sym_number_2_green': 'Number 2, Green',
        'sym_number_2_blue': 'Number 2, Blue',
        'sym_number_3_red': 'Number 3, Red',
        'sym_number_3_green': 'Number 3, Green',
        'sym_number_3_blue': 'Number 3, Blue',
        'sym_number_4_red': 'Number 4, Red',
        'sym_number_4_green': 'Number 4, Green',
        'sym_number_4_blue': 'Number 4, Blue',
        'sym_number_5_red': 'Number 5, Red',
        'sym_number_5_green': 'Number 5, Green',
        'sym_number_5_blue': 'Number 5, Blue',
        'sym_number_6_red': 'Number 6, Red',
        'sym_number_6_green': 'Number 6, Green',
        'sym_number_6_blue': 'Number 6, Blue',
        'sym_number_7_red': 'Number 7, Red',
        'sym_number_7_green': 'Number 7, Green',
        'sym_number_7_blue': 'Number 7, Blue',
        'sym_number_8_red': 'Number 8, Red',
        'sym_number_8_green': 'Number 8, Green',
        'sym_number_8_blue': 'Number 8, Blue',
        'sym_number_9_red': 'Number 9, Red',
        'sym_number_9_green': 'Number 9, Green',
        'sym_number_9_blue': 'Number 9, Blue',
        'sym_triangle_blue': 'Triangle, Blue',
        'sym_triangle_green': 'Triangle, Green',
        'sym_triangle_red': 'Triangle, Red',
        # The symbols below are mentioned in Garmin MapSource, but not in the specification
        # 'Multi-Cache'
        # 'Letterbox Cache',
        # 'Puzzle Cache',
        'sym_library': 'Library',
        'sym_bus': 'Ground Transportation',
        'sym_city_hall': 'City Hall',
        'sym_wine': 'Winery',
        'sym_atv': 'ATV',
        'sym_big_game': 'Big Game',
        'sym_blind': 'Blind',
        'sym_blood_trail': 'Blood Trail',
        'sym_cover': 'Cover',
        'sym_covey': 'Covey',
        'sym_food_source': 'Food Source',
        'sym_furbearer': 'Furbearer',
        'sym_lodge': 'Lodge',
        'sym_small_game': 'Small Game',
        'sym_tracks': 'Animal Tracks',
        'sym_treed_quarry': 'Treed Quarry',
        'sym_tree_stand': 'Tree Stand',
        'sym_truck': 'Truck',
        'sym_upland_game': 'Upland Game',
        'sym_waterfowl': 'Waterfowl',
        'sym_water_source': 'Water Source',
    }

    def __str__(self):
        return self.gpx.to_xml()


class GPXWaypoints(GPX):

    def __init__(self, waypoints):
        self.gpx = self.waypoints_to_gpx(waypoints)

    def waypoints_to_gpx(self, waypoints):
        gpx = gpxpy.gpx.GPX()
        gpx.name = 'Waypoints'
        gpx.description = 'Waypoints'
        gpxx = 'gpxx'
        nsmap = { gpxx: 'https://www8.garmin.com/xmlschemas/GpxExtensions/v3/GpxExtensionsv3.xsd' }
        gpx.nsmap = nsmap
        for point in waypoints:
            if isinstance(point, garmin.Wpt) and point.get_posn().is_valid():
                # Possible fields: ('posn', 'color', 'lnk_ident', 'city',
                # 'attr', 'facility', 'dspl_color', 'dst', 'dpth', 'cc', 'cmnt',
                # 'wpt_cat', 'alt', 'state', 'time', 'unused', 'cross_road',
                # 'addr', 'dtyp', 'dspl', 'temp', 'dist', 'subclass', 'ete',
                # 'wpt_class', 'ident', 'smbl', 'wpt_ident')
                latitude = point.get_posn().as_degrees().lat
                longitude = point.get_posn().as_degrees().lon
                name = point.ident.decode(encoding='latin_1')
                comment = point.cmnt.decode(encoding='latin_1')
                if point.get_dict().get('alt') is not None and point.is_valid_alt() is True:
                    elevation = point.alt
                else:
                    elevation = None
                if point.get_dict().get('time') is not None and point.is_valid_time() is True:
                    time = point.get_datetime()
                else:
                    time = None
                if point.get_dict().get('smbl') is not None:
                    smbl = point.get_smbl()
                    if self._symbol.get(smbl) is not None:
                        symbol = self._symbol.get(smbl)
                    else:
                        symbol = smbl
                else:
                    symbol = None
                gpx_point = gpxpy.gpx.GPXWaypoint(latitude=latitude,
                                                  longitude=longitude,
                                                  elevation=elevation,
                                                  name=name,
                                                  comment=comment,
                                                  symbol=symbol)
                waypoint_extension = ET.Element(f'{{{gpxx}}}WaypointExtension')
                # The 'dst' (D101, D102, D104, D107) and 'dist' (D108, D109,
                # D100) fields both contain the proximity distance in meters
                if point.get_dict().get('dst') is not None and point.is_valid_dst() is True:
                    proximity = ET.SubElement(waypoint_extension, f'{{{gpxx}}}Proximity')
                    proximity.text = str(point.dst)
                if point.get_dict().get('dist') is not None  and point.is_valid_dist() is True:
                    proximity = ET.SubElement(waypoint_extension, f'{{{gpxx}}}Proximity')
                    proximity.text = str(point.dist)
                if point.get_dict().get('temp') is not None and point.is_valid_temp() is True:
                    temperature = ET.SubElement(waypoint_extension, f'{{{gpxx}}}Temperature')
                    temperature.text = str(point.temp)
                if point.get_dict().get('dpth') is not None and point.is_valid_dpth() is True:
                    depth = ET.SubElement(waypoint_extension, f'{{{gpxx}}}Depth')
                    depth.text = str(point.dpth)
                if point.get_dict().get('dspl') is not None:
                    display_mode = ET.SubElement(waypoint_extension,f'{{{gpxx}}}DisplayMode')
                    dspl = point.get_dspl()
                    display_mode.text = _display_mode.get(dspl)
                if point.get_dict().get('wpt_cat') is not None and waypoint_categories is not None:
                    category_numbers = point.get_wpt_cat()
                    category_names = [ category.name.decode(encoding='latin_1') for category in waypoint_categories ]
                    category_members = [ category_names[number-1] for number in category_numbers ]
                    categories = ET.SubElement(waypoint_extension, f'{{{gpxx}}}Categories')
                    for category_member in category_members:
                        category = ET.SubElement(categories, f'{{{gpxx}}}Category')
                        category.text = category_member
                gpx_point.extensions.append(waypoint_extension)
                gpx.waypoints.append(gpx_point)
        return gpx


class GPXRoutes(GPX):

    def __init__(self, routes):
        self.gpx = self.routes_to_gpx(routes)

    def routes_to_gpx(self, routes):
        gpx = gpxpy.gpx.GPX()
        gpx.name = 'Routes'
        gpx.description = 'Routes'
        gpxx = 'gpxx'
        nsmap = { gpxx: 'https://www8.garmin.com/xmlschemas/GpxExtensions/v3/GpxExtensionsv3.xsd' }
        gpx.nsmap = nsmap
        for point in routes:
            if isinstance(point, garmin.RteHdr):
                # Possible fields: ('nmbr', 'cmnt', 'ident')
                gpx_route = gpxpy.gpx.GPXRoute()
                number = point.get_dict().get('nmbr')
                name = point.get_dict().get('ident')
                comment = point.get_dict().get('cmnt')
                gpx_route.number = number
                if name is not None:
                    gpx_route.name = name.decode(encoding='latin_1')
                if comment is not None:
                    gpx_route.comment = comment.decode(encoding='latin_1')
                gpx.routes.append(gpx_route)
            elif isinstance(point, garmin.Wpt):
                # Possible fields: ('dist', 'state', 'wpt_ident', 'subclass',
                # 'dst', 'facility', 'dtyp', 'dspl_color', 'cross_road',
                # 'wpt_cat', 'attr', 'color', 'smbl', 'addr', 'ete', 'alt',
                # 'wpt_class', 'lnk_ident', 'dpth', 'city', 'posn', 'dspl',
                # 'ident', 'unused', 'cmnt', 'temp', 'cc', 'time')
                if point.get_posn().is_valid():
                    latitude = point.get_posn().as_degrees().lat
                    longitude = point.get_posn().as_degrees().lon
                    if point.get_dict().get('alt') is not None and point.is_valid_alt() is True:
                        elevation = point.alt
                    else:
                        elevation = None
                    name = point.ident.decode(encoding='latin_1')
                    comment = point.cmnt.decode(encoding='latin_1')
                    if point.get_dict().get('time') is not None and point.is_valid_time() is True:
                        time = point.get_datetime()
                    else:
                        time = None
                    if point.get_dict().get('smbl') is not None:
                        smbl = point.get_smbl()
                        if self._symbol.get(smbl) is not None:
                            symbol = self._symbol.get(smbl)
                        else:
                            symbol = smbl
                    else:
                        symbol = None
                    gpx_point = gpxpy.gpx.GPXRoutePoint(latitude=latitude,
                                                        longitude=longitude,
                                                        elevation=elevation,
                                                        name=name,
                                                        comment=comment,
                                                        time=time,
                                                        symbol=symbol)
                    route_point_extension = ET.Element(f'{{{gpxx}}}RoutePointExtension')
                    if point.get_dict().get('wpt_class') is not None:
                        wpt_class = point.get_wpt_class()
                        if wpt_class != 0:  # Non-user waypoint
                            subclass = ET.SubElement(route_point_extension, f'{{{gpxx}}}Subclass')
                            subclass_int = point.subclass
                            subclass_bytes = bytes(subclass_int)
                            subclass_hex = subclass_bytes.hex()
                            subclass.text = subclass_hex
                    gpx_point.extensions.append(route_point_extension)
                    gpx_route.points.append(gpx_point)
            elif isinstance(point, garmin.RteLink):
                pass
        return gpx


class GPXTracks(GPX):

    def __init__(self, tracks):
        self.gpx = self.tracks_to_gpx(tracks)

    def tracks_to_gpx(self, tracks):
        gpx = gpxpy.gpx.GPX()
        gpx.name = 'Tracks'
        gpx.description = 'Tracks'
        gpxx = 'gpxx'
        gpxtpx = 'gpxtpx'
        nsmap = { gpxx: 'https://www8.garmin.com/xmlschemas/GpxExtensions/v3/GpxExtensionsv3.xsd',
                  gpxtpx: 'http://www8.garmin.com/xmlschemas/TrackPointExtensionv2.xsd' }
        gpx.nsmap = nsmap
        for point in tracks:
            if isinstance(point, garmin.TrkHdr):
                # Possible fields: ('color', 'trk_ident', 'index', 'dspl')
                gpx_track = gpxpy.gpx.GPXTrack()
                name = point.trk_ident
                gpx.tracks.append(gpx_track)
                gpx_track.name = name.decode(encoding='latin_1')
                track_extension = ET.Element(f'{{{gpxx}}}TrackExtension')
                if point.get_dict().get('color') is not None or point.get_dict().get('dspl_color') is not None:
                    color = point.get_color()
                    if self._display_color.get('color') is not None:
                        display_color = ET.SubElement(track_extension, f'{{{gpxx}}}DisplayColor')
                        display_color.text = self._display_color.get('color')
                gpx_track.extensions.append(track_extension)
            elif isinstance(point, garmin.TrkPoint):
                # Possible fields: ('new_trk', 'alt', 'heart_rate', 'sensor',
                # 'dpth', 'cadence', 'posn', 'temp', 'time', 'distance')
                if len(gpx.tracks) == 0:
                    gpx_track = gpxpy.gpx.GPXTrack()
                    gpx.tracks.append(gpx_track)
                if point.new_trk is True or len(gpx_track.segments) == 0:
                    gpx_segment = gpxpy.gpx.GPXTrackSegment()
                    gpx_track.segments.append(gpx_segment)
                if point.get_posn().is_valid():
                    latitude = point.get_posn().as_degrees().lat
                    longitude = point.get_posn().as_degrees().lon
                    time = point.get_datetime()
                    if point.is_valid_alt() is True:
                        elevation = point.get_dict().get('alt')
                    else:
                        elevation = None
                    gpx_point = gpxpy.gpx.GPXTrackPoint(latitude=latitude,
                                                        longitude=longitude,
                                                        elevation=elevation,
                                                        time=time)
                    track_point_extension = ET.Element(f'{{{gpxtpx}}}TrackPointExtension')
                    if point.get_dict().get('heart_rate') is not None:
                        hr = ET.SubElement(track_point_extension, f'{{{gpxtpx}}}hr')
                        hr.text = str(point.heart_rate)
                    if point.get_dict().get('dpth') is not None and point.is_valid_dpth() is True:
                        depth = ET.SubElement(track_point_extension, f'{{{gpxtpx}}}depth')
                        depth.text = str(point.dpth)
                    if point.get_dict().get('cadence') is not None:
                        cad = ET.SubElement(track_point_extension, f'{{{gpxtpx}}}cad')
                        cad.text = str(point.cadence)
                    if point.get_dict().get('temp') is not None and point.is_valid_temp() is True:
                        atemp = ET.SubElement(track_point_extension, f'{{{gpxtpx}}}atemp')
                        atemp.text = str(point.temp)
                    gpx_point.extensions.append(track_point_extension)
                    gpx_segment.points.append(gpx_point)
        return gpx


class Gpsd:
    pass


class TPV(Gpsd):

    def __init__(self, pvt):
        self.pvt = pvt
        self.mode = self._get_mode()
        self.time = self.pvt.get_datetime().isoformat()
        self.alt_hae = self.pvt.alt
        self.alt_msl = self.pvt.get_msl_alt()
        # Gpsd assumes a confidence of 50%, and applies a correction to
        # obtain a 95% confidence circle. However, according to the
        # specification the 2-sigma (95th percentile) accuracy value is
        # provided, so no correction is needed.
        self.sep = self.pvt.epe
        self.eph = self.pvt.eph
        self.epv = self.pvt.epv
        self.geoid_sep = -self.pvt.msl_hght  # sign is opposite of garmin sign
        self.lat = self.pvt.get_posn().as_degrees().lat
        self.leapseconds = self.pvt.leap_scnds
        self.lon = self.pvt.get_posn().as_degrees().lon
        self.vel_d = -self.pvt.up  # sign is opposite of garmin sign
        self.vel_e = self.pvt.east
        self.vel_n = self.pvt.north

    def _get_mode(self, product_description=None):
        if product_description:
            fix = self.pvt.get_fix(str(product_description, 'latin_1'))
        else:
            fix = self.pvt.get_fix()
        if fix == '2D' or fix == '2D_diff':
            mode = 2
        elif fix == '3D' or fix == '3D_diff':
            mode = 3
        else:
            mode = 1
        return mode

    def __str__(self):
        return json.dumps({
            'class': 'TPV',
            'device': 'device',
            'mode': self.mode,
            'time': self.time,
            'altHAE': self.alt_hae,
            'altMSL': self.alt_msl,
            'sep': self.sep,
            'eph': self.eph,
            'epv': self.epv,
            'geoidSep': self.geoid_sep,
            'lat': self.lat,
            'leapseconds': self.leapseconds,
            'lon': self.lon,
            'velD': self.vel_d,
            'velE': self.vel_e,
            'velN': self.vel_n,
        })


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

    def __init__(self, port):
        self.port = port
        self.gps = self.get_gps(self.port)


    def get_gps(self, port):
        phys = garmin.USBLink() if port == 'usb:' else garmin.SerialLink(port)
        log.info(f"listening on port {port}")
        return garmin.Garmin(phys)

    def info(self, args):
        info = "Product information\n"
        info += "===================\n"
        info += f"Product ID: {self.gps.product_id}\n"
        info += f"Software version: {self.gps.software_version:.2f}\n"
        info += f"Product description: {str(self.gps.product_description, 'latin_1')}\n"
        info += f"Unit ID: {self.gps.get_unit_id()}\n"
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
        data = self.gps.map_transfer.get_memory_properties()
        info = "Memory information\n"
        info += "==================\n"
        info += f"Memory region: {data.mem_region}\n"
        info += f"Maximum number of tiles: {data.max_tiles}\n"
        info += f"Memory size: {data.mem_size}\n"
        args.filename.write(info)

    def map(self, args):
        records = self.gps.map_transfer.get_map_properties()
        if records is None:
            log.warning("Map not found")
        else:
            info = "Map information\n"
            info += "===============\n"
            for record in records:
                if isinstance(record, garmin.MapSegment):
                    info += "Map segment description\n"
                    info += "-----------------------\n"
                    info += f"Product ID: {record.pid}\n"
                    info += f"Family ID: {record.fid}\n"
                    info += f"Segment ID: {record.segment_id}\n"
                    info += f"Family name: {str(record.name, 'latin_1')}\n"
                    info += f"Segment name: {str(record.segment_name, 'latin_1')}\n"
                    info += f"Area name: {str(record.area_name, 'latin_1')}\n"
                    info += "\n"
                elif isinstance(record, garmin.MapSet):
                    info += "Map set description\n"
                    info += "-------------------\n"
                    info += f"Mapset name: {str(record.mapset_name, 'latin_1')}\n"
                    info += "\n"
                elif isinstance(record, garmin.MapUnlock):
                    info += "Map unlock description\n"
                    info += "----------------------\n"
                    info += f"Unlock code: {str(unlock_code, 'latin_1')}\n"
                    info += "\n"
                elif isinstance(record, garmin.MapProduct):
                    info += "Map product description\n"
                    info += "-----------------------\n"
                    info += f"Product ID: {record.pid}\n"
                    info += f"Family ID: {record.fid}\n"
                    info += f"Family name: {str(record.name, 'latin_1')}\n"
                    info += "\n"
            args.filename.write(info)

    def get_waypoints(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                waypoints = self.gps.get_waypoints(callback=progress_bar.update_to)
        else:
            waypoints = self.gps.get_waypoints()
        if self.gps.waypoint_category_transfer is not None:
            if args.progress:
                with ProgressBar() as progress_bar:
                    waypoint_categories = self.gps.waypoint_category_transfer.get_data(callback=progress_bar.update_to)
            else:
                waypoint_categories = self.gps.waypoint_category_transfer.get_data()
        else:
            waypoint_categories = None
        if args.format == 'txt':
            for waypoint in waypoints:
                args.filename.write(f"{str(waypoint)}\n")
        elif args.format == 'garmin':
            for waypoint in waypoints:
                args.filename.write(f"{repr(waypoint)}\n")
        elif args.format == 'gpx':
            gpx = GPXWaypoints(waypoints)
            args.filename.write(f"{str(gpx)}\n")

    def put_waypoints(self, args):
        data = []
        for line in args.filename:
            object = eval(line)
            data.append(object)
        if args.progress:
            with ProgressBar() as progress_bar:
                self.gps.put_waypoints(data, callback=progress_bar.update_to)
        else:
            self.gps.put_waypoints(data)

    def get_routes(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                routes = self.gps.get_routes(callback=progress_bar.update_to)
        else:
            routes = self.gps.get_routes()
        if args.format == 'txt':
            for point in routes:
                args.filename.write(f"{str(point)}\n")
        elif args.format == 'garmin':
            for point in routes:
                args.filename.write(f"{repr(point)}\n")
        elif args.format == 'gpx':
            gpx = GPXRoutes(routes)
            args.filename.write(f"{str(gpx)}\n")

    def put_routes(self, args):
        data = []
        for line in args.filename:
            object = eval(line)
            data.append(object)
        if args.progress:
            with ProgressBar() as progress_bar:
                self.gps.put_routes(data, callback=progress_bar.update_to)
        else:
            self.gps.put_routes(data)

    def get_tracks(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                tracks = self.gps.get_tracks(callback=progress_bar.update_to)
        else:
            tracks = self.gps.get_tracks()
        if args.format == 'txt':
            for point in tracks:
                args.filename.write(f"{str(point)}\n")
        elif args.format == 'garmin':
            for point in tracks:
                args.filename.write(f"{repr(point)}\n")
        elif args.format == 'gpx':
            gpx = GPXTracks(tracks)
            args.filename.write(f"{str(gpx)}\n")

    def put_tracks(self, args):
        data = []
        for line in args.filename:
            object = eval(line)
            data.append(object)
        if args.progress:
            with ProgressBar() as progress_bar:
                self.gps.put_tracks(data, callback=progress_bar.update_to)
        else:
            self.gps.put_tracks(data)

    def get_proximities(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                proximities = self.gps.get_proximities(callback=progress_bar.update_to)
        else:
            proximities = self.gps.get_proximities()
        if args.format == 'txt':
            for waypoint in proximities:
                args.filename.write(f"{str(waypoint)}\n")
        elif args.format == 'garmin':
            for waypoint in proximities:
                args.filename.write(f"{repr(waypoint)}\n")
        elif args.format == 'gpx':
            gpx = self.waypoints_to_gpx(proximities)
            args.filename.write(gpx.to_xml())

    def put_proximities(self, args):
        data = []
        for line in args.filename:
            object = eval(line)
            data.append(object)
        if args.progress:
            with ProgressBar() as progress_bar:
                self.gps.put_proximities(data, callback=progress_bar.update_to)
        else:
            self.gps.put_proximities(data)

    def get_almanac(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                almanacs = self.gps.get_almanac(callback=progress_bar.update_to)
        else:
            almanacs = self.gps.get_almanac()
        if args.format == 'txt':
            func = str
        elif args.format == 'garmin':
            func = repr
        for almanac in almanacs:
            args.filename.write(f"{func(almanac)}\n")

    def time(self, args):
        time = self.gps.get_time()
        if args.format == 'txt':
            args.filename.write(f"{time.get_datetime()}\n")
        elif args.format == 'garmin':
            args.filename.write(f"{repr(time)}\n")

    def position(self, args):
        position = self.gps.get_position()
        if args.format == 'txt':
            func = str
        elif args.format == 'garmin':
            func = repr
        args.filename.write(f"{func(position.as_degrees())}\n")

    def pvt(self, args):
        def signal_handler(signal, frame):
            self.gps.pvt_off()
            sys.exit(0)
        log.warning("Press Ctrl-C to quit")
        # Catch interrupt from keyboard (Control-C)
        signal.signal(signal.SIGINT, signal_handler)
        if args.format == 'txt':
            func = str
        elif args.format == 'garmin':
            func = repr
        elif args.format == 'tpv':
            func = TPV
        self.gps.pvt_on()
        # In PVT mode the device will transmit packets approximately once per
        # second, but the default timeout of 1 second will lead to a timeout
        # error frequently
        self.gps.phys.set_timeout(2)
        while True:
            pvt = self.gps.get_pvt()
            args.filename.write(f"{func(pvt)}\n")
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

    def get_runs(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                runs = self.gps.get_runs(callback=progress_bar.update_to)
        else:
            runs = self.gps.get_runs()
        for run in runs:
            if args.format == 'txt':
                args.filename.write(f"{str(run)}\n")
            elif args.format == 'garmin':
                args.filename.write(f"{repr(run)}\n")

    def get_map(self, args):
        if args.progress:
            with ProgressBar() as progress_bar:
                data = self.gps.get_map(callback=progress_bar.update_to)
        else:
            data = self.gps.get_map()
        if data is None:
            log.warning("Map not found")
        else:
            with open(args.filename, 'wb') as f:
                f.write(data)

    def put_map(self, args):
        with open(args.filename, 'rb') as f:
            if args.progress:
                with ProgressBar(unit='B', unit_scale=True, unit_divisor=1024, miniters=1) as progress_bar:
                    self.gps.put_map(f, callback=progress_bar.update_to)
            else:
                self.gps.put_map(f)

    def del_map(self, args):
        self.gps.del_map()

    def get_screenshot(self, args):
        with ProgressBar() as progress_bar:
            image = self.gps.get_screenshot(callback=progress_bar.update_to)
        image.save(args.filename, format=args.format)

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
        else:
            indices = args.index
        for idx in indices:
            basename = image_list[idx].get('name')
            log.info(f"Downloading {basename}")
            single_modulo = '(?<!%)%(?!%)'  # match a single % character
            if args.filename is None or os.path.isdir(args.filename):
                if args.format is None:
                    log.info(f"Using the BMP format")
                    filename = basename + '.bmp'
                else:
                    log.debug(f"Supported formats: {*PIL.Image.registered_extensions().values(), }")
                    log.info(f"Trying to find an extension matching the {args.format.upper()} format")
                    extensions = [ extension for (extension, format) in PIL.Image.registered_extensions().items() if format == args.format.upper() ]
                    log.info(f"Found extensions {PIL.Image.registered_extensions().items()}")
                    if len(extensions) == 0:
                        sys.exit(f"Image format {args.format.upper()} is not supported")
                    elif len(extensions) == 1:
                        log.info(f"Found extension {extensions[0]}")
                        filename = basename + extensions[0]
                    elif len(extensions) > 1:
                        log.info(f"Found extensions {*extensions, }")
                        # If a format has multiple extensions, prefer the
                        # extension with the same name as the format.
                        preferred_extension = [ extension for extension in extensions if extension.endswith(args.format.lower()) ]
                        if preferred_extension:
                            log.info(f"Prefer extension {preferred_extension[0]}")
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
            if args.progress:
                with ProgressBar(unit='B', unit_scale=True, unit_divisor=1024, miniters=1) as progress_bar:
                    image = self.gps.get_image(idx, callback=progress_bar.update_to)
            else:
                image = self.gps.get_image(idx)
            if args.format is not None and not path.endswith(args.format.lower()):
                log.warning(f"Overriding format by saving {path} as {args.format.upper()}")
            log.info(f"Saving {path}")
            image.save(path, format=args.format)

    def put_image(self, args):
        files = args.filename
        image_list = self.gps.get_image_list()
        if args.index is None:
            indices = [ image['idx'] for image in image_list if image['writable'] is True ]
        else:
            indices = args.index
        if len(files) != len(indices):
            log.warning(f"Trying to upload {len(files)} files to {len(indices)} indices.")
        for idx, filename in zip(indices, files):
            image = image_list[idx]
            if image['writable'] is True:
                if args.progress:
                    with ProgressBar(unit='B', unit_scale=True, unit_divisor=1024, miniters=1) as progress_bar:
                        self.gps.put_image(idx, filename, callback=progress_bar.update_to)
                else:
                    self.gps.put_image(idx, filename)
            else:
                log.error(f"Image {image['name']} with index {idx} is not writable")

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
map = subparsers.add_parser('map', help="Return map info")
map.set_defaults(command='map')
map.add_argument('filename',
                 nargs='?',
                 type=argparse.FileType(mode='w'),
                 default=sys.stdout,
                 help="Set output file")
get_waypoints = subparsers.add_parser('get-waypoints', help="Download waypoints")
get_waypoints.set_defaults(command='get_waypoints')
get_waypoints.add_argument('-t',
                           '--format',
                           choices=['txt', 'garmin', 'gpx'],
                           default='garmin',
                           help="Set output format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``gpx`` returns a string in GPS Exchange Format (GPX).")
get_waypoints.add_argument('filename',
                           nargs='?',
                           type=argparse.FileType(mode='w'),
                           default=sys.stdout,
                           help="Set output file")
put_waypoints = subparsers.add_parser('put-waypoints', help="Upload waypoints")
put_waypoints.set_defaults(command='put_waypoints')
put_waypoints.add_argument('-t',
                           '--format',
                           choices=['txt', 'garmin'],
                           default='garmin',
                           help="Set input format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype.")
put_waypoints.add_argument('filename',
                           nargs='?',
                           type=argparse.FileType(mode='r'),
                           default=sys.stdin,
                           help="Set input file")
get_routes = subparsers.add_parser('get-routes', help="Download routes")
get_routes.set_defaults(command='get_routes')
get_routes.add_argument('-t',
                        '--format',
                        choices=['txt', 'garmin', 'gpx'],
                        default='garmin',
                        help="Set output format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``gpx`` returns a string in GPS Exchange Format (GPX).")
get_routes.add_argument('filename',
                        nargs='?',
                        type=argparse.FileType(mode='w'),
                        default=sys.stdout,
                        help="Set output file")
put_routes = subparsers.add_parser('put-routes', help="Upload routes")
put_routes.set_defaults(command='put_routes')
put_routes.add_argument('-t',
                        '--format',
                        choices=['txt', 'garmin'],
                        default='garmin',
                        help="Set input format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype.")
put_routes.add_argument('filename',
                        nargs='?',
                        type=argparse.FileType(mode='r'),
                        default=sys.stdin,
                        help="Set input file")
get_tracks = subparsers.add_parser('get-tracks', help="Download tracks")
get_tracks.set_defaults(command='get_tracks')
get_tracks.add_argument('-t',
                        '--format',
                        choices=['txt', 'garmin', 'gpx'],
                        default='garmin',
                        help="Set output format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``gpx`` returns a string in GPS Exchange Format (GPX).")
get_tracks.add_argument('filename',
                        nargs='?',
                        type=argparse.FileType(mode='w'),
                        default=sys.stdout,
                        help="Set output file")
put_tracks = subparsers.add_parser('put-tracks', help="Upload tracks")
put_tracks.set_defaults(command='put_tracks')
put_tracks.add_argument('-t',
                        '--format',
                        choices=['txt', 'garmin'],
                        default='garmin',
                        help="Set input format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype.")
put_tracks.add_argument('filename',
                        nargs='?',
                        type=argparse.FileType(mode='r'),
                        default=sys.stdin,
                        help="Set input file")
get_proximities = subparsers.add_parser('get-proximities', help="Download proximities")
get_proximities.set_defaults(command='get_proximities')
get_proximities.add_argument('-t',
                             '--format',
                             choices=['txt', 'garmin', 'gpx'],
                             default='garmin',
                             help="Set output format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``gpx`` returns a string in GPS Exchange Format (GPX).")
get_proximities.add_argument('filename',
                             nargs='?',
                             type=argparse.FileType(mode='w'),
                             default=sys.stdout,
                             help="Set output file")
put_proximities = subparsers.add_parser('put-proximities', help="Upload proximities")
put_proximities.set_defaults(command='put_proximities')
put_proximities.add_argument('-t',
                             '--format',
                             choices=['txt', 'garmin'],
                             default='garmin',
                             help="Set input format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype.")
put_proximities.add_argument('filename',
                             nargs='?',
                             type=argparse.FileType(mode='r'),
                             default=sys.stdin,
                             help="Set input file")
get_almanac = subparsers.add_parser('get-almanac', help="Download almanac")
get_almanac.set_defaults(command='get_almanac')
get_almanac.add_argument('-t',
                         '--format',
                         choices=['txt', 'garmin'],
                         default='garmin',
                         help="Set output format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype.")
get_almanac.add_argument('filename',
                         nargs='?',
                         type=argparse.FileType(mode='w'),
                         default=sys.stdout,
                         help="Set output file")
time = subparsers.add_parser('time', help="Download current date and time")
time.set_defaults(command='time')
time.add_argument('-t',
                  '--format',
                  choices=['txt', 'garmin'],
                  default='garmin',
                  help="Set output format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype.")
time.add_argument('filename',
                  nargs='?',
                  type=argparse.FileType(mode='w'),
                  default=sys.stdout,
                  help="Set output file")
position = subparsers.add_parser('position', help="Download current position")
position.set_defaults(command='position')
position.add_argument('-t',
                      '--format',
                      choices=['txt', 'garmin'],
                      default='garmin',
                      help="Set output format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype.")
position.add_argument('filename',
                      nargs='?',
                      type=argparse.FileType(mode='w'),
                      default=sys.stdout,
                      help="Set output file")
pvt = subparsers.add_parser('pvt', help="Download pvt")
pvt.set_defaults(command='pvt')
pvt.add_argument('-t',
                 '--format',
                 choices=['txt', 'garmin', 'tpv'],
                 default='garmin',
                 help="Set output format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype. ``tpv`` returns a TPV object based on the GPSD JSON protocol.")
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
                      help="Set output format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype.")
get_laps.add_argument('filename',
                      nargs='?',
                      type=argparse.FileType(mode='w'),
                      default=sys.stdout,
                      help="Set output file")
get_runs = subparsers.add_parser('get-runs', help="Download runs")
get_runs.set_defaults(command='get_runs')
get_runs.add_argument('-t',
                      '--format',
                      choices=['txt', 'garmin'],
                      default='garmin',
                      help="Set output format. ``txt`` returns a JSON string that consists of a dictionary with the datatypes attributes. ``garmin`` returns a string that can be executed and will yield the same value as the datatype.")
get_runs.add_argument('filename',
                      nargs='?',
                      type=argparse.FileType(mode='w'),
                      default=sys.stdout,
                      help="Set output file")
get_map = subparsers.add_parser('get-map', help="Download map")
get_map.set_defaults(command='get_map')
get_map.add_argument('filename',
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
                            default='Screenshot.bmp',
                            help="Set image file name")
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
    log.setLevel(logging_level)
    log.info(f"Version {__version__}")
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
