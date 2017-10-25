#!/usr/bin/python
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
import logging
from logging import handlers
from logging import getLogger, INFO, DEBUG, StreamHandler, Formatter, Handler

logger = logging.getLogger('harpoon')

def initLogger(logpath):
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('apscheduler.scheduler').setLevel(logging.WARN)
    logging.getLogger('apscheduler.threadpool').setLevel(logging.WARN)
    logging.getLogger('apscheduler.scheduler').propagate = False
    logging.getLogger('apscheduler.threadpool').propagate = False
    logger = logging.getLogger()

    # Setup file logger
    filename = os.path.join(logpath, 'harpoon.log')
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)-7s :: %(threadName)s : %(message)s', '%d-%b-%Y %H:%M:%S')
    file_handler = handlers.RotatingFileHandler(filename, maxBytes=1000000, backupCount=5)
    file_handler.setLevel(logging.DEBUG)

    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

# Expose logger methods
info = logger.info
warn = logger.warn
error = logger.error
debug = logger.debug
warning = logger.warning
message = logger.info
exception = logger.exception
