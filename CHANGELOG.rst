Changelog
=========

[1.2.0] 2024-03-17
------------------

- Fix datetimes that were off by 12 hours
- Localize datetimes
- Fix name clashes of classes
- Fix A201 route transfer protocol
- Fix D104 waypoint datatype
- Fix D304 track point datatype
- Better layout of submodules
- Support export to and import from JSON
- Support import from GPX (export to GPX was already supported)
- Add creator attribute to exported GPX
- Support export to FIT
- Use the same version for the module and the application
- Various bugfixes

[1.1.2] 2023-12-27
------------------

- Fix GPX export of Garmin Forerunner 305 tracks

[1.1.1] 2023-12-26
------------------

- Use the same license (GPLv2 or later) for the package as the source

[1.1.0] 2023-12-26
------------------

- Support Garmin Forerunner 305
- Support images of different color depths
- Various bugfixes

[1.0.5] 2023-11-22
------------------

- Fix relative package import (PR #7)

[1.0.4] 2022-12-23
------------------

- Improve documentation
- Add usage of pygarmin application to project description

[1.0.3] 2022-12-23
------------------

-  Fix project description

[1.0.2] 2022-12-22
------------------

-  Host documentation on Read the Docs

.. _section-1:

[1.0.1] 2022-12-21
------------------

-  Made the pygarmin script a submodule
-  Improved docstrings
-  Switched from Markdown to ReStructuredText
-  Added documentation using Sphinx

.. _section-2:

[1.0]
-----

-  Improved coding style to conform to the PEP8 style guide
-  Improved logging
-  Improved docstrings
-  Used a factory method to create objects
-  Used the new PyUSB 1.0 API
-  Used f-strings instead of %-formatting
-  Used the rawutil module instead of a customized struct
-  Implemented unit ID request
-  Added support for baudrate change
-  Added support for proximity waypoints transfer
-  Added support for waypoint category transfer
-  Added support for position initialization
-  Added support for maps
-  Added support for image transfer (screenshots and waypoint symbols)
-  Added support for screenshots
-  Removed test code (because I believe this belongs outside the main
   module)
-  Rewritten pygarmin to a fairly complete command-line program

.. _section-3:

[0.8]
-----

-  Used pyserial for serial communication
-  Added debian package support
-  Added support for flightbook
-  Added support for laps
-  Added support for runs
-  Added support for USB devices
-  Migrated to python3

.. _section-4:

[0.7]
-----

-  Fixed various bugs
-  Brought up to date with CVS (the tarball had become very dated)
-  Patches for recent pythons on Win32
-  JAHS’s mods - callback, debug etc
-  See CVS logs for more details

.. _section-5:

[0.6]
-----

-  Fixed various bugs
-  Tidier SerialLink code
-  Runs under Python 1.5.2
-  More debugging available if wanted

.. _section-6:

[0.5]
-----

-  Added a datum-conversion module.
-  Added Raymond Penners’ Win32SerialLink stuff and timeout stuff
-  A900 support
-  A800 support (for real-time data)
-  Waypoints now have **repr**, **str** and getDict methods
-  The ‘pygarmin’ app has some facilities to output XML, using the new
   xmlwriter module

.. _section-7:

[0.4]
-----

-  Various bug fixes and minor changes. See CVS logs for details

.. _section-8:

[0.3]
-----

-  Some changes to newstruct to fix bugs and make it work with Python
   1.5.1
-  Added TrackHdr class to fix protocol D310

.. _section-9:

[0.2]
-----

-  Incorporated James Skillen’s improvements to support protocol A001
   for newer Garmin units
-  Updated the tables based on new spec

.. _section-10:

[0.1]
-----

-  Initial release
