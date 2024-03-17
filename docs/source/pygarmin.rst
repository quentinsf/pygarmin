Pygarmin application
====================

Synopsis
--------

.. code-block:: text

   pygarmin [arguments] <sub-command> [arguments]

The arguments before the sub-command configure pygarmins behaviour, the
sub-command indicates which operation should be performed, and the arguments
after the sub-command configure the sub-commands behaviour.

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

Options
-------

.. currentmodule:: pygarmin.pygarmin

.. argparse::
   :module: pygarmin.pygarmin
   :func: parser
   :prog: pygarmin

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

Print real-time position, velocity, and time (PVT) in GPSD JSON format to stdout::

   pygarmin pvt -t gpsd

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
