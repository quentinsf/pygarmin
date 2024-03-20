from datetime import date, datetime, timedelta, timezone
import math
import rawutil
import re
from . import logger as mod_logger


class DataType():
    """Base datatype.

    Datatypes must derive from the DataType base class. It uses the ``rawutil``
    module to pack and unpack binary data. Each subclass must define a _fields
    attribute. _fields must be a list of 2-tuples, containing a field name and a
    field type. The field type must be a ``rawutil`` `format character
    <https://github.com/Tyulis/rawutil#elements>`_.

    """
    byteorder = 'little'
    #: binary data
    data = bytes()
    #: ``datetime`` of 12:00 AM December 31, 1989 UTC
    epoch = datetime(1989, 12, 31, 0, 0, tzinfo=timezone.utc)
    #: regex matching upper-case letters and numbers
    re_upcase_digit = r'[A-Z0-9]'
    #: regex matching upper-case letters, numbers and space
    re_upcase_digit_space = r'[A-Z0-9 ]'
    #: regex matching upper-case letters, numbers, space and hyphen
    re_upcase_digit_space_hyphen = r'[A-Z0-9 _]'
    #: regex matching any ASCII character
    re_ascii = r'[\x20-\x7E]'

    @classmethod
    def get_keys(cls):
        """Return the list of keys of the structure fields.

        :return: list of _field keys
        :rtype: list[str]

        """
        keys = list(zip(*cls._fields))[0]
        return keys

    @classmethod
    def get_format(cls):
        """Return the format string of the structure fields.

        :return: ``rawutil`` format string
        :rtype: str

        """
        fmt_chars = list(zip(*cls._fields))[1]
        fmt = ' '.join(fmt_chars)
        return fmt

    @classmethod
    def get_struct(cls):
        """Return a ``rawutil.Struct`` object with the structure fields.

        :return: struct object
        :rtype: ``rawutil.Struct``

        """
        struct = rawutil.Struct(cls.get_format(),
                                names=cls.get_keys())
        struct.setbyteorder(cls.byteorder)
        return struct

    def get_dict(self):
        """Return a dictionary with the datatype properties.

        :return: dictionary with datatype properties
        :rtype: dict
        """
        keys = self.get_keys()
        return {key: self.__dict__.get(key) for key in keys}

    def get_values(self):
        """Return the list of values of the datatype properties.

        :return: list of values
        :rtype: list

        """
        return list(self.get_dict().values())

    def get_data(self):
        """Return the packed data.

        :return: packed data
        :rtype: bytes

        """

        return self.data

    def unpack(self, data):
        """Unpack binary data according to the structure.

        :param data: binary data
        :type data: bytes
        :return: None

        """
        struct = self.get_struct()
        values = struct.unpack(data)
        self.data = data
        self.__dict__.update(values._asdict())

    def pack(self):
        """Pack the datatype properties in the format defined by the structure."""
        struct = self.get_struct()
        values = self.get_values()
        self.data = struct.pack(*values)

    def is_valid_charset(self, pattern, bytes):
        """Return whether the bytes string matches the regex pattern.

        :param pattern: regular expression
        :type pattern: str
        :param bytes: bytestring
        :type bytes: bytes
        :return: True if bytes matches pattern, otherwise False
        :rtype: bool

        """
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
        """Format the record to a string consisting of the tag and 3-digit number."""
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

        A waypoint is invalid if both the ``lat`` and ``lon`` members are equal to
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
    _epoch = datetime(1989, 12, 31, 0, 0, tzinfo=timezone.utc)  # 12:00 AM December 31, 1989 UTC
    _fields = [('time', 'I'),  # timestamp, invalid if 0xFFFFFFFF
               ]

    def __init__(self, time=4294967295):
        self.time = time

    def __str__(self):
        datetime = self.get_datetime()
        return str(datetime)

    def get_datetime(self):
        """Return a datetime object of the time.

        The ``time`` member indicates the number of seconds since 12:00 am
        December 31, 1989 UTC.

        A value of 0xFFFFFFFF (4294967295) indicates that the ``time`` member is
        unsupported or unknown.

        """
        if self.is_valid():
            delta = timedelta(seconds=self.time)
            return self._epoch + delta

    def set_datetime(self, datetime):
        delta = datetime - self._epoch
        self.time = round(delta.total_seconds())

    def is_valid(self):
        """Return whether the time is valid.

        A ``time`` value of 0xFFFFFFFF that this parameter is not supported or unknown.

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

    def __init__(self, smbl=18):
        self.smbl = smbl

    def __str__(self):
        return f'{self.get_smbl()}'

    def get_smbl(self):
        """Get the symbol."""
        return self._smbl.get(self.smbl, 'sym_wpt_dot')

    def set_smbl(self, symbol):
        """Set the symbol.

        If an invalid symbol is received, it will be substituted by a generic dot symbol.

        """
        smbl_value = next((key for key, item in self._smbl.items() if item == symbol), 18)
        self.smbl = smbl_value


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

    def __init__(self, ident=bytes(6), posn=[0, 0], cmnt=bytes(40)):
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

        A ``dst`` value of 1.0e25 indicates that this parameter is not supported or unknown.

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
        """Return the symbol value."""
        return _smbl.get(self.smbl)

    def get_dspl(self):
        """Return the display option."""
        return self._dspl.get(self.dspl, 'dspl_smbl_name')

    def set_dspl(self, dspl):
        """Set the display option.

        If an invalid display value is received, the value will be 'dspl_smbl_name'.

        """
        dspl_value = next((key for key, value in self._dspl.items() if value == dspl), 0)
        self.dspl = dspl_value


class D104(D101):
    _posn_fmt = Position.get_format()
    _smbl_fmt = Symbol.get_format()
    _fields = [('ident', '6s'),             # identifier
               ('posn', f'({_posn_fmt})'),  # position
               ('unused', 'I'),             # should be set to zero
               ('cmnt', '40s'),             # comment
               ('dst', 'f'),                # proximity distance (meters)
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
        """Return the display option."""
        return self._dspl.get(self.dspl, 'dspl_smbl_none')

    def set_dspl(self, dspl):
        """Set the display option.

        If an invalid display value is received, the value will be 'dspl_smbl_none'.

        """
        dspl_value = next((key for key, value in self._dspl.items() if value == dspl), 0)
        self.dspl = dspl_value


class D105(D101):
    _posn_fmt = Position.get_format()
    _smbl_fmt = Symbol.get_format()
    _fields = [('posn', f'({_posn_fmt})'),  # position
               ('smbl', f'{_smbl_fmt}'),    # symbol id
               ('wpt_ident', 'n'),          # waypoint identifier
               ]

    def __init__(self, wpt_ident=b'\x00', **kwargs):
        super().__init__(**kwargs)
        self.wpt_ident = wpt_ident


class D106(D101):
    _posn_fmt = Position.get_format()
    _smbl_fmt = Symbol.get_format()
    _fields = [('wpt_class', 'B'),          # class
               ('subclass', '13s'),         # subclass
               ('posn', f'({_posn_fmt})'),  # position
               ('smbl', f'{_smbl_fmt}'),    # symbol id
               ('wpt_ident', 'n'),          # waypoint identifier
               ('lnk_ident', 'n'),          # link identifier
               ]

    def __init__(self, wpt_class=0, subclass=bytes((0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)), wpt_ident=b'\x00', lnk_ident=b'\x00', **kwargs):
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
    _color = {0: 'clr_default_color',  # default waypoint color
              1: 'clr_red',            # red
              2: 'clr_green',          # green
              3: 'clr_blue',           # blue
              }

    def __init__(self, dst=0, color=0, **kwargs):
        super().__init__(**kwargs)
        self.dst = dst
        self.color = color

    def get_color(self):
        """Return the color."""
        return self._color.get(self.color, 'clr_default_color')

    def set_color(self, color):
        """Set the color."""
        color_value = next((key for key, value in self._color.items() if value == color), 0)
        self.set_color_value(color_value)

    def is_valid_dst(self):
        """Return whether the proximity distance is valid.

        A ``dst`` value of 1.0e25 indicates that this parameter is not supported or unknown.

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
               ('subclass', '18s'),         # subclass
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

    def __init__(self, wpt_class=0, color=255, attr=96, smbl=0, subclass=bytes((0, 0, 0, 0, 0, 0, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255)), alt=1.0e25, dpth=1.0e25, dist=1.0e25, state=bytes(2), cc=bytes(2), cmnt=b'\x00', facility=b'\x00', city=b'\x00', addr=b'\x00', cross_road=b'\x00', **kwargs):
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
        """Return the waypoint class value.

        if an invalid value is received, the value will be user_wpt.

        """
        return self._wpt_class.get(self.wpt_class, 'user_wpt')

    def get_color(self):
        """Return the color value."""
        return self._color.get(self.color, 'clr_default_color')

    def set_color(self, color):
        """Set the color.

        If an invalid color value is received, the value will be
        'clr_default_color'.

        """
        color_value = next((key for key, value in self._color.items() if value == color), 255)
        self.set_color_value(color_value)

    def get_symbol(self):
        return Symbol(self.smbl)

    def get_smbl(self):
        symbol = self.get_symbol()
        return symbol.get_smbl()

    def is_valid_alt(self):
        """Return whether the altitude is valid.

        A ``alt`` value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.alt:.1e}" == "1.0e+25"

    def is_valid_dpth(self):
        """Return whether the depth is valid.

        A ``dpth`` value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.dpth:.1e}" == "1.0e+25"

    def is_valid_dist(self):
        """Return whether the proximity distance is valid.

        A ``dist`` value of 1.0e25 indicates that this parameter is not supported or unknown.

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
               ('subclass', '18s'),         # subclass
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
              31: 'clr_default_color'
              }

    def __init__(self, dtyp=1, dspl_color=0, attr=112, ete=4294967295, **kwargs):
        super().__init__(**kwargs)
        self.dtyp = dtyp
        self.dspl_color = dspl_color
        self.attr = attr
        self.ete = ete

    # The ``dspl_color`` member contains three fields; bits 0-4 specify the color,
    # bits 5-6 specify the waypoint display attribute and bit 7 is unused and
    # must be 0.

    # The ``dspl_color`` member contains three fields; bits 0-4 specify the
    # color, bits 5-6 specify the waypoint display attribute and bit 7 is
    # unused and must be 0.
    def get_color(self):
        color_value = self.get_color_value()
        return self._color.get(color_value, 'clr_default_color')

    def get_color_value(self):
        """Return the color value."""
        bit_size = 5
        shift = 0
        mask = pow(2, bit_size) - 1
        color_value = self.dspl_color >> shift & mask
        return color_value

    def set_color(self, color):
        """Set the color.

        If an invalid color value is received, the value will be Black.

        """
        color_value = next((key for key, value in self._color.items() if value == color), 255)
        self.set_color_value(color_value)

    def set_color_value(self, value):
        """Set the color value."""
        bit_size = 5
        shift = 0
        color_value = value << shift
        self.dspl_color = self.get_dspl_value() + color_value

    def get_dspl(self):
        dspl_value = self.get_dspl_value()
        return self._dspl.get(dspl_value, 'dspl_smbl_none')

    def get_dspl_value(self):
        """Return the display attribute value."""
        bit_size = 2
        shift = 5
        mask = pow(2, bit_size) - 1
        dspl_value = self.dspl_color >> shift & mask
        return dspl_value

    def set_dspl(self, dspl):
        """Set the display option.

        If an invalid display value is received, the value will be 'dspl_smbl_name'.

        """
        dspl_value = next((key for key, value in self._dspl.items() if value == dspl), 0)
        self.set_dspl_value = dspl_value

    def set_dspl_value(self, value):
        """Set the display attribute value."""
        bit_size = 2
        shift = 5
        dspl_value = value << shift
        self.dspl_color = dspl_value + self.get_color_value()


class D110(D109):
    _smbl_fmt = Symbol.get_format()
    _posn_fmt = Position.get_format()
    _time_fmt = Time.get_format()
    _fields = [('dtyp', 'B'),               # data packet type (0x01 for D110)
               ('wpt_class', 'B'),          # class
               ('dspl_color', 'B'),         # display & color
               ('attr', 'B'),               # attributes (0x80 for D110)
               ('smbl', f'{_smbl_fmt}'),    # symbol id
               ('subclass', '18s'),         # subclass
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
    _dspl = {0: 'dspl_smbl_name',
             1: 'dspl_smbl_only',
             2: 'dspl_smbl_comment',
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
        return self._wpt_class.get(self.wpt_class, 'user_wpt')

    def get_color(self):
        color_value = self.get_color_value()
        return self._color.get(color_value, 'clr_black')

    def get_dspl(self):
        dspl_value = self.get_dspl_value()
        return self._dspl.get(dspl_value, 'dspl_smbl_none')

    def get_datetime(self):
        return Time(self.time).get_datetime()

    def get_wpt_cat(self):
        """Return a list of waypoint categories.

        The ``wpt_cat`` member contains 16 bits that provide category membership
        information for the waypoint. If a bit is set then the waypoint is a
        member of the corresponding category.

        """
        bits = [(self.wpt_cat >> bit) & 1 for bit in range(16)]
        categories = [bool(bit) for bit in bits]
        return categories

    def is_valid(self):
        """Return whether the waypoint is valid.

        A waypoint is invalid if the ``lat`` member of the ``posn`` member contains
        a value greater than 2^30 or less than -2^30

        """
        return not self.posn.lat > 2**30 or self.posn.lat < -2**30

    def is_valid_temp(self):
        """Return whether the temperature is valid.

        A ``temp`` value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.temp:.1e}" == "1.0e+25"

    def is_valid_time(self):
        """Return whether the time is valid.

        A ``time`` value of 0xFFFFFFFF that this parameter is not supported or unknown.

        """
        return not self.time == 4294967295


