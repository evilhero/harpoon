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
import requests
from harpoon import logger

class Sonarr(object):

    def __init__(self, sonarr_info):
       logger.info(sonarr_info)
       self.sonarr_url = sonarr_info['sonarr_url']
       self.sonarr_headers = sonarr_info['sonarr_headers']
       self.applylabel = sonarr_info['applylabel']
       self.defaultdir = sonarr_info['defaultdir']
       self.snstat = sonarr_info['snstat']

    def post_process(self):
        url = self.sonarr_url + '/api/command'
        if self.applylabel == 'true':
            if self.snstat['label'] == 'None':
                newpath = os.path.join(self.defaultdir, self.snstat['name'])
            else:
                newpath = os.path.join(self.defaultdir, self.snstat['label'], self.snstat['name'])
        else:
            newpath = os.path.join(self.defaultdir, self.snstat['name'])

        payload = {'name': 'DownloadedEpisodesScan',
                   'path': newpath,
                   'downloadClientID': self.snstat['hash'],
                   'importMode': 'Move'}

        logger.info('[SONARR] Posting url: %s' % url)
        logger.info('[SONARR] Posting to completed download handling now: %s' % payload)

        r = requests.post(url, json=payload, headers=self.sonarr_headers)
        data = r.json()
        logger.info('content: %s' % data)
        
        check = True
        while check:
            url = self.sonarr_url + '/api/command/' + str(data['id'])
            logger.info('[SONARR] command check url : %s' % url)
            try:
                r = requests.get(url, params=None, headers=self.sonarr_headers)
                dt = r.json()
                logger.info('[SONARR] Reponse: %s' % dt)
            except:
                logger.warn('error returned from sonarr call. Aborting.')
                return False
            else:
                if dt['state'] == 'completed':
                    logger.info('[SONARR] Successfully post-processed : ' + self.snstat['name'])
                    check = False
                else:
                    time.sleep(10)

        if check is False:
            #we need to get the root path here in order to make sure we call the correct plex update ...
            #hash is know @ self.snstat['hash'], file will exist in snatch queue dir as hashvalue.hash
            #file contains complete snatch record - retrieve the 'path' value to get the series directory.
            return True
        else:
            return False
