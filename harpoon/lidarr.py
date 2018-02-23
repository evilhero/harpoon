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
import time
import shutil
import requests

from harpoon import logger

class Lidarr(object):

    def __init__(self, lidarr_info):
        self.lidarr_url = lidarr_info['lidarr_url']
        self.lidarr_label = lidarr_info['lidarr_label']
        self.lidarr_headers = lidarr_info['lidarr_headers']
        self.applylabel = lidarr_info['applylabel']
        self.defaultdir = lidarr_info['defaultdir']
        self.torrentfile_dir = lidarr_info['torrentfile_dir']
        self.snstat = lidarr_info['snstat']


    def post_process(self):
        url = self.lidarr_url + '/api/v1/command'
        if self.applylabel == 'true':
            if self.snstat['label'] == 'None':
                newpath = os.path.join(self.defaultdir, self.snstat['name'])
            else:
                newpath = os.path.join(self.defaultdir, self.snstat['label'], self.snstat['name'])
        else:
            newpath = os.path.join(self.defaultdir, self.snstat['name'])

        payload = {'name': 'DownloadedAlbumsScan',
                   'path': newpath,
                   'downloadClientID': self.snstat['hash'],
                   'importMode': 'Move'}

        logger.info('[LIDARR] Posting url: %s' % url)
        logger.info('[LIDARR] Posting to completed download handling now: %s' % payload)

        r = requests.post(url, json=payload, headers=self.lidarr_headers)
        data = r.json()
        logger.info('content: %s' % data)

        check = True
        while check:
            url = self.lidarr_url + '/api/v1/command/' + str(data['id'])
            logger.info('[LIDARR] command check url : %s' % url)
            try:
                r = requests.get(url, params=None, headers=self.lidarr_headers)
                dt = r.json()
                logger.info('[LIDARR] Reponse: %s' % dt)
            except:
                logger.warn('error returned from lidarr call. Aborting.')
                return False
            else:
                if dt['state'] == 'completed':
                    logger.info('[LIDARR] Successfully post-processed : ' + self.snstat['name'])
                    check = False
                else:
                    time.sleep(10)

        if check is False:
            # we need to get the root path here in order to make sure we call the correct plex update ...
            # hash is know @ self.snstat['hash'], file will exist in snatch queue dir as hashvalue.hash
            # file contains complete snatch record - retrieve the 'path' value to get the series directory.
            return True
        else:
            return False