class WptCat(DataType):

    def is_valid(self):
        """Return whether the waypoint category is valid.

        A waypoint category is invalid if the ``name`` member contains a value
        with a null byte in the first character.

        """
        self.name[0] != 0


class D120(WptCat):
    _fields = [('name', '17s'),  # category name
               ]

    def __init__(self, name=bytes(17)):
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

    def __init__(self, ident=bytes(6), cc=bytes(2), wpt_class=0, posn=[0, 0],
                 alt=1.0e25, city=bytes(24), state=bytes(2), facility=bytes(30),
                 cmnt=bytes(40)):
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
        return self._wpt_class.get(self.wpt_class, 'user_wpt')


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

    def __init__(self, dst=0, name=bytes(30), **kwargs):
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
        """Return the display option."""
        return self._dspl.get(self.dspl, 'dspl_smbl_only')


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

    def __init__(self, nmbr=0, cmnt=bytes(20)):
        self.nmbr = nmbr
        self.cmnt = cmnt


class D202(RteHdr):
    _fields = [('ident', 'n'),  # identifier
               ]

    def __init__(self, ident=b'\x00'):
        self.ident = ident


class RteLink(DataType):

    def is_valid_ident(self):
        pattern = self.re_upcase_digit_space_hyphen
        self.is_valid_charset(pattern, self.ident)


