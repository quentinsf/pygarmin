PyGarmin
========

.. figure:: pygarmin.png
   :alt: PyGarmin

The **Pygarmin** distribution provides a `Python <https://www.python.org/>`_
module and a command line application that implement the protocol used by
`Garmin <https://www.garmin.com/>`_ GPS devices. It is based on the official
`protocol specification <https://www8.garmin.com/support/commProtocol.html>`_.

Documentation
-------------

For API documentation, usage and examples see the files in the ``docs``
directory. The documentation is also hosted on `Read the Docs
<https://pygarmin.readthedocs.io/en/latest/>`_.

Installing
----------

You can install Pygarmin with ``pip`` as follows:

.. code-block:: console

   $ pip install pygarmin

Or to upgrade to the most recent version:

.. code-block:: console

   $ pip install pygarmin --upgrade

To follow or contribute to pygarmin development, you can browse or clone the Git
repository `on Github <https://github.com/quentinsf/pygarmin>`_:

.. code-block:: console

   $ git clone https://github.com/quentinsf/pygarmin.git

And install the requirements using the below command:

.. code-block:: console

   $ pip install -r requirements.txt

Pygarmin application
====================

Description
-----------

*Pygarmin* is a command line application that can retrieve data from and
transfer data to a Garmin GPS device connected by a serial or USB port.

The port is specified with the -p PORT option. To communicate with a Garmin GPS
serially, use the name of that serial port such as /dev/ttyUSB0, /dev/cu.serial,
or COM1. To communicate via USB use usb: as the port on all OSes. For this to
work on GNU/Linux, you probably should remove and blacklist the ``garmin_gps``
kernel module. Some protocols won't work at all with a serial connection, like
the transfer of images and maps. So your best bet is to use the internal USB
support.

The functionality is split into a number of sub-commands, like ``pygarmin info``
to return a product description, ``pygarmin get-waypoints`` to download the
waypoints, and ``pygarmin put-map`` to upload a new map.

Examples
--------

Show help message::

   pygarmin --help

Show help on the ``get-almanac`` command::

   pygarmin get-almanac -h

Show product description with debugging enabled::

   pygarmin --debug info

Show information on the currently installed maps, use the serial port and be very verbose::

   pygarmin -p /dev/ttyUSB0 -vv map

Download all waypoints in gpx format to the file waypoints.gpx::

   pygarmin get-waypoints waypoints.gpx -t gpx

Upload all waypoints in the file waypoints.gpx::

   pygarmin put-waypoints waypoints.gpx -t gpx

Download all activities in FIT format to the files activity001.fit to activityNNN.fit in the current directory::

   pygarmin get-activities -t fit activity%03d.fit

Print real-time position, velocity, and time (PVT) to stdout::

   pygarmin pvt -t tpv

List the images types::

   pygarmin get-image-types

List all images::

   pygarmin get-image-list

Download all images and save them according to the given filename pattern::

   pygarmin get-image ~/icons/waypoint%03d.png

Download the images with index 1, 2, and 3 and save them as PNG files with the default filenames to the current directory::

   pygarmin get-image -t png -i 1 2 3

Upload an image as a custom waypoint symbol with index 1, and don't show the progress bar::

   pygarmin --no-progress put-image Waypoint\ Symbol\ 000.bmp -i 1

Download the currently installed map from the device and save it as "*gmapsupp.img*" to the current directory::

   pygarmin get-map

Upload the map "*gmapsupp.img*"::

   pygarmin put-map gmapsupp.img


Garmin module
=============

The *garmin module* is a set of `Python <https://www.python.org/>`__ classes which
implement the protocol used by `Garmin <https://www.garmin.com/>`__ GPS
receivers to talk to each other and to other machines. It is based on the
official `protocol specification
<https://www8.garmin.com/support/commProtocol.html>`__. The project was started
by `Quentin Stafford-Fraser <https://quentinsf.com/software/pygarmin/>`__ but
several others have helped to make it what it is today.

PyGarmin has been used to transfer information to and from several different
Garmin receivers, mostly under Linux, though there is some Windows support now
and people have used it on Mac OS X as well. If you use PyGarmin, it will
probably be much quicker than writing your own software from scratch.

Basics
------

Almost every model of Garmin receiver implements a slightly different protocol.
They have many things in common, but there are minor differences. The class
``Garmin`` will create instances of the appropriate protocol classes and
notes the datatype classes for each type of data used in the transmissions. It
also has some friendly methods like ``get_waypoints()``, which do what you would
expect. What you get back when you call this is a list of objects, each of which
is a child the ``Wpt`` class.

Example Code
------------

Here’s a simple Python program:

.. code-block:: python

   #!/usr/bin/env python3
   import logging
   from garmin import garmin, link, logger

   logger.log.addHandler(logging.StreamHandler())
   logger.log.setLevel(logging.INFO)

   # Create a 'physical layer' connection using serial port
   phys = link.SerialLink('/dev/ttyUSB0')

   # ...or using USB
   phys = link.USBLink()

   # Create a Garmin object using this connection
   gps = garmin.Garmin(phys)

   # Get the waypoints from the GPS
   waypoints = gps.get_waypoints()

   # Get the tracks from the GPS
   tracks = gps.get_tracks()

   # Print the waypoints
   print("Waypoints:")
   for waypoint in waypoints:
       posn = waypoint.get_posn()
       degrees = posn.as_degrees()
       lat = degrees.lat
       lon = degrees.lon
       print(waypoint.ident, lat, lon, waypoint.cmnt)

   # Print the tracks
   print("Tracks:")
   for track in tracks:
       print(track)

   # Put a new waypoint
   print("Upload a new waypoint:")
   waypoints = [{'ident': b'CHURCH',
                 'cmnt': b'LA SAGRADA FAMILIA',
                 'posn': [493961671, 25937164]}]
   gps.put_waypoints(waypoints)

This should work for most models, because all waypoints will have an identity, a
position (latitude and longitude), and a comment field. The latitude and
longitude are transferred as ‘semicircle’ coordinates (basically degrees, but
scaled to fill a signed long integer). The static method
``Position.to_degrees()`` converts a semicircle integer into a degree float and
the ``as_degrees()`` method converts a Position into a DegreePosition data type.

License
=======

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, version 3.

In the past, it has been released under the GNU General Public License
version 2, and some contributions have been made under that license. You
may use it under the terms of the GPLv2 if you prefer.

Acknowledgements
================

Thanks are due to, amongst others:

-  `Quentin Stafford-Fraser <https://quentinsf.com/>`__
-  James Skillen
-  `Bjorn Tillenius <http://tillenius.me/>`__
-  Hyrum K. Wright
-  Cedric Dutoit
-  Folkert van der Beek (for a major rewrite in Dec 2022)

and probably others, to whom our apologies!

The logo was designed by `Quentin
Stafford-Fraser <https://quentinsf.com/>`__
