"""gpx.py: Contains the GPX class which is used to encode gpx files."""

from datetime import datetime, tzinfo
import gpxpy
import xml.etree.ElementTree as ET
from . import datatype as mod_datatype
from . import logger as mod_logger

class GPX:
    creator = "Pygarmin - https://github.com/quentinsf/pygarmin/"

    _display_mode = {
        'dspl_smbl_none': 'SymbolOnly',
        'dspl_smbl_only': 'SymbolOnly',
        'dspl_smbl_name': 'SymbolAndName',
        'dspl_smbl_cmnt': 'SymbolAndDescription',
    }

    _display_color = {
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

    def __init__(self, waypoints=[]):
        self.gpx = self.waypoints_to_gpx(waypoints)

    def waypoints_to_gpx(self, waypoints):
        gpx = gpxpy.gpx.GPX()
        gpx.name = 'Waypoints'
        gpx.description = 'Waypoints'
        gpx.creator = self.creator
        gpxx = 'gpxx'
        nsmap = { gpxx: 'https://www8.garmin.com/xmlschemas/GpxExtensions/v3/GpxExtensionsv3.xsd' }
        gpx.nsmap = nsmap
        for point in waypoints:
            if isinstance(point, mod_datatype.Wpt) and point.get_posn().is_valid():
                # Possible fields: ('posn', 'color', 'lnk_ident', 'city',
                # 'attr', 'facility', 'dspl_color', 'dst', 'dpth', 'cc', 'cmnt',
                # 'wpt_cat', 'alt', 'state', 'time', 'unused', 'cross_road',
                # 'addr', 'dtyp', 'dspl', 'temp', 'dist', 'subclass', 'ete',
                # 'wpt_class', 'ident', 'smbl', 'wpt_ident')
                latitude = point.get_posn().as_degrees().lat
                longitude = point.get_posn().as_degrees().lon
                name = point.ident.decode(encoding='latin_1')
                comment = point.cmnt.decode(encoding='latin_1')
                if point.get_dict().get('alt') is not None and point.is_valid_alt():
                    elevation = point.alt
                else:
                    elevation = None
                if point.get_dict().get('time') is not None and point.is_valid_time():
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
                if point.get_dict().get('dst') is not None and point.is_valid_dst():
                    proximity = ET.SubElement(waypoint_extension, f'{{{gpxx}}}Proximity')
                    proximity.text = str(point.dst)
                if point.get_dict().get('dist') is not None  and point.is_valid_dist():
                    proximity = ET.SubElement(waypoint_extension, f'{{{gpxx}}}Proximity')
                    proximity.text = str(point.dist)
                if point.get_dict().get('temp') is not None and point.is_valid_temp():
                    temperature = ET.SubElement(waypoint_extension, f'{{{gpxx}}}Temperature')
                    temperature.text = str(point.temp)
                if point.get_dict().get('dpth') and point.is_valid_dpth():
                    depth = ET.SubElement(waypoint_extension, f'{{{gpxx}}}Depth')
                    depth.text = str(point.dpth)
                if point.get_dict().get('dspl'):
                    display_mode = ET.SubElement(waypoint_extension, f'{{{gpxx}}}DisplayMode')
                    dspl = point.get_dspl()
                    display_mode.text = self._display_mode.get(dspl)
                gpx.waypoints.append(gpx_point)
        return gpx


class GPXRoutes(GPX):

    def __init__(self, routes=[]):
        self.gpx = self.routes_to_gpx(routes)

    def routes_to_gpx(self, routes):
        gpx = gpxpy.gpx.GPX()
        gpx.name = 'Routes'
        gpx.description = 'Routes'
        gpx.creator = self.creator
        gpxx = 'gpxx'
        nsmap = { gpxx: 'https://www8.garmin.com/xmlschemas/GpxExtensions/v3/GpxExtensionsv3.xsd' }
        gpx.nsmap = nsmap
        for route in routes:
            for point in route:
                if isinstance(point, mod_datatype.RteHdr):
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
                elif isinstance(point, mod_datatype.Wpt):
                    # Possible fields: ('dist', 'state', 'wpt_ident', 'subclass',
                    # 'dst', 'facility', 'dtyp', 'dspl_color', 'cross_road',
                    # 'wpt_cat', 'attr', 'color', 'smbl', 'addr', 'ete', 'alt',
                    # 'wpt_class', 'lnk_ident', 'dpth', 'city', 'posn', 'dspl',
                    # 'ident', 'unused', 'cmnt', 'temp', 'cc', 'time')
                    if point.get_posn().is_valid():
                        latitude = point.get_posn().as_degrees().lat
                        longitude = point.get_posn().as_degrees().lon
                        if point.get_dict().get('alt') is not None and point.is_valid_alt():
                            elevation = point.alt
                        else:
                            elevation = None
                        name = point.ident.decode(encoding='latin_1')
                        comment = point.cmnt.decode(encoding='latin_1')
                        if point.get_dict().get('time') is not None and point.is_valid_time():
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
                elif isinstance(point, mod_datatype.RteLink):
                    pass
        return gpx


class GPXTracks(GPX):

    def __init__(self, tracks=[]):
        self.gpx = self.tracks_to_gpx(tracks)

    def tracks_to_gpx(self, tracks):
        gpx = gpxpy.gpx.GPX()
        gpx.name = 'Tracks'
        gpx.description = 'Tracks'
        gpx.creator = self.creator
        gpxx = 'gpxx'
        gpxtpx = 'gpxtpx'
        nsmap = { gpxx: 'https://www8.garmin.com/xmlschemas/GpxExtensions/v3/GpxExtensionsv3.xsd',
                  gpxtpx: 'http://www8.garmin.com/xmlschemas/TrackPointExtensionv2.xsd' }
        gpx.nsmap = nsmap
        for track in tracks:
            for point in track:
                if isinstance(point, mod_datatype.TrkHdr):
                    # Possible fields: ('color', 'trk_ident', 'index', 'dspl')
                    gpx_track = gpxpy.gpx.GPXTrack()
                    identifier = point.get_dict().get('trk_ident')
                    index = point.get_dict().get('index')
                    name = identifier if identifier else str(index).encode()
                    gpx.tracks.append(gpx_track)
                    gpx_track.name = name.decode(encoding='latin_1')
                    track_extension = ET.Element(f'{{{gpxx}}}TrackExtension')
                    if point.get_dict().get('color') is not None or point.get_dict().get('dspl_color') is not None:
                        color = point.get_color()
                        if self._display_color.get(color) is not None:
                            display_color = ET.SubElement(track_extension, f'{{{gpxx}}}DisplayColor')
                            display_color.text = self._display_color.get(color)
                    gpx_track.extensions.append(track_extension)
                elif isinstance(point, mod_datatype.TrkPoint):
                    # Possible fields: ('new_trk', 'alt', 'heart_rate', 'sensor',
                    # 'dpth', 'cadence', 'posn', 'temp', 'time', 'distance')
                    if len(gpx.tracks) == 0:
                        gpx_track = gpxpy.gpx.GPXTrack()
                        gpx.tracks.append(gpx_track)
                    if point.get_dict().get('new_trk') or len(gpx_track.segments) == 0:
                        gpx_segment = gpxpy.gpx.GPXTrackSegment()
                        gpx_track.segments.append(gpx_segment)
                    if point.get_posn().is_valid():
                        latitude = point.get_posn().as_degrees().lat
                        longitude = point.get_posn().as_degrees().lon
                        time = point.get_datetime()
                        if point.is_valid_alt():
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
                        if point.get_dict().get('dpth') is not None and point.is_valid_dpth():
                            depth = ET.SubElement(track_point_extension, f'{{{gpxtpx}}}depth')
                            depth.text = str(point.dpth)
                        if point.get_dict().get('cadence') is not None:
                            cad = ET.SubElement(track_point_extension, f'{{{gpxtpx}}}cad')
                            cad.text = str(point.cadence)
                        if point.get_dict().get('temp') is not None and point.is_valid_temp():
                            atemp = ET.SubElement(track_point_extension, f'{{{gpxtpx}}}atemp')
                            atemp.text = str(point.temp)
                        gpx_point.extensions.append(track_point_extension)
                        gpx_segment.points.append(gpx_point)
        return gpx


class Garmin():

    _display_mode = {
        'SymbolAndName':        'dspl_smbl_name',
        'SymbolOnly':           'dspl_smbl_only',
        'SymbolAndDescription': 'dspl_smbl_cmnt',
    }

    _display_color = {
        None: 'clr_default_color',
        'Black': 'clr_black',
        'DarkRed': 'clr_dark_red',
        'DarkGreen': 'clr_dark_green',
        'DarkYellow': 'clr_dark_yellow',
        'DarkBlue': 'clr_dark_blue',
        'DarkMagenta': 'clr_dark_magenta',
        'DarkCyan': 'clr_dark_cyan',
        'LightGray': 'clr_light_gray',
        'DarkGray': 'clr_dark_gray',
        'Red': 'clr_red',
        'Green': 'clr_green',
        'Yellow': 'clr_yellow',
        'Blue': 'clr_blue',
        'Magenta': 'clr_magenta',
        'Cyan': 'clr_cyan',
        'White': 'clr_white',
        'Transparent': 'clr_transparent',
    }

    _symbol = {
        'Dot, White': 'smbl_dot',
        'Residence': 'smbl_house',
        'Gas Station': 'smbl_gas',
        'Car': 'smbl_car',
        'Fishing Area': 'smbl_fish',
        'Boat Ramp': 'smbl_boat',
        'Anchor': 'smbl_anchor',
        'Shipwreck': 'smbl_wreck',
        'Exit': 'smbl_exit',
        'Skull and Crossbones': 'smbl_skull',
        'Flag': 'smbl_flag',
        'Campground': 'smbl_camp',
        'Circle with X': 'smbl_circle_x',
        'Hunting Area': 'smbl_deer',
        'Medical Facility': 'smbl_1st_aid',
        'TracBack Point': 'smbl_back_track',
        'Anchor': 'sym_anchor',
        'Bell': 'sym_bell',
        'Diamond, Green': 'sym_diamond_grn',
        'Diamond, Red': 'sym_diamond_red',
        'Diver Down Flag 1': 'sym_dive1',
        'Diver Down Flag 2': 'sym_dive2',
        'Bank': 'sym_dollar',
        'Fishing Area': 'sym_fish',
        'Gas Station': 'sym_fuel',
        'Horn': 'sym_horn',
        'Residence': 'sym_house',
        'Restaurant': 'sym_knife',
        'Light': 'sym_light',
        'Bar': 'sym_mug',
        'Skull and Crossbones': 'sym_skull',
        'Square, Green': 'sym_square_grn',
        'Square, Red': 'sym_square_red',
        'Buoy, White': 'sym_wbuoy',
        'Waypoint': 'sym_wpt_dot',
        'Shipwreck': 'sym_wreck',
        'Man Overboard': 'sym_mob',
        'Navaid, Amber': 'sym_buoy_ambr',
        'Navaid, Black': 'sym_buoy_blck',
        'Navaid, Blue': 'sym_buoy_blue',
        'Navaid, Green': 'sym_buoy_grn',
        'Navaid, Green/Red': 'sym_buoy_grn_red',
        'Navaid, Green/White': 'sym_buoy_grn_wht',
        'Navaid, Orange': 'sym_buoy_orng',
        'Navaid, Red': 'sym_buoy_red',
        'Navaid, Red/Green': 'sym_buoy_red_grn',
        'Navaid, Red/White': 'sym_buoy_red_wht',
        'Navaid, Violet': 'sym_buoy_violet',
        'Navaid, White': 'sym_buoy_wht',
        'Navaid, White/Green': 'sym_buoy_wht_grn',
        'Navaid, White/Red': 'sym_buoy_wht_red',
        'Dot, White': 'sym_dot',
        'Radio Beacon': 'sym_rbcn',
        'Boat Ramp': 'sym_boat_ramp',
        'Campground': 'sym_camp',
        'Restroom': 'sym_restrooms',
        'Shower': 'sym_showers',
        'Drinking Water': 'sym_drinking_wtr',
        'Telephone': 'sym_phone',
        'Medical Facility': 'sym_1st_aid',
        'Information': 'sym_info',
        'Parking Area': 'sym_parking',
        'Park': 'sym_park',
        'Picnic Area': 'sym_picnic',
        'Scenic Area': 'sym_scenic',
        'Skiing Area': 'sym_skiing',
        'Swimming Area': 'sym_swimming',
        'Dam': 'sym_dam',
        'Controlled Area': 'sym_controlled',
        'Danger Area': 'sym_danger',
        'Restricted Area': 'sym_restricted',
        'Ball Park': 'sym_ball',
        'Car': 'sym_car',
        'Hunting Area': 'sym_deer',
        'Shopping Center': 'sym_shpng_cart',
        'Lodging': 'sym_lodging',
        'Mine': 'sym_mine',
        'Trail Head': 'sym_trail_head',
        'Truck Stop': 'sym_truck_stop',
        'Exit': 'sym_user_exit',
        'Flag': 'sym_flag',
        'Circle with X': 'sym_circle_x',
        'Mile Marker': 'sym_mi_mrkr',
        'TracBack Point': 'sym_trcbck',
        'Golf Course': 'sym_golf',
        'City (Small)': 'sym_sml_cty',
        'City (Medium)': 'sym_med_cty',
        'City (Large)': 'sym_lrg_cty',
        'City (Capitol)': 'sym_cap_cty',
        'Amusement Park': 'sym_amuse_pk',
        'Bowling': 'sym_bowling',
        'Car Rental': 'sym_car_rental',
        'Car Repair': 'sym_car_repair',
        'Fast Food': 'sym_fastfood',
        'Fitness Center': 'sym_fitness',
        'Movie Theater': 'sym_movie',
        'Museum': 'sym_museum',
        'Pharmacy': 'sym_pharmacy',
        'Pizza': 'sym_pizza',
        'Post Office': 'sym_post_ofc',
        'RV Park': 'sym_rv_park',
        'School': 'sym_school',
        'Stadium': 'sym_stadium',
        'Department Store': 'sym_store',
        'Zoo': 'sym_zoo',
        'Convenience Store': 'sym_gas_plus',
        'Live Theater': 'sym_faces',
        'Scales': 'sym_weigh_sttn',
        'Toll Booth': 'sym_toll_booth',
        'Bridge': 'sym_bridge',
        'Building': 'sym_building',
        'Cemetery': 'sym_cemetery',
        'Church': 'sym_church',
        'Civil': 'sym_civil',
        'Crossing': 'sym_crossing',
        'Ghost Town': 'sym_hist_town',
        'Levee': 'sym_levee',
        'Military': 'sym_military',
        'Oil Field': 'sym_oil_field',
        'Tunnel': 'sym_tunnel',
        'Beach': 'sym_beach',
        'Forest': 'sym_forest',
        'Summit': 'sym_summit',
        'Airport': 'sym_airport',
        'Heliport': 'sym_heliport',
        'Private Field': 'sym_private',
        'Soft Field': 'sym_soft_fld',
        'Tall Tower': 'sym_tall_tower',
        'Short Tower': 'sym_short_tower',
        'Glider Area': 'sym_glider',
        'Ultralight Area': 'sym_ultralight',
        'Parachute Area': 'sym_parachute',
        'Seaplane Base': 'sym_seaplane',
        'Geocache': 'sym_geocache',
        'Geocache Found': 'sym_geocache_fnd',
        'Contact, Afro': 'sym_cntct_afro',
        'Contact, Alien': 'sym_cntct_alien',
        'Contact, Ball Cap': 'sym_cntct_ball_cap',
        'Contact, Big Ears': 'sym_cntct_big_ears',
        'Contact, Biker': 'sym_cntct_biker',
        'Contact, Bug': 'sym_cntct_bug',
        'Contact, Cat': 'sym_cntct_cat',
        'Contact, Dog': 'sym_cntct_dog',
        'Contact, Dreadlocks': 'sym_cntct_dreads',
        'Contact, Female1': 'sym_cntct_female1',
        'Contact, Female2': 'sym_cntct_female2',
        'Contact, Female3': 'sym_cntct_female3',
        'Contact, Goatee': 'sym_cntct_goatee',
        'Contact, Kung Fu': 'sym_cntct_kung_fu',
        'Contact, Pig': 'sym_cntct_pig',
        'Contact, Pirate': 'sym_cntct_pirate',
        'Contact, Ranger': 'sym_cntct_ranger',
        'Contact, Smiley': 'sym_cntct_smiley',
        'Contact, Spike': 'sym_cntct_spike',
        'Contact, Sumo': 'sym_cntct_sumo',
        'Contact, Blonde': 'sym_cntct_blond_woman',
        'Contact, Clown': 'sym_cntct_clown',
        'Contact, Glasses': 'sym_cntct_glasses_boy',
        'Contact, Panda': 'sym_cntct_panda',
        'Water Hydrant': 'sym_hydrant',
        'Flag, Red': 'sym_flag_red',
        'Flag, Blue': 'sym_flag_blue',
        'Flag, Green': 'sym_flag_green',
        'Pin, Red': 'sym_pin_red',
        'Pin, Blue': 'sym_pin_blue',
        'Pin, Green': 'sym_pin_green',
        'Block, Red': 'sym_block_red',
        'Block, Blue': 'sym_block_blue',
        'Block, Green': 'sym_block_green',
        'Bike Trail': 'sym_bike_trail',
        'Fishing Hot Spot Facility': 'sym_fhs_facility',
        'Police Station': 'sym_badge',
        'Ski Resort': 'sym_snowski',
        'Ice Skating': 'sym_iceskate',
        'Wrecker': 'sym_wrecker',
        'Anchor Prohibited': 'sym_anchor_prohib',
        'Beacon': 'sym_beacon',
        'Coast Guard': 'sym_coast_guard',
        'Reef': 'sym_reef',
        'Weed Bed': 'sym_weedbed',
        'Dropoff': 'sym_dropoff',
        'Dock': 'sym_dock',
        'Marina': 'sym_marina',
        'Bait and Tackle': 'sym_bait_tackle',
        'Stump': 'sym_stump',
        'Circle, Red': 'sym_circle_red',
        'Circle, Green': 'sym_circle_green',
        'Circle, Blue': 'sym_circle_blue',
        'Diamond, Blue': 'sym_diamond_blue',
        'Oval, Red': 'sym_oval_red',
        'Oval, Green': 'sym_oval_green',
        'Oval, Blue': 'sym_oval_blue',
        'Rectangle, Red': 'sym_rect_red',
        'Rectangle, Green': 'sym_rect_green',
        'Rectangle, Blue': 'sym_rect_blue',
        'Square, Blue': 'sym_square_blue',
        'Letter A, Red': 'sym_letter_a_red',
        'Letter A, Green': 'sym_letter_a_green',
        'Letter A, Blue': 'sym_letter_a_blue',
        'Letter B, Red': 'sym_letter_b_red',
        'Letter B, Green': 'sym_letter_b_green',
        'Letter B, Blue': 'sym_letter_b_blue',
        'Letter C, Red': 'sym_letter_c_red',
        'Letter C, Green': 'sym_letter_c_green',
        'Letter C, Blue': 'sym_letter_c_blue',
        'Letter D, Red': 'sym_letter_d_red',
        'Letter D, Green': 'sym_letter_d_green',
        'Letter D, Blue': 'sym_letter_d_blue',
        'Number 0, Red': 'sym_number_0_red',
        'Number 0, Green': 'sym_number_0_green',
        'Number 0, Blue': 'sym_number_0_blue',
        'Number 1, Red': 'sym_number_1_red',
        'Number 1, Green': 'sym_number_1_green',
        'Number 1, Blue': 'sym_number_1_blue',
        'Number 2, Red': 'sym_number_2_red',
        'Number 2, Green': 'sym_number_2_green',
        'Number 2, Blue': 'sym_number_2_blue',
        'Number 3, Red': 'sym_number_3_red',
        'Number 3, Green': 'sym_number_3_green',
        'Number 3, Blue': 'sym_number_3_blue',
        'Number 4, Red': 'sym_number_4_red',
        'Number 4, Green': 'sym_number_4_green',
        'Number 4, Blue': 'sym_number_4_blue',
        'Number 5, Red': 'sym_number_5_red',
        'Number 5, Green': 'sym_number_5_green',
        'Number 5, Blue': 'sym_number_5_blue',
        'Number 6, Red': 'sym_number_6_red',
        'Number 6, Green': 'sym_number_6_green',
        'Number 6, Blue': 'sym_number_6_blue',
        'Number 7, Red': 'sym_number_7_red',
        'Number 7, Green': 'sym_number_7_green',
        'Number 7, Blue': 'sym_number_7_blue',
        'Number 8, Red': 'sym_number_8_red',
        'Number 8, Green': 'sym_number_8_green',
        'Number 8, Blue': 'sym_number_8_blue',
        'Number 9, Red': 'sym_number_9_red',
        'Number 9, Green': 'sym_number_9_green',
        'Number 9, Blue': 'sym_number_9_blue',
        'Triangle, Blue': 'sym_triangle_blue',
        'Triangle, Green': 'sym_triangle_green',
        'Triangle, Red': 'sym_triangle_red',
        # The symbols below are mentioned in Garmin MapSource, but not in the specification
        # 'Multi-Cache'
        # 'Letterbox Cache',
        # 'Puzzle Cache',
        'Library': 'sym_library',
        'Ground Transportation': 'sym_bus',
        'City Hall': 'sym_city_hall',
        'Winery': 'sym_wine',
        'ATV': 'sym_atv',
        'Big Game': 'sym_big_game',
        'Blind': 'sym_blind',
        'Blood Trail': 'sym_blood_trail',
        'Cover': 'sym_cover',
        'Covey': 'sym_covey',
        'Food Source': 'sym_food_source',
        'Furbearer': 'sym_furbearer',
        'Lodge': 'sym_lodge',
        'Small Game': 'sym_small_game',
        'Animal Tracks': 'sym_tracks',
        'Treed Quarry': 'sym_treed_quarry',
        'Tree Stand': 'sym_tree_stand',
        'Truck': 'sym_truck',
        'Upland Game': 'sym_upland_game',
        'Waterfowl': 'sym_waterfowl',
        'Water Source': 'sym_water_source',
    }

    def join(self, iterable, delimiter):
        it = iter(iterable)
        yield next(it)
        for x in it:
            yield delimiter
            yield x


class GarminWaypoints(Garmin):

    def __init__(self, xml_or_file, datatypes):
        self.waypoints = self.gpx_to_waypoints(xml_or_file, datatypes)

    def gpx_to_waypoints(self, xml_or_file, datatypes):
        gpx = gpxpy.parse(xml_or_file)
        waypoints = []
        if gpx.waypoints:
            for point in gpx.waypoints:
                wpt = datatypes[0]()
                mod_logger.log.info(f"Adding waypoint {point.name}")
                wpt.ident = str.encode(point.name)
                degree_posn = mod_datatype.DegreePosition(point.latitude, point.longitude)
                posn = degree_posn.as_semicircles()
                wpt.posn = (posn.lat, posn.lon)
                if point.has_elevation() and 'alt' in wpt.get_keys():
                    wpt.alt = point.elevation
                extension = next((extension for extension in point.extensions if extension.tag.endswith('WayPointExtension')), None)
                if extension is not None:
                    uri = extension.tag.rstrip('WayPointExtension')
                    proximity = extension.find(f'{uri}Proximity')
                    if proximity is not None:
                        wpt.dist = float(proximity.text)
                        wpt.dst = float(proximity.text)
                    temperature = extension.find(f'{uri}Temperature')
                    if temperature is not None:
                        wpt.temp = float(temperature.text)
                    depth = extension.find(f'{uri}Depth')
                    if depth is not None:
                        wpt.dpth = float(depth.text)
                    displaymode = extension.find(f'{uri}DisplayMode')
                    if displaymode is not None:
                        dspl_mode = self._display_mode.get(displaymode.text)
                        dspl_value = next(value for value, mode in wpt._dspl if mode == dpsl_mode)
                        wpt.set_dspl(dspl_value)
                    address = extension.find(f'{uri}Address')
                    if address is not None:
                        streetaddress = extension.find(f'{uri}StreetAddress')
                        if streetaddress is not None:
                            wpt.addr = str.encode(streetaddress.text)
                        city = extension.find(f'{uri}City')
                        if city is not None:
                            wpt.city = str.encode(city.text)
                        state = extension.find(f'{uri}State')
                        if state and len(state) == 2:
                            wpt.state = str.encode(state.text)
                        country = extension.find(f'{uri}Country')
                        if country is not None and len(country) == 2:
                            wpt.cc = str.encode(country.text)
                waypoints.append(wpt)
        return waypoints

class GarminRoutes(Garmin):

    def __init__(self, xml_or_file, datatypes):
        self.routes = self.gpx_to_routes(xml_or_file, datatypes)

    def gpx_to_routes(self, xml_or_file, datatypes):
        gpx = gpxpy.parse(xml_or_file)
        routes = []
        if gpx.routes:
            for route in gpx.routes:
                if issubclass(datatypes[0], mod_datatype.RteHdr):
                    rte_hdr = datatypes[0]()
                    point_type = datatypes[1]
                    mod_logger.log.info(f"Adding route {route.name}")
                    rte_hdr.ident = str.encode(route.name)
                    extension = next((extension for extension in route.extensions if extension.tag.endswith('RouteExtension')), None)
                    if extension is not None:
                        uri = extension.tag.rstrip('RouteExtension')
                        displaycolor = extension.find(f'{uri}DisplayColor')
                        if displaycolor is not None:
                            color = self._display_color.get(displaycolor.text)
                    rte_hdr.pack()
                    routes.append([rte_hdr])
                else:
                    point_type = datatypes[0]
                    routes.append([])
                points = []
                for point in route.points:
                    rte_wpt = point_type()
                    degree_posn = mod_datatype.DegreePosition(point.latitude, point.longitude)
                    posn = degree_posn.as_semicircles()
                    rte_wpt.posn = (posn.lat, posn.lon)
                    if point.has_elevation():
                        rte_wpt.alt = point.elevation
                    if point.time is not None:
                        point_time = mod_datatype.Time()
                        point_time.set_datetime(point.time)
                        if point_time.is_valid():
                            rte_wpt.time = point_time.time
                    mod_logger.log.info(f"Adding waypoint {point.name}")
                    rte_wpt.ident = str.encode(point.name)
                    if point.comment is not None:
                        rte_wpt.cmnt = str.encode(point.comment)
                    if 'color' in vars():
                        rte_wpt.set_color(color)
                    if point.symbol is not None:
                        symbol = self._symbol.get(point.symbol)
                        point_symbol = mod_datatype.Symbol()
                        point_symbol.set_smbl(symbol)
                        rte_wpt.smbl = point_symbol.smbl
                    extension = next((extension for extension in point.extensions if extension.tag.endswith('RoutePointExtension')), None)
                    if extension is not None:
                        uri = extension.tag.rstrip('RoutePointExtension')
                        subclass = extension.find(f'{uri}Subclass')
                        if subclass is not None:
                            rte_wpt.subclass = bytes.fromhex(subclass.text)
                    points.append(rte_wpt)
        elif gpx.tracks:
            for track in gpx.tracks:
                if issubclass(datatypes[0], mod_datatype.TrkHdr):
                    mod_logger.log.info(f"{datatypes[0]}, {mod_datatype.TrkHdr}")
                    rte_hdr = datatypes[0]()
                    point_type = datatypes[1]
                    mod_logger.log.info(f"Adding route {track.name}")
                    rte_hdr.ident = str.encode(track.name)
                    extension = next((extension for extension in track.extensions if extension.tag.endswith('TrackExtension')),None)
                    if extension is not None:
                        uri = extension.tag.rstrip('TrackExtension')
                        displaycolor = extension.find(f'{uri}DisplayColor')
                        if displaycolor is not None:
                            color = self._display_color.get(displaycolor)
                    rte_hdr.pack()
                    routes.append([rte_hdr])
                else:
                    point_type = datatypes[0]
                    routes.append([])
                points = []
                for segment in track.segments:
                    for idx, point in enumerate(segment.points):
                        mod_logger.log.info(f"Adding waypoint {idx}")
                        rte_wpt = point_type()
                        degree_posn = mod_datatype.DegreePosition(point.latitude, point.longitude)
                        posn = degree_posn.as_semicircles()
                        rte_wpt.posn = (posn.lat, posn.lon)
                        if point.has_elevation():
                            rte_wpt.alt = point.elevation
                        if point.time is not None:
                            point_time = mod_datatype.Time()
                            point_time.set_datetime(point.time)
                            if point_time.is_valid():
                                rte_wpt.time = point_time.time
                        extension = next((extension for extension in point.extensions if extension.tag.endswith('TrackPointExtension')), None)
                        if extension is not None:
                            uri = extension.tag.rstrip('TrackPointExtension')
                            temperature = extension.find(f'{uri}Temperature') or extension.find(f'{uri}atemp')
                            if temperature is not None:
                                trk_point.temp = float(temperature.text)
                            depth = extension.find(f'{uri}Depth') or extension.find(f'{uri}depth')
                            if depth is not None:
                                rte_wpt.dpth = depth
                        points.append(rte_wpt)
        # The A201 route transfer protocol adds an undocumented proprietary
        # waypoint link between waypoints
        if any([issubclass(datatype, mod_datatype.RteLink) for datatype in datatypes]):
            rte_link = datatypes[2]()
            mod_logger.log.info(f"Linking waypoints")
            points = list(self.join(points, rte_link))
        routes[-1].extend(points)
        return routes


class GarminTracks(Garmin):

    def __init__(self, xml_or_file, datatypes):
        self.tracks = self.gpx_to_tracks(xml_or_file, datatypes)

    def gpx_to_tracks(self, xml_or_file, datatypes):
        gpx = gpxpy.parse(xml_or_file)
        tracks = []
        if gpx.tracks:
            for idx, track in enumerate(gpx.tracks):
                if issubclass(datatypes[0], mod_datatype.TrkHdr):
                    trk_hdr = datatypes[0]()
                    point_type = datatypes[1]
                    if track.name:
                        mod_logger.log.info(f"Adding track {track.name}")
                        trk_hdr.ident = str.encode(track.name)
                        trk_hdr.trk_ident = str.encode(track.name)
                    else:
                        mod_logger.log.info(f"Adding track {idx}")
                    trk_hdr.index = idx
                    trk_hdr.pack()
                    tracks.append([trk_hdr])
                else:
                    point_type = datatypes[0]
                    tracks.append([])
                extension = next((extension for extension in track.extensions if extension.tag.endswith('TrackExtension')),None)
                if extension:
                    uri = extension.tag.rstrip('TrackExtension')
                    displaycolor = extension.find(f'{uri}DisplayColor')
                    if displaycolor is not None:
                        color = self._display_color.get(displaycolor.text)
                points = []
                for segment in track.segments:
                    for idx, point in enumerate(segment.points):
                        mod_logger.log.info(f"Adding track point {idx}")
                        trk_point = point_type()
                        degree_posn = mod_datatype.DegreePosition(point.latitude, point.longitude)
                        posn = degree_posn.as_semicircles()
                        trk_point.posn = (posn.lat, posn.lon)
                        if point.has_elevation():
                            trk_point.alt = point.elevation
                        if point.time is not None:
                            point_time = mod_datatype.Time()
                            point_time.set_datetime(point.time)
                            if point_time.is_valid():
                                trk_point.time = point_time.time
                        if 'color' in vars():
                            trk_point.set_color(color)
                        extension = next((extension for extension in point.extensions if extension.tag.endswith('TrackPointExtension')), None)
                        if extension is not None:
                            uri = extension.tag.rstrip('TrackPointExtension')
                            temperature = extension.find(f'{uri}Temperature') or extension.find(f'{uri}atemp')
                            if temperature is not None:
                                trk_point.temp = float(temperature.text)
                            depth = extension.find(f'{uri}Depth') or extension.find(f'{uri}depth')
                            if depth is not None:
                                trk_point.dpth = float(depth.text)
                            hr = extension.find(f'{uri}hr')
                            if hr is not None:
                                trk_point.heart_rate = int(hr.text)
                            cad = extension.find(f'{uri}cad')
                            if cad is not None:
                                trk_point.cadence = int(cad.text)
                        trk_point.pack()
                        points.append(trk_point)
                tracks[-1].extend(points)
            return tracks