class D210(RteLink):
    _fields = [('lnk_class', 'H'),   # link class
               ('subclass', '18s'),  # subclass
               ('ident', 'n'),       # identifier
               ]
    _lnk_class = {0:   'line',
                  1:   'link',
                  2:   'net',
                  3:   'direct',
                  255: 'snap'}

    def __init__(self, lnk_class=0, subclass=bytes((0, 0, 0, 0, 0, 0, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255)), ident=b'\x00'):
        self.lnk_class = lnk_class
        self.subclass = subclass
        self.ident = ident

    def get_lnk_class(self):
        """Return the link class value."""
        return self._lnk_class.get(self.lnk_class, 'line')


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

        A ``alt`` value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.alt:.1e}" == "1.0e+25"

    def is_valid_dpth(self):
        """Return whether the depth is valid.

        A ``dpth`` value of 1.0e25 indicates that this parameter is not supported or unknown.

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

        A ``alt`` value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.alt:.1e}" == "1.0e+25"

    def is_valid_dpth(self):
        """Return whether the depth is valid.

        A ``dpth`` value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.dpth:.1e}" == "1.0e+25"

    def is_valid_temp(self):
        """Return whether the temperature is valid.

        A ``temp`` value of 1.0e25 indicates that this parameter is not supported or unknown.

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

        A ``alt`` value of 1.0e25 indicates that this parameter is not supported or unknown.

        """
        return not f"{self.alt:.1e}" == "1.0e+25"

    def is_valid_heart_rate(self):
        """Return whether the heart rate is valid.

        A ``heart_rate`` value of 0 indicates that this parameter is not supported or unknown.

        """
        return not self.heart_rate == 0


