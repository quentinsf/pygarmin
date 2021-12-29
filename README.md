PyGarmin
========

![PyGarmin](pygarmin.png)

PyGarmin is a set of Python classes for interfacing with (mostly older) Garmin GPS equipment.

Background
----------

PyGarmin is a set of [Python] classes which implement the protocol used by
[Garmin] GPS receivers to talk to each other and to other machines. It is based
on the official [protocol specification]. The project was started by [Quentin
Stafford-Fraser] but several others have helped to make it what it is today.

PyGarmin is not a complete application. Some simple applications are now
included, one of which is called pygarmin, but it is primarily just a toolkit
to help you write applications.  This is a project which is in development.
No support. No guarantees. And so forth.

Having said all of that, this has been used to transfer information to and from
several different Garmin receivers, mostly under Linux, though there is some
Windows support now and people have used it on Mac OS X as well. If you use
PyGarmin, it will probably be much quicker than writing your own software from
scratch.

We suggest you read these docs first. The code looks quites scary if you don't
know what's happening, though it's actually pretty simple.


Basics
------

Almost every model of Garmin receiver implements a slightly different
protocol. They have many things in common, but there are minor differences.
For example, some receivers can display icons, and they therefore transmit
waypoints which have an extra 'symbol' field, which is not used in other
models. Others don't use icons, but do store altitude. And so forth. You need
to get the protocol right for your particular model.

This makes matters more complicated, but at least these things are well
documented by Garmin. The [protocol specification]
includes a big table which details, for each product type, what protocol it
uses for basic commands, what it uses for downloading waypoints, what it uses
for downloading routes, and so forth.

I have created Python classes for each of the protocols listed in the spec,
and for each of the data types. Well, most of them. The big table becomes, in
Python, a mapping from the Garmin product ID to the set of relevant classes.
This means that, while there are a large number of classes defined in the
source, only a few of them will ever be used by any given receiver. The
classes are all given names based on those used in the specification, so look
at the spec if you want to know more about the classes.

The class <tt>garmin.Garmin</tt> will connect to your GPS, read its product
ID and software version, and then look up the appropriate classes in the
table. It creates instances of the protocol classes and notes the datatype
classes for each type of data used in the transmisisons. It also has some
friendly methods like 'getWaypoints', which do what you would expect.
What you get back when you call this is a list of objects, each of which is  an
instance of a class derived from garmin.Waypoint, but the precise type of the
objects will depend on the GPS you're talking to.

Installation
------------

Pygarmin makes use of the PySerial package for talking to serial ports.  If you don't have it already you can do a standard

    pip install -r requirements.txt

to get it.

You may also need to set suitable permissions on the serial port (e.g /dev/ttyS0) that you're planning to use.

Example Code
------------
OK. Here's a simple Python program. 

     #!/usr/bin/env python
     import logging
     import garmin
     
     c_handler = logging.StreamHandler()
     garmin.log.addHandler(c_handler)
     
     # uncomment to enable debug logging
     # garmin.log.setLevel(10)
     
     # Create a 'physical layer' connection using serial port
     phys = garmin.SerialLink("/dev/ttyUSB0")
     
     # Create a Garmin object using this connection
     gps = garmin.Garmin(phys)
     
     # Get the waypoints from the GPS
     # (This may take a little while)
     waypoints = gps.getWaypoints()
     
     # Get the tracks from the GPS
     # (This may take a little while)
     tracks = gps.getTracks()
     
     # Print the waypoints
     print('# Waypoints:')
     for w in waypoints:
         lat = garmin.degrees(w.slat)
         lon = garmin.degrees(w.slon)
         print(w.ident, lat, lon, w.cmnt)
     
     # Print the tracks
     print('\n\n# Tracks:')
     for t in tracks:
         print(t)
     
     # Put a new waypoint
     print('Storing a new waypoint..')
     new_wpt = {'ident': 'CLUB91', 'cmnt': 'DRINKING', 'slat': 606532864, 'slon': 57654672, 'smbl': 13}
     gps.putWaypoints([new_wpt])

This should work for almost any model, because all waypoints will have an identity, a latitude &amp; longitude, and a comment field. The latitude and longitude are stored in 'semicircle' coordinates (basically degrees, but scaled to fill a signed long integer), and so the fields are called 'slat' and 'slon'. The function `garmin.degrees()` converts these to degrees.


More details
------------

There are 3 levels of protocol documented:

     ................
    |  Application   | (highest level)
     ................
    |  Link layer    |
     ................
    | Physical layer | (lowest level)
     ................

The specification documents the various different versions of these under
labels of Pxxx, Lxxx, Axxx etc, where xxx is a number, and this convention is
followed in the code. There are also various data types, named Dxxx. Roughly
speaking, the Physical protocols specify RS232, the Link protocols specify a
packet structure for sending messages to and fro, and the Application
protocols specify what can actually go in those packets.

For example, a Garmin GPS 38 will talk to your computer over physical layer
P000 (RS232) using a packet structure defined by link layer L001. If you want
to transfer waypoints to and from it, they will be sent using application
layer A100 (a waypoint transfer protocol), and the actual waypoints
transferred will be of type D100.

At the time of writing, the only documented physical layer is P000 which is
roughly RS232 at 9600 baud, 8 data bits, no parity, 1 stop bit. In the
software, we model this as a P000 class that has read and write methods, which
can be used by the higher protocol levels. The UnixSerialPort class used in
the sample code above is a subtype of P000.

That should be enough to get you going.

Some data type classes are not implemented here, just because I got bored
of typing. We've done the ones used by the more common units, but if yours
isn't covered, it should be easy to add. They're only a few lines each.


Licence
-------

This software is released under the GNU General Public Licence v2. It comes with no warranties, explicit or implied, and you use it at your own risk.


Acknowledgements
----------------

Thanks are due to, amongst others:

* [Quentin Stafford-Fraser](http://www.statusq.org)
* James Skillen
* [Bjorn Tillenius](http://tillenius.me/)
* Hyrum K. Wright
* Cedric Dutoit

and probably others, to whom our apologies!

The logo was designed by [Quentin Stafford-Fraser].

[Python]: http://www.python.org
[Garmin]: http://www.garmin.com
[protocol specification]: http://www.garmin.com/support/commProtocol.html
[Quentin Stafford-Fraser]: http://quentinsf.com
