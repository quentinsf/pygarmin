
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