class D304(D303):
    _posn_fmt = Position.get_format()
    _time_fmt = Time.get_format()
    _fields = [('posn', f'({_posn_fmt})'),  # position
               ('time', f'{_time_fmt}'),    # time, invalid if 0xFFFFFFFF
               ('alt', 'f'),                # altitude in meters, invalid if 1.0e25
               ('distance', 'f'),           # distance traveled in meters, invalid if 1.0e25
               ('heart_rate', 'B'),         # heart rate in beats per minute, invalid if 0
               ('cadence', 'B'),            # in revolutions per minute, invalid if 0xFF
               ('sensor', '?'),             # is a wheel sensor present?
               ]

    def __init__(self, distance=1.0e25, heart_rate=0, cadence=255, sensor=False, **kwargs):
        super().__init__(**kwargs)
        self.distance = distance
        self.heart_rate = heart_rate
        self.cadence = cadence
        self.sensor = sensor

    def is_valid_distance(self):
        """Return whether the distance is valid.

        A ``distance`` value of 1.0e25, indicating that it is invalid.

        """
        return not f"{self.distance:.1e}" == "1.0e+25"

    def is_valid_cadence(self):
        """Return whether the cadence is valid.

        A ``cadence`` value of 0xFF indicates that this parameter is not supported or unknown.

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

    def __init__(self, dspl=True, color=255, trk_ident=b'\x00'):
        self.dspl = dspl
        self.color = color
        self.trk_ident = trk_ident

    def get_color(self):
        """Return the color value."""
        return self._color.get(self.color, 'clr_default_color')


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
              255: 'clr_default_color',
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

        The ``svid`` member identifies a satellite in the GPS constellation as
        follows: PRN-01 through PRN-32 are indicated by ``svid`` equal to 0
        through 31, respectively.

        """
        return self.svid + 1


class D551(D501):
    _fields = [('svid', 'B')  # satellite id
               ] + D501._fields

    def get_prn(self):
        """Return the PRN.

        The ``svid`` member identifies a satellite in the GPS constellation as
        follows: PRN-01 through PRN-32 are indicated by ``svid`` equal to 0
        through 31, respectively.

        """
        return self.svid + 1


class DateTime(DataType):
    def get_datetime(self):
        """Return a datetime object of the time."""
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
        m = re.search(pattern, product_description)
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

        To find the altitude above mean sea level, add ``msl_hght`` (height of the
        WGS 84 ellipsoid above mean sea level) to ``alt`` (altitude above the WGS
        84 ellipsoid).

        """
        return self.msl_hght + self.alt

    def get_datetime(self):
        """Return a datetime object of the time."""
        seconds = math.floor(self.tow - self.leap_scnds)
        days = self.wn_days
        delta = timedelta(days=days, seconds=seconds)
        return self.epoch + delta

    def get_fix(self, product_description=None):
        """Return the fix value.

        The default enumerated values for the ``fix`` member of the D800 PVT are
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


class D900(DataType):
    """Undocumented unlock code communication datatype."""


class Lap(DataType):
    _intensity = {0: 'active',  # This is a standard, active lap
                  1: 'rest',    # This is a rest lap in a workout
                  }

    def get_start_datetime(self):
        return Time(self.start_time).get_datetime()

    def get_begin(self):
        return Position(*self.begin)

    def get_end(self):
        return Position(*self.end)

    def is_valid_avg_heart_rate(self):
        """Return whether the cadence is valid.

        A ``avg_heart_rate`` value of 0 indicates that this parameter is not supported or unknown.

        """
        return not self.avg_heart_rate == 0

    def is_valid_max_heart_rate(self):
        """Return whether the cadence is valid.

        A ``max_heart_rate`` value of 0 indicates that this parameter is not supported or unknown.

        """
        return not self.max_heart_rate == 0

    def is_valid_avg_cadence(self):
        """Return whether the average cadence is valid.

        A ``cadence`` value of 0xFF indicates that this parameter is not supported or unknown.

        """
        return not self.avg_cadence == 255

    def get_intensity(self):
        return self._intensity.get(self.intensity)


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

