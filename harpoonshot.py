#!/usr/bin/env python
#  This file is part of Harpoon.
#
#  Harpoon is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Harpoon is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Harpoon.  If not, see <http://www.gnu.org/licenses/>.

import os
import re
import json
import requests
import time
import sys
import ConfigParser

import logging
from logging import handlers

##config
#this is required here to get the log path below
datadir = os.path.dirname(os.path.realpath(__file__))
config = ConfigParser.RawConfigParser()
config.read(os.path.join(datadir, 'conf', 'harpoon.conf'))

log_path = config.get('general', 'logpath')
sonarr_label = config.get('sonarr', 'sonarr_label')
radarr_label = config.get('radarr', 'radarr_label')
mylar_label = config.get('mylar', 'mylar_label')
torrentfile_dir = config.get('general', 'torrentfile_dir')

# Setup file logger
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

filename = os.path.join(log_path, 'harpoonshot.log')
file_formatter = logging.Formatter('%(asctime)s - %(levelname)-7s :: %(threadName)s : %(message)s', '%d-%b-%Y %H:%M:%S')
file_handler = handlers.RotatingFileHandler(filename, maxBytes=1000000, backupCount=5)
file_handler.setLevel(logging.DEBUG)

file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

try:
    mode = sys.argv[1]
except IndexError:
    try:
        if 'mylar_method' in os.environ:
            method = os.environ.get('mylar_method')
            if method == 'torrent':
                inputfile = os.environ.get('mylar_release_hash')
                label = mylar_label
                filetype = '.hash'
                mode = 'mylar'
            else:
                logger.info('mylar_method is not set to torrent, so cannot process this as it is an nzb.')
                sys.exit(1)
        else:
            logger.info('mylar_method not in os.environ, but it was called from mylar...')
            #ignore non-torrent snatches...
            sys.exit(1)
    except:
        logger.warn('Cannot determine if item came from sonarr / radarr / mylar ... Unable to harpoon item. ')
        sys.exit(1)
else:
    if mode == 'sonarr':
        inputfile = os.environ.get('sonarr_release_title')
        label = sonarr_label
        filetype = '.file'
    elif mode == 'radarr':
        inputfile = os.environ.get('radarr_release_title')
        if '//' in inputfile:
            inputfile = re.sub('-', '//', inputfile).strip()
        label = radarr_label
        filetype = '.file'
    else:
        logger.warn('Cannot determine if item came from sonarr / radarr / mylar ... Unable to harpoon item. ')
        sys.exit(1)

logger.info("Torrent name to use: %s" % inputfile)

path = os.path.join(torrentfile_dir, label)

#if mode == 'mylar':
#    filepath = os.path.join(path, inputfile + filetype)
#else:
filepath = os.path.join(path, inputfile + '.' + mode + filetype)

#create empty file with the given filename and update the mtime
with open(filepath, 'w'):
     os.utime(filepath, None)

logger.info('Successfully created .file to allow for harpooning.')
