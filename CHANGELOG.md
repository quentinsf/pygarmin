# Changelog
## [1.0]
- Improved coding style to conform to the PEP8 style guide
- Improved logging
- Improved docstrings
- Used a factory method to create objects
- Used the new PyUSB 1.0 API
- Used f-strings instead of %-formatting
- Used the rawutil module instead of a customized struct
- Implemented unit ID request
- Added support for baudrate change
- Added support for proximity waypoints transfer
- Added support for waypoint category transfer
- Added support for position initialization
- Added support for maps
- Added support for image transfer (screenshots and waypoint symbols)
- Added support for screenshots
- Removed test code (because I believe this belongs outside the main module)
- Rewritten pygarmin to a fairly complete command-line program

## [0.8]
- Used pyserial for serial communication
- Added debian package support
- Added support for flightbook
- Added support for laps
- Added support for runs
- Added support for USB devices
- Migrated to python3

## [0.7]
- Fixed various bugs
- Brought up to date with CVS (the tarball had become very dated)
- Patches for recent pythons on Win32
- JAHS's mods - callback, debug etc
- See CVS logs for more details

## [0.6]
- Fixed various bugs
- Tidier SerialLink code
- Runs under Python 1.5.2
- More debugging available if wanted

## [0.5]
- Added a datum-conversion module.
- Added Raymond Penners' Win32SerialLink stuff and timeout stuff
- A900 support
- A800 support (for real-time data)
- Waypoints now have __repr__, __str__ and getDict methods
- The 'pygarmin' app has some facilities to output XML, using the new xmlwriter module

## [0.4]
- Various bug fixes and minor changes. See CVS logs for details

## [0.3]
- Some changes to newstruct to fix bugs and make it work with Python 1.5.1
- Added TrackHdr class to fix protocol D310

## [0.2]
- Incorporated James Skillen's improvements to support protocol A001 for newer Garmin units
- Updated the tables based on new spec

## [0.1]
- Initial release