class D907(DataType):
    """Undocumented datatype."""


class D908(DataType):
    """Undocumented datatype."""


class D909(DataType):
    """Undocumented datatype."""


class D910(DataType):
    """Undocumented datatype."""


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

    _intensity = {0: 'active',  # This is a standard, active lap
                  1: 'rest',    # This is a rest lap in a workout
                  }
    _duration_type = {0: 'time',                     # In seconds
                      1: 'distance',                 # In meters
                      2: 'heart rate less than',     # A value from 0 – 100
                                                     # indicates a percentage of
                                                     # max heart rate. A value
                                                     # above 100 indicates
                                                     # beats-per-minute (255
                                                     # max) plus 100.
                      3: 'heart rate greater than',  # A value from 0 – 100
                                                     # indicates a percentage of
                                                     # max heart rate. A value
                                                     # above 100 indicates
                                                     # beats-per-minute (255
                                                     # max) plus 100.
                      4: 'calories burned',          # In calories
                      5: 'open',                     # Undefined
                      6: 'repeat',                   # Number of the step to
                                                     # loop back to. Steps are
                                                     # assumed to be in the
                                                     # order in which they are
                                                     # received, and are
                                                     # numbered starting at one.
                                                     # The ``custom_name`` and
                                                     # ``intensity`` members are
                                                     # undefined for this
                                                     # duration type.
                      }

    _target_type = {0: 'speed',
                    1: 'heart rate',
                    2: 'open',
                    3: 'cadence',     # The cadence target type is only
                                      # available in the D1008 datatype
                    }

    def __init__(self, custom_name=bytes(16), target_custom_zone_low=0,
                 target_custom_zone_high=0, duration_value=0, intensity=0,
                 duration_type=0, target_type=0, target_value=0, unused=0):
        self.custom_name = custom_name
        self.target_custom_zone_low = target_custom_zone_low
        self.target_custom_zone_high = target_custom_zone_high
        self.duration_value = duration_value
        self.intensity = intensity
        self.duration_type = duration_type
        self.target_type = target_type
        self.target_value = target_value
        self.unused = unused

    def get_custom_name(self):
        values = rawutil.unpack('<n', self.custom_name)
        name = values[0].decode('ascii')
        return name

    def get_intensity(self):
        return self._intensity.get(self.intensity)

    def get_duration_type(self):
        return self._duration_type.get(self.duration_type)

    def get_target_type(self):
        return self._target_type.get(self.target_type)

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

    def get_sport_type(self):
        return self._sport_type.get(self.sport_type)

    def get_program_type(self):
        return self._program_type.get(self.program_type)


class VirtualPartner(DataType):
    _time_fmt = Time.get_format()
    _fields = ([('time', f'{_time_fmt}'),  # Time result of virtual partner
                ('distance', 'f'),         # Distance result of virtual partner
                ])

    def get_datetime(self):
        return Time(self.time).get_datetime()


class QuickWorkout(DataType):
    _fields = [('time', 'I'),      # Time result of quick workout
               ('distance', 'f'),  # Distance result of quick workout
               ]

    def __init__(self, time=0, distance=0):
        self.time = time
        self.distance = distance


class Workout(DataType):
    _step_fmt = Step.get_format()
    _fields = [('num_valid_steps', 'I'),       # Number of valid steps (1-20)
               ('steps', f'20[{_step_fmt}]'),  # Steps
               ('name', '16s'),                # Null-terminated workout name
               ('sport_type', 'B'),            # Same as D1000
               ]
    _sport_type = {0: 'running',
                   1: 'biking',
                   2: 'other',
                   }

    def __init__(self, num_valid_steps=0, steps=[], name=bytes(16), sport_type=0):
        self.num_valid_steps = num_valid_steps
        self.steps = steps
        self.name = name
        self.sport_type = sport_type

    def get_steps(self):
        return [ Step(*step) for step in self.steps ]

    def get_name(self):
        values = rawutil.unpack('<n', self.name)
        name = values[0].decode('ascii')
        return name

    def get_sport_type(self):
        return self._sport_type.get(self.sport_type)


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
               ('max_speed', 'f'),              # In meters per second
               ('begin', f'({_posn_fmt})'),     # Invalid if both lat and lon are 0x7FFFFFFF
               ('end', f'({_posn_fmt})'),       # Invalid if both lat and lon are 0x7FFFFFFF
               ('calories', 'H'),               # Calories burned this lap
               ('avg_heart_rate', 'B'),         # In beats-per-minute, invalid if 0
               ('max_heart_rate', 'B'),         # In beats-per-minute, invalid if 0
               ('intensity', 'B'),
               ]


class D1002(Workout):
    pass


class WorkoutOccurrence(DataType):
    _fields = [('workout_name', '16s'),  # Null-terminated workout name
               ('day', 'I'),             # Day on which the workout falls
               ]


class D1003(WorkoutOccurrence):
    _fields = WorkoutOccurrence._fields


