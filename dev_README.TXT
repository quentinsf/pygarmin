Coding Guidelines
-----------------------
As of 2005-03-25, all code has been reformatted to use four space indents,
and no tabs. This is the preferred Python coding style, as documented
in PEP 8.
-----------------------

Date : 24 December 2004
Author : Gerrit Sere

Happy days everybody

dev_garmin.py
------------------------

* Lap protocel is tested.
* FlightBook protocol is included but not tested. Do you have an airplane ?

dev_format.py
------------------------

* Include GPX, it is now possible to get and send information into GPX format. 
GPX format is a standard XML schema for gps and used with lots of other programs
(http://www.topografix.com/GPX/1/1 )

dev_pygarmin.py
------------------------

Changed this program fast to work with the new dev_garmin.py program



****************************************************************************************************************************
Origal Version
date : Novermber
Author : Gerrit Sere

This readme file explains :

dev_garmin.py
dev_format.py

dev_garmin.py
------------------------

I made a lot of changes to the original "garmin.py" that I found that it was too risky to continue developing the original one. One day after testing, debugging, dev_garmin.py would be renamed to garmin.py.

What's new :
---------------------
* Change the code to the "Garmin GPS Interface Specification" from February 24, 2004. The FlightBook protocol is not yet complete. The Lap protocol is included but not tested !
* It is possible to send waypoints, routes and tracks to your GPS.
* Examples can be found in the main function. In this function you see a lot of
"if 0:" sentences, changes those to "if 1:" and try. Of course, your GPS need to understand the protocol.

A few things to know :
--------------------------------------
* Don't try to rename dev_garmin.py to garmin.py. pygarmin.py won't work. After dev_garmin.py is stable, changes will be done to pygarmin.py and other programs.
* You also need to install pyserial.
* When you start the program, you may get a "Link Error", then start the program again.


dev_format.py
-----------------------

With this program you can get info from your gps and save it to an OziExplorer format. Also, it is possible to send an OziExplorer file to your gps. Look at the main function

This code worked for:

GPSMAP 76S
GPSMAP 60CS

Because, we won't have all the different Garmin Gps, please try the code and your info is more than welcome !
Thx,

