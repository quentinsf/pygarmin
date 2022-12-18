# PyGarmin

![PyGarmin](pygarmin.png)

PyGarmin is a set of Python classes for interfacing with (mostly older) Garmin
GPS equipment.

## Background

PyGarmin is a set of [Python](https://www.python.org/) classes which implement
the protocol used by [Garmin](https://www.garmin.com/) GPS receivers to talk to
each other and to other machines. It is based on the official [protocol
specification](https://www8.garmin.com/support/commProtocol.html). The project
was started by [Quentin
Stafford-Fraser](https://quentinsf.com/software/pygarmin/) but several others
have helped to make it what it is today.

PyGarmin has been used to transfer information to and from several different
Garmin receivers, mostly under Linux, though there is some Windows support now
and people have used it on Mac OS X as well. If you use PyGarmin, it will
probably be much quicker than writing your own software from scratch.

We suggest you read these docs first. The code looks quite scary if you don't
know what's happening, though it's actually pretty simple.

## Basics

Almost every model of Garmin receiver implements a slightly different protocol.
They have many things in common, but there are minor differences. For example,
some receivers can display icons, and they therefore transmit waypoints which
have an extra 'symbol' field, which is not used in other models. Others don't
use icons, but do store altitude. And so forth. You need to get the protocol
right for your particular model.

This makes matters more complicated, but at least these things are well
documented by Garmin. The [protocol
specification](https://www8.garmin.com/support/commProtocol.html) includes a big
table which details, for each product type, what protocol it uses for basic
commands, what it uses for downloading waypoints, what it uses for downloading
routes, and so forth.

I have created Python classes for each of the protocols listed in the spec, and
for each of the data types. Well, most of them. The big table becomes, in
Python, a mapping from the Garmin product ID to the set of relevant classes.
This means that, while there are a large number of classes defined in the
source, only a few of them will ever be used by any given receiver. The classes
are all given names based on those used in the specification, so look at the
spec if you want to know more about the classes.

The class `garmin.Garmin` will connect to your GPS, read its product ID and
software version, and then look up the appropriate classes in the table. It
creates instances of the protocol classes and notes the datatype classes for
each type of data used in the transmissions. It also has some friendly methods
like `get_waypoints()`, which do what you would expect. What you get back when
you call this is a list of objects, each of which is an instance of a class
derived from `garmin.Wpt`, but the precise type of the objects will depend on
the GPS you're talking to.

## Installation

Pygarmin makes use of the PySerial package for talking to serial ports. If you
don't have it already you can do a standard

    pip install -r requirements.txt

to get it.

You may also need to set suitable permissions on the serial port (e.g
/dev/ttyUSB0) that you're planning to use.

## Example Code

OK. Here's a simple Python program.

    #!/usr/bin/env python3
    import logging
    from garmin import garmin

    log = logging.getLogger('pygarmin')
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)

    # Create a 'physical layer' connection using serial port
    phys = garmin.SerialLink("/dev/ttyUSB0")

    # Create a Garmin object using this connection
    gps = garmin.Garmin(phys)

    # Get the waypoints from the GPS
    # (This may take a little while)
    waypoints = gps.get_waypoints()

    # Get the tracks from the GPS
    # (This may take a little while)
    tracks = gps.get_tracks()

    # Print the waypoints
    print("# Waypoints:")
    for waypoint in waypoints:
        posn = waypoint.get_posn()
        degrees = posn.as_degrees()
        lat = degrees.lat
        lon = degrees.lon
        print(waypoint.ident, lat, lon, waypoint.cmnt, waypoint.get_smbl())

    # Print the tracks
    print("# Tracks:")
    for track in tracks:
        print(track)

    # Put a new waypoint
    print("Upload a new waypoint:")
    waypoint = {'ident': 'CHURCH',
                'cmnt': 'LA SAGRADA FAMILIA',
                'posn': [493961671, 25937164],
                'smbl': 8236}
    gps.put_waypoints(waypoint)

This should work for most models, because all waypoints will have an identity, a
position (latitude and longitude), and a comment field. The latitude and
longitude are transferred as 'semicircle' coordinates (basically degrees, but
scaled to fill a signed long integer). The static method `Position.to_degrees()`
converts a semicircle integer into a degree float and the `as_degrees()` method
converts a Position into a DegreePosition data type.

## More details

There are 3 levels of protocol documented:
| Application    | (highest level) |
| Link layer     |                 |
| Physical layer | (lowest level)  |

The specification documents the various different versions of these under labels
of Pxxx, Lxxx, Axxx etc, where xxx is a number, and this convention is followed
in the code. There are also various data types, named Dxxx. Roughly speaking,
the Physical protocols specify RS232, the Link protocols specify a packet
structure for sending messages to and fro, and the Application protocols specify
what can actually go in those packets.

For example, a Garmin GPS 38 will talk to your computer over physical layer P000
(RS232) using a packet structure defined by link layer L001. If you want to
transfer waypoints to and from it, they will be sent using application layer
A100 (a waypoint transfer protocol), and the actual waypoints transferred will
be of type D100.

At the time of writing, the only documented physical layer is P000 which is
roughly RS232 at 9600 baud, 8 data bits, no parity, 1 stop bit. In the software,
we model this as a P000 class that has read and write methods, which can be used
by the higher protocol levels.

That should be enough to get you going.

## Licence

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, version 3.

## Acknowledgements

Thanks are due to, amongst others:

* [Quentin Stafford-Fraser](https://quentinsf.com/)
* James Skillen
* [Bjorn Tillenius](http://tillenius.me/)
* Hyrum K. Wright
* Cedric Dutoit

and probably others, to whom our apologies!

The logo was designed by [Quentin Stafford-Fraser](https://quentinsf.com/)
