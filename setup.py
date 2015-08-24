#!/usr/bin/env python

from setuptools import setup

setup(name="pygarmin",
      # packages = ['pygarmin'],
      scripts = ['pygarmin', 'gnome-pygarmin'],
      version = "0.8",
      description = "A Python interface to older Garmin GPS equipment",
      author = "Quentin Stafford-Fraser",
      author_email = "quentin@pobox.com",
      url = "http://github.com/quentinsf/pygarmin",
      keywords = 'gps gis',
      py_modules = ["garmin", "newstruct", "datum", "refdatum", "xmlwriter"],
      install_requires = ['pyserial'],
    )