class HeartRateZone(DataType):
    _fields = [('low_heart_rate', 'B'),   # In beats-per-minute, must be > 0
               ('high_heart_rate', 'B'),  # In beats-per-minute, must be > 0
               ('unused', 'H'),           # Unused. Set to 0.
               ]

    def __init__(self, low_heart_rate=0, high_heart_rate=0, unused=0):
        self.low_heart_rate = low_heart_rate
        self.high_heart_rate = high_heart_rate


class SpeedZone(DataType):
    _fields = [('low_speed', 'f'),   # In meters-per-second
               ('high_speed', 'f'),  # In meters-per-second
               ('name', '16s'),      # Null-terminated speed-zone name
               ]

    def __init__(self, low_speed=0, high_speed=0, name=bytes(16)):
        self.low_speed = low_speed
        self.high_speed = high_speed

class Activity(DataType):
    _heart_rate_zone_fmt = HeartRateZone.get_format()
    _speed_zone_fmt = SpeedZone.get_format()
    _fields = [('heart_rate_zones', f'5[{_heart_rate_zone_fmt}]'),
               ('speed_zones', f'10[{_speed_zone_fmt}]'),
               ('gear_weight', 'f'),                                # Weight of equipment in kilograms
               ('max_heart_rate', 'B'),                             # In beats-per-minute, must be > 0
               ('unused1', 'B'),                                    # Unused. Set to 0.
               ('unused2', 'H'),                                    # Unused. Set to 0.
               ]

    def __init__(self,
                 heart_rate_zones=[[93, 111, 0],
                                   [111, 130, 0],
                                   [130, 148, 0],
                                   [148, 167, 0],
                                   [167, 185, 0]],
                 speed_zones=[[0.6705600023269653, 1.3410999774932861, b'Snail\x00\x00\x00\xb4\xd6!\x00i\xa0\x10\x04'],
                              [1.3410999774932861, 1.6763999462127686, b'Turtle\x00\x00\xa8\x00"\x00B\x00\x00\x00'],
                              [1.6763999462127686, 2.4384000301361084, b'Squirrel\x00\x00\x00\x00\xb4\xd6!\x00'],
                              [2.4384000301361084, 3.829900026321411, b'Elephant\x00\x00\x00\x00\xf8\x00!\x00'],
                              [3.829900026321411, 4.0, b'Rabbit\x00\x04G\x9a\x10\x04\x14\x00\x00\x00'],
                              [4.0, 5.0, b'Greyhound\x00\x00\x00?g\x10\x04'],
                              [5.0, 6.0, b'Horse\x00!\x00\xf8\x00\x00\x000\xd7!\x00'],
                              [6.0, 7.0, b'Lion\x00\xd7!\x00\x0c\x00\x00\x00\xf8\x00\x00\x00'],
                              [7.0, 8.0, b'Antelope\x00/A\x00\xff\x00\x00\x00'],
                              [8.0, 9.0, b'Cheetah\x00runnB\x00\x00\x00']],
                 gear_weight=0.0, max_heart_rate=0, unused1=0, unused2=0):
        self.heart_rate_zones = heart_rate_zones
        self.speed_zones = speed_zones
        self.gear_weight = gear_weight
        self.max_heart_rate = max_heart_rate

    def get_heart_rate_zones(self):
        return [ HeartRateZone(*heart_rate_zone) for heart_rate_zone in self.heart_rate_zones ]

    def get_speed_zones(self):
        return [ SpeedZone(*speed_zone) for speed_zone in self.speed_zones ]


class FitnessUserProfile(DataType):
    _activity_fmt = Activity.get_format()
    _fields = [('activities', f'3[{_activity_fmt}]'),
               ('weight', 'f'),                        # User’s weight, in kilograms
               ('birth_year', 'H'),                    # No base value (i.e. 1990 means 1990)
               ('birth_month', 'B'),                   # 1 = January, etc.
               ('birth_day', 'B'),                     # 1 = first day of month, etc.
               ('gender', 'B'),                        # See below
               ]
    _gender = {0: 'female',
               1: 'male',
               }

    def get_activities(self):
        return [ Activity(*activity) for activity in self.activities ]

    def get_birth_date(self):
        return date(self.birth_year, self.birth_month, self.birth_day)

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
    _fields = [('index', 'H'),          # Unique among courses on device
               ('unused', 'H'),         # Unused. Set to 0.
               ('course_name', '16s'),  # Null-terminated, unique course name
               ('track_index', 'H'),    # Index of the associated track
               ]

    def get_course_name(self):
        values = rawutil.unpack('<n', self.course_name)
        name = values[0].decode('ascii')
        return name


class D1006(Course):
    pass


class CourseLap(DataType):
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
    _intensity = {0: 'active',  # This is a standard, active lap
                  1: 'rest',    # This is a rest lap in a workout
                  }

    def get_begin(self):
        return Position(*self.begin)

    def get_end(self):
        return Position(*self.end)

    def get_intensity(self):
        return self._intensity.get(self.intensity)

    def is_valid_avg_heart_rate(self):
        """Return whether the cadence is valid.

        A ``avg_heart_rate`` value of 0 indicates that this parameter is not supported or unknown.

        """
        return not self.avg_heart_rate == 0

    def is_valid_max_heart_rate(self):
        """Return whether the cadence is valid.

        A ``max_heart_rate`` value of 0 indicates that this parameter is not supported or unknown.

        """
        return not self.max_heart_rate == 0

    def is_valid_avg_cadence(self):
        """Return whether the average cadence is valid.

        A ``cadence`` value of 0xFF indicates that this parameter is not supported or unknown.

        """
        return not self.avg_cadence == 255


