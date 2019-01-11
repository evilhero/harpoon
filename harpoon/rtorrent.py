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
import sys
import re
import time
import shutil
import traceback
from base64 import b16encode, b32decode

import hashlib, StringIO
import bencode
from torrent.helpers.variable import link, symlink, is_rarfile

import ConfigParser

import torrent.clients.rtorrent as TorClient

import harpoon
from harpoon import logger

class RTorrent(object):
    def __init__(self, hash=None, file=None, add=False, label=None, partial=False, conf=None):

        if hash is None:
            self.torrent_hash = None
        else:
            self.torrent_hash = hash

        if file is None:
            self.filepath = None
        else:
            self.filepath = file

        self.basedir = None

        if label is None:
            self.label = None
        else:
            self.label = label

        if add is True:
            self.add = True
        else:
            self.add = False

        if partial is True:
            self.partial = True
        else:
            self.partial = False

        if conf is None:
            logger.warn('Unable to load config file properly for rtorrent usage. Make sure harpoon.conf is located in the /conf directory')
            return None
        else:
            self.conf_location = conf

        config = ConfigParser.RawConfigParser()
        config.read(self.conf_location)

        self.applylabel = config.getboolean('general', 'applylabel')
        self.multiple_seedboxes = config.getboolean('general', 'multiple_seedboxes')
        logger.info('multiple_seedboxes: %s' % self.multiple_seedboxes)
        if self.multiple_seedboxes is True:
            sectionsconfig1 = config.get('general', 'multiple1')
            sectionsconfig2 = config.get('general', 'multiple2')
            sectionlist1 = sectionsconfig1.split(',')
            sections1 = [x for x in sectionlist1 if x.lower() == label.lower()]
            sectionlist2 = sectionsconfig2.split(',')
            sections2 = [x for x in sectionlist2 if x.lower() == label.lower()]
            logger.info('sections1: %s' % sections1)
            logger.info('sections2: %s' % sections2)
            if sections1:
                logger.info('SEEDBOX-1 ENABLED!')
                self.start = config.getboolean('rtorrent', 'startonload')
                self.rtorrent_host = config.get('rtorrent', 'rtorr_host') + ':' + config.get('rtorrent', 'rtorr_port')
                self.rtorrent_user = config.get('rtorrent', 'rtorr_user')
                self.rtorrent_pass = config.get('rtorrent', 'rtorr_passwd')
                self.rtorrent_auth = config.get('rtorrent', 'authentication')
                self.rtorrent_rpc = config.get('rtorrent', 'rpc_url')
                self.rtorrent_ssl = config.getboolean('rtorrent', 'ssl')
                self.rtorrent_verify = config.getboolean('rtorrent', 'verify_ssl')
                self.basedir = config.get('post-processing', 'pp_basedir')
                self.multiple = '1'

            elif sections2:
                logger.info('SEEDBOX-2 ENABLED!')
                self.start = config.getboolean('rtorrent2', 'startonload')
                self.rtorrent_host = config.get('rtorrent2', 'rtorr_host') + ':' + config.get('rtorrent2', 'rtorr_port')
                self.rtorrent_user = config.get('rtorrent2', 'rtorr_user')
                self.rtorrent_pass = config.get('rtorrent2', 'rtorr_passwd')
                self.rtorrent_auth = config.get('rtorrent2', 'authentication')
                self.rtorrent_rpc = config.get('rtorrent2', 'rpc_url')
                self.rtorrent_ssl = config.getboolean('rtorrent2', 'ssl')
                self.rtorrent_verify = config.getboolean('rtorrent2', 'verify_ssl')
                self.basedir = config.get('post-processing2', 'pp_basedir2')
                self.multiple = '2'
            else:
                logger.info('No label directory assignment provided (ie. the torrent file is not located in a directory named after the label.')
                return None
        else:
            logger.info('SEEDBOX-1 IS LONE OPTION - ENABLED!')
            self.start = config.getboolean('rtorrent', 'startonload')
            self.rtorrent_host = config.get('rtorrent', 'rtorr_host') + ':' + config.get('rtorrent', 'rtorr_port')
            self.rtorrent_user = config.get('rtorrent', 'rtorr_user')
            self.rtorrent_pass = config.get('rtorrent', 'rtorr_passwd')
            self.rtorrent_auth = config.get('rtorrent', 'authentication')
            self.rtorrent_rpc = config.get('rtorrent', 'rpc_url')
            self.rtorrent_ssl = config.getboolean('rtorrent', 'ssl')
            self.rtorrent_verify = config.getboolean('rtorrent', 'verify_ssl')
            self.basedir = config.get('post-processing', 'pp_basedir')
            self.multiple = None

        self.client = TorClient.TorrentClient()
        if not self.client.connect(self.rtorrent_host,
                                   self.rtorrent_user,
                                   self.rtorrent_pass,
                                   self.rtorrent_auth,
                                   self.rtorrent_rpc,
                                   self.rtorrent_ssl,
                                   self.rtorrent_verify):
            logger.info('could not connect to host, exiting')
            return None
            #sys.exit(-1)

    def main(self, check=False):

        if self.torrent_hash:
            torrent = self.client.find_torrent(self.torrent_hash)
            if torrent:
                if check:
                    logger.info('Successfully located torrent %s by hash on client. Detailed statistics to follow' % self.torrent_hash)
                else:
                    if self.add is False:
                        logger.info('[SELF-ADD FALSE] Successfully located torrent %s by hash on client. Detailed statistics to follow' % self.torrent_hash)
                    else:
                        logger.info("[SELF-ADD TRUE] %s Torrent already exists. Not adding to client.", self.torrent_hash)
                        return False
            else:
                if self.add is True:
                    logger.info('Torrent with hash value of %s does not exist. Adding to client...' % self.torrent_hash)
                else:
                    logger.info('Unable to locate torrent with a hash value of %s' % self.torrent_hash)
                    return None

        #if self.filepath exists it will be the filename that exists on the torrent client. self.add cannot be true EVER in this case.
        elif all([self.filepath, self.add is False]):
            torrent = self.client.find_torrent(filepath=self.filepath)
            if torrent is None:
                logger.info("Couldn't find torrent with filename: %s " % self.filepath)
                return None #sys.exit(-1)
            else:
               logger.info("Located file at: %s" % self.filepath)

        #if add is true, self.filepath will contain the local path the .torrent file to load.
        if self.add is True:
            logger.info("Attempting to load torrent. Filepath is : %s" % self.filepath)
            logger.info("label is : %s" % self.label)
            loadit = self.client.load_torrent(self.filepath, self.label, self.start, self.applylabel, self.basedir)
            if loadit:
                logger.info('Successfully loaded torrent.')
                torrent_hash = self.get_the_hash()
            else:
                logger.info('NOT Successfully loaded.')
                return None
            logger.info('Attempting to find by hash: ' + torrent_hash)
            torrent = self.client.find_torrent(torrent_hash)

        logger.info(torrent)
        torrent_info = self.client.get_torrent(torrent)

        if any([torrent_info is False, torrent_info is None]):
            return None

        if check:
            return torrent_info

        logger.info(torrent_info)

        if torrent_info['completed'] or self.partial is True:
            logger.info('# of files: %s' % str(len(torrent_info['files'])))
            logger.info('self.basedir: %s' % self.basedir)
            logger.info('torrent_info_folder: %s' % torrent_info['folder'])
            logger.info('folder+label: %s' % os.path.join(torrent_info['folder'], torrent_info['label']))
            logger.info('base: %s' % os.path.dirname(os.path.normpath(torrent_info['folder'])))
            logger.info('label: %s' % torrent_info['label'])
            if all([len(torrent_info['files']) >= 1, self.basedir is not None, self.basedir != torrent_info['folder'], torrent_info['folder'] not in self.basedir]) and all([os.path.join(self.basedir, torrent_info['label']) != torrent_info['folder'], os.path.dirname(os.path.normpath(torrent_info['folder']))!= torrent_info['label']]):
                logger.info("MIRROR SHOULD BE USED: %s" % str(len(torrent_info['files'])))
                torrent_info['mirror'] = True
            else:
                logger.info("FILE SHOULD BE USED: %s" % torrent_info['files'])
                torrent_info['mirror'] = False
            logger.info("Directory: %s" % torrent_info['folder'])
            logger.info("Name: %s" % torrent_info['name'])
            #logger.info("FileSize: %s", helpers.human_size(torrent_info['total_filesize']))
            logger.info("Completed: %s" % torrent_info['completed'])
            #logger.info("Downloaded: %s", helpers.human_size(torrent_info['download_total']))
            #logger.info("Uploaded: %s", helpers.human_size(torrent_info['upload_total']))
            logger.info("Ratio: %s" % torrent_info['ratio'])
            #logger.info("Time Started: %s", torrent_info['time_started'])
            #logger.info("Seeding Time: %s", helpers.humanize_time(int(time.time()) - torrent_info['time_started']))

            if torrent_info['label']:
                logger.info("Torrent Label: %s" % torrent_info['label'])

            torrent_info['multiple'] = self.multiple

        logger.info(torrent_info)
        return torrent_info

    def get_the_hash(self):
        # Open torrent file
        torrent_file = open(self.filepath, "rb")
        metainfo = bencode.decode(torrent_file.read())
        info = metainfo['info']
        thehash = hashlib.sha1(bencode.encode(info)).hexdigest().upper()
        logger.info('Hash: %s' % thehash)
        return thehash


#if __name__ == '__main__':
#    gf = RTorrent()
#    gf.main()


