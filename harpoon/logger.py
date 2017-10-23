#!/usr/bin/python
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
