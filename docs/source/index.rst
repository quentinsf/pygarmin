.. Pygarmin documentation master file, created by
   sphinx-quickstart on Mon Dec 19 10:54:34 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Pygarmin's documentation!
====================================

The *Pygarmin* distribution provides a `Python <https://www.python.org/>`_
module and a command line application that implement the protocol used by
`Garmin <https://www.garmin.com/>`_ GPS devices. It is based on the official
`protocol specification <https://www8.garmin.com/support/commProtocol.html>`_.

Installing
==========

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

Contents
========

.. toctree::
   :maxdepth: 2

   pygarmin
   api
   exceptions
   protocols
   datatypes

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
