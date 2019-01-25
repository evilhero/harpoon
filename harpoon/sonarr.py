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
import shutil
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
        name = self.snstat['name']
        if 'extendedname' in self.snstat.keys():
            name = self.snstat['extendedname']
        if self.applylabel is True:
            if self.snstat['label'] == 'None':
                newpath = os.path.join(self.defaultdir, name)
            else:
                newpath = os.path.join(self.defaultdir, self.snstat['label'], name)
        else:
            newpath = os.path.join(self.defaultdir, name)

        if os.path.isfile(newpath):
            logger.warn('[SONARR] This is an individual movie, but Sonarr will only import from a directory. Creating a temporary directory and moving this so it can proceed.')
            newdir = os.path.join(os.path.abspath(os.path.join(newpath, os.pardir)), os.path.splitext(self.snstat['name'])[0])
            logger.info('[SONARR] Creating directory: %s' % newdir)
            os.makedirs(newdir)
            logger.info('[SONARR] Moving %s -TO- %s' % (newpath, newdir))
            shutil.move(newpath, newdir)
            newpath = newdir
            logger.info('[SONARR] New path location now set to: %s' % newpath)

        #make sure it's in a Completed status otherwise it won't import (why? I haven't a f*ckin' clue but it's cause of v2.0.0.5301)
        cntit = 0
        while True:
            check_that_shit = self.checkyourself()
            if check_that_shit is True:
                break
            if cntit == 10:
                logger.error('[SONARR-ERROR] Unable to verify completion status of item - maybe this was already post-processed using a different method?')
                return False
            cntit+=1
            time.sleep(15)

        payload = {"name": "DownloadedEpisodesScan",
                   "path": newpath,
                   "downloadClientID": self.snstat['hash'],
                   "importMode": "Move"}

        logger.info('[SONARR] Waiting 10s prior to sending to download handler to make sure item is completed within Sonarr')
        logger.info('[SONARR] Posting to completed download handling after a short 10s delay: %s' % payload)
        time.sleep(10)

        r = requests.post(url, json=payload, headers=self.sonarr_headers)
        data = r.json()

        check = True
        while check:
            url = self.sonarr_url + '/api/command/' + str(data['id'])
            logger.info('[SONARR] command check url : %s' % url)
            try:
                r = requests.get(url, params=None, headers=self.sonarr_headers)
                dt = r.json()
                logger.info('[SONARR] Reponse: %s' % dt)
            except Exception as e:
                logger.warn('[%s] error returned from sonarr call. Aborting.' % e)
                return False
            else:
                if dt['state'] == 'completed':
                    #duration = time.strptime(dt['duration'][:-1], '%H:%M:%S.%f').tm_sec
                    #if tm_sec < 20:
                    #    #if less than 20s duration, the pp didn't succeed.
                    #else:
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

    def checkyourself(self):

        url = self.sonarr_url + '/api/queue'
        checkit = False

        logger.info('[SONARR] Querying against active queue now for completion')
        r = requests.get(url, headers=self.sonarr_headers)
        logger.info(r.status_code)
        results = r.json()

        for x in results:
            try:
                if x['downloadId']:
                    if self.snstat['hash'] == x['downloadId']:
                        if x['status'] == 'Completed':
                            logger.info('[SONARR] file has been marked as completed within Sonarr. It\'s a Go!')
                            checkit = True
                            break
            except:
                continue

        return checkit
