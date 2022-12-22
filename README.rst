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

To follow or contribute to emacs-zotero development, you can browse or clone the
Git repository `on Github <https://github.com/quentinsf/pygarmin>`_:

.. code-block:: console

   $ git clone https://github.com/quentinsf/pygarmin.git

And install the requirements using the below command:

.. code-block:: console

   $ pip install -r requirements.txt

Background
----------

PyGarmin is a set of `Python <https://www.python.org/>`__ classes which
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
``garmin.Garmin`` will create instances of the appropriate protocol classes and
notes the datatype classes for each type of data used in the transmissions. It
also has some friendly methods like ``get_waypoints()``, which do what you would
expect. What you get back when you call this is a list of objects, each of which
is a child the ``garmin.Wpt`` class.

Example Code
------------

Here’s a simple Python program:

.. code-block:: python

   #!/usr/bin/env python3
   import logging
   from garmin import garmin

   log = logging.getLogger('garmin')
   log.addHandler(logging.StreamHandler())
   log.setLevel(logging.INFO)

   # Create a 'physical layer' connection using serial port
   phys = garmin.SerialLink('/dev/ttyUSB0')

   # ...or using USB
   phys = garmin.USBLink()

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
longitude are transferred as ‘semicircle’ coordinates (basically degrees, but
scaled to fill a signed long integer). The static method
``Position.to_degrees()`` converts a semicircle integer into a degree float and
the ``as_degrees()`` method converts a Position into a DegreePosition data type.

More details
------------

There are 3 levels of protocol documented:

============= =========
 Layer         Level
============= =========
 Application   highest
 Link
 Physical      lowest
============= =========

The specification documents the various different versions of these
under labels of Pxxx, Lxxx, Axxx etc, where xxx is a number, and this
convention is followed in the code. There are also various data types,
named Dxxx. Roughly speaking, the Physical protocols specify RS232, the
Link protocols specify a packet structure for sending messages to and
fro, and the Application protocols specify what can actually go in those
packets.

For example, a Garmin GPS 38 will talk to your computer over physical
layer P000 (RS232) using a packet structure defined by link layer L001.
If you want to transfer waypoints to and from it, they will be sent
using application layer A100 (a waypoint transfer protocol), and the
actual waypoints transferred will be of type D100.

License
-------

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, version 3.

In the past, it has been released under the GNU General Public License
version 2, and some contributions have been made under that license. You
may use it under the terms of the GPLv2 if you prefer.

Acknowledgements
----------------

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