class D1007(CourseLap):
    pass


class D1008(Workout):
    pass


class D1009(Run):
    _quickworkout_fmt = QuickWorkout.get_format()
    _workout_fmt = Workout.get_format()
    _fields = [('track_index', 'H'),      # Index of associated track
               ('first_lap_index', 'H'),  # Index of first associated lap
               ('last_lap_index', 'H'),   # Index of last associated lap
               ('sport_type', 'B'),       # Same as D1000
               ('program_type', 'B'),     # See below
               ('multisport', 'B'),       # See below
               ('unused1', 'B'),          # Unused. Set to 0.
               ('unused2', 'H'),          # Unused. Set to 0.
               ('quick_workout', f'({_quickworkout_fmt})'),
               ('workout', f'({_workout_fmt})'),
               ]
    _multisport = {0: 'no',                 # Not a MultiSport run
                   1: 'yes',                # Part of a MultiSport session
                   2: 'yesAndLastInGroup',  # The last of a MultiSport session
                   }

    def get_track_index(self):
        """Return the track_index.

        The value of the ``track_index`` member must be 0xFFFF if there is no
        associated track.

        """
        return self.track_index if self.track_index != 65535 else None

    def get_quick_workout(self):
        return QuickWorkout(*self.quick_workout)

    def get_workout(self):
        return Workout(*self.workout)

    # The ``program_type`` member is a bit field that indicates the type of run
    # this is. The following table describes the meaning of each bit:

    # ============================= ===========================================
    #  Bit                           Interpretation
    # ============================= ===========================================
    #  0 (least significant bit)     This is a virtual partner run
    #  1                             This is associated with a workout
    #  2                             This is a quick workout
    #  3                             This is associated with a course
    #  4                             This is an interval workout
    #  5                             This is part of an auto-MultiSport session
    #  6-7 (most significant bits)   Undefined. Set to 0.
    # ============================= ===========================================

    # If the ``program_type`` member indicates that this run is associated with
    # a course, then the ``workout`` member contains the name of the associated
    # course in its ``name`` field.

    def is_virtual_partner_run(self):
        """Return whether the virtual partner bit is set."""
        shift = 0
        mask = 1
        bit = self.program_type >> shift & mask
        return bool(bit)

    def has_workout(self):
        """Return whether the workout bit is set."""
        shift = 1
        mask = 1
        bit = self.program_type >> shift & mask
        return bool(bit)

    def is_quick_workout(self):
        """Return whether the quick workout bit is set."""
        shift = 2
        mask = 1
        bit = self.program_type >> shift & mask
        return bool(bit)

    def has_course(self):
        """Return whether the course bit is set."""
        shift = 3
        mask = 1
        bit = self.program_type >> shift & mask
        return bool(bit)

    def is_interval_workout(self):
        """Return whether the interval workout bit is set."""
        shift = 4
        mask = 1
        bit = self.program_type >> shift & mask
        return bool(bit)

    def is_auto_multisport(self):
        """Return whether the auto MultiSport bit is set.

        If the ``auto MultiSport`` bit is set in the ``program_type`` member,
        and if the last lap in the run is a rest lap, then that last lap’s time
        represents the time during which the user was transitioning to the next
        sport.

        """
        shift = 5
        mask = 1
        bit = self.program_type >> shift & mask
        return bool(bit)

    def get_multisport(self):
        """Return the multisport value."""
        return self._multisport.get(self.multisport)


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

    def get_name(self):
        values = rawutil.unpack('<n', self.name)
        name = values[0].decode('ascii')
        return name

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

class D1015(D1011):
    """Undocumented datatype."""
    _fields = D1011._fields + [('unknown', '(5B)')]  # unknown additional bytes


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
            mod_logger.log.debug(f"Record 'F': Product")
            datatype = MapProduct()
        elif type == 'map_segment_id':
            mod_logger.log.debug(f"Record 'L': Map segment")
            datatype = MapSegment()
        elif type == 'map_unknown_id':
            mod_logger.log.debug(f"Record 'P': Unknown")
            datatype = MapUnknown()
        elif type == 'map_unlock_id':
            mod_logger.log.debug(f"Record 'U': Unlock")
            datatype = MapUnlock()
        elif type == 'map_set_id':
            mod_logger.log.debug(f"Record 'V': Mapset")
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
    (bpp). The alpha channel is unused. Instead, a color is used for
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

    def get_bytearray(self):
        """Return the color as bytearray."""
        return bytearray([self.red, self.green, self.blue])

    def get_rgb(self):
        """Return an RGB tuple."""
        return (self.red, self.green, self.blue)


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
               ('height', 'H'),              # height in pixels
               ('width', 'H'),               # width in pixels
               ('bytewidth', 'H'),           # width in bytes
               ('unknown3', 'H'),
               ('color', f'({_rgba_fmt})'),  # transparent color
               )

    def get_dimensions(self):
        return (self.width, self.height)

    def get_size(self):
        return (self.bpp * self.width * self.height) // 8

    def get_row_size(self):
        return (self.width * self.bpp // 8)

    def get_bytesize(self):
        return (self.bytewidth * self.height)

    def get_colors_used(self):
        if self.bpp <= 8:
            return 1 << self.bpp
        elif self.bpp == 24:
            return 0

    def get_color(self):
        if any(x != 0 for x in self.color):
            return RGBA(*self.color)


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

    def __init__(self, id=0, colors=b''):
        self.id = id
        self.colors = colors

    def get_colors(self):
        return [ RGBA(*color) for color in self.colors ]

    def get_palette(self):
        """Returns the RGB color palette as a list of bytearray."""
        palette = [ color.get_bytearray() for color in self.get_colors() ]
        return palette


class ImageChunk(DataType):
    _id_fmt = ImageId.get_format()
    _fields = [('id', f'{_id_fmt}'),
               ('chunk', '$'),
               ]

    def __init__(self, id=0, chunk=b''):
        self.id = id
        self.chunk = chunk


class RGB(DataType):
    """RGB is a sRGB format that uses 24 bits of data per per pixel.

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

    def get_bytearray(self):
        """Return the color as bytearray."""
        return bytearray([self.red, self.green, self.blue])

    def get_rgb(self):
        """Return an RGB tuple."""
        return (self.red, self.green, self.blue)


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
    BMP files contain bitfields mask values in place of the color palette. 2-bit
    BMP files were added for Windows CE
    (http://fileformats.archiveteam.org/wiki/Pocket_PC_Bitmap), but are not well
    supported.

    The pixel array is a series of values representing either color palette
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
                 1: 'pixel_array',
                 2: 'color_table',
                }

    def get_section(self):
        return self._section.get(self.section)


class ScreenshotHeader(Screenshot):
    _fields = Screenshot._fields + [('bytewidth', 'I'),  # width in bytes
                                    ('bpp', 'I'),        # bits per pixel or color depth
                                    ('width', 'I'),      # width in pixels
                                    ('height', 'I'),     # height in pixels
                                    ('unknown2', '(12B)'),
                                    ]

    def get_dimensions(self):
        return (self.width, self.height)

    def get_size(self):
        return (self.bpp * self.width * self.height) // 8

    def get_row_size(self):
        return (self.width * self.bpp // 8)

    def get_bytesize(self):
        return (self.bytewidth * self.height)

    def get_colors_used(self):
        if self.bpp <= 8:
            return 1 << self.bpp
        elif self.bpp == 24:
            return 0


class ScreenshotColor(Screenshot):
    _rgb_fmt = RGB.get_format()
    _fields = Screenshot._fields + [('color', f'({_rgb_fmt})')]

    def get_color(self):
        return RGB(*self.color)


class ScreenshotChunk(Screenshot):
    _fields = Screenshot._fields + [('chunk', '$')]


class SatelliteRecord(DataType):
    _fields = [('svid', 'B'),    # space vehicle identification (1–32 and 33–64 for WAAS)
               ('snr', 'H'),     # signal-to-noise ratio
               ('elev', 'B'),    # satellite elevation in degrees
               ('azmth', 'H'),   # satellite azimuth in degrees
               ('status', 'B'),  # status bit-field
               ]

    def __init__(self, svid, snr, elev, azmth, status):
        self.svid = svid
        self.snr = snr
        self.elev = elev
        self.azmth = azmth
        self.status = status

    # The status bit field represents a set of booleans described below:

    # ===== ====================================================================
    #  Bit   Meaning when bit is one (1)
    # ===== ====================================================================
    #    0   The unit has ephemeris data for the specified satellite
    #    1   The unit has a differential correction for the specified satellite
    #    2   The unit is using this satellite in the solution
    #  ===== ====================================================================

    def has_eph(self):
        """Return whether the unit has ephemeris data for the specified satellite."""
        shift = 7
        mask = 1
        bit = self.status >> shift & mask
        return bool(bit)

    def has_diff(self):
        """Return whether the unit has a differential correction for the specified satellite."""
        shift = 6
        mask = 1
        bit = self.status >> shift & mask
        return bool(bit)

    def is_used(self):
        """Return whether the unit is using this satellite in the solution."""
        shift = 5
        mask = 1
        bit = self.status >> shift & mask
        return bool(bit)

    def get_prn(self):
        """Return the PRN.

        The ``svid`` member identifies a satellite in the GPS constellation as
        follows: PRN-01 through PRN-32 are indicated by ``svid`` equal to 0
        through 31, respectively.

        """
        return self.svid + 1


class Satellite(DataType):
    """Satellite datatype.

    The satellite records contain post-process information, such as position and velocity
    information.

    This datatype is undocumented in the spec, but it is described in the GPS
    16/17 Technical Specifications
    (https://static.garmin.com/pumac/470_GPS16_17TechnicalSpecification.pdf) and
    the GPS 18x Technical Specifications
    (https://static.garmin.com/pumac/GPS_18x_Tech_Specs.pdf).

    """
    _satellite_record_fmt = SatelliteRecord.get_format()
    _fields = [('records', f'12[{_satellite_record_fmt}]'),
               ]

    def __init__(self, records=None):
        self.records = records

    def get_records(self):
        return [ SatelliteRecord(*record) for record in self.records ]
