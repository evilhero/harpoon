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

class LazyLibrarian(object):

    def __init__(self, ll_info):
        logger.info(ll_info)
        self.lazylibrarian_url = ll_info['lazylibrarian_url']
        self.lazylibrarian_label = ll_info['lazylibrarian_label']
        self.lazylibrarian_headers = ll_info['lazylibrarian_headers']
        self.lazylibrarian_apikey = ll_info['lazylibrarian_apikey']
        self.lazylibrarian_filedata = ll_info['lazylibrarian_filedata']
        self.applylabel = ll_info['applylabel']
        self.defaultdir = ll_info['defaultdir']
        self.snstat = ll_info['snstat']

    def post_process(self):
        url = self.lazylibrarian_url + '/api'
        if self.applylabel == 'true':
            if self.snstat['label'] == 'None':
                newpath = os.path.join(self.defaultdir, self.snstat['name'])
            else:
                newpath = os.path.join(self.defaultdir, self.snstat['label'], self.snstat['name'])
        else:
            newpath = os.path.join(self.defaultdir, self.snstat['name'])
        if self.lazylibrarian_filedata and 'BookID' in self.lazylibrarian_filedata.keys():
            brandnewpath = newpath + ' LL.(%s)' % self.lazylibrarian_filedata['BookID']
            logger.debug('[LAZYLIBRARIAN] New Path: %s' % brandnewpath)
            if os.path.isdir(newpath):
                logger.debug('[LAZYLIBRARIAN] Renaming Folder')
                os.rename(newpath, brandnewpath)
                logger.debug('Path Renamed')
            elif os.path.isfile(newpath):
                logger.debug('[LAZYLIBRARIAN] Moving file (%s) into folder (%s)' % (newpath, brandnewpath))
                newfile = os.path.join(brandnewpath, self.snstat['name'])
                os.mkdir(brandnewpath)
                logger.debug('NewFile: %s' % newfile)
                shutil.move(newpath, newfile)
            else:
                logger.debug('[LAZYLIBRARIAN] File not found.')
                return False
        else:
            brandnewpath = newpath
        logger.info('[LAZYLIBRARIAN] Path: %s' % brandnewpath)
        payload = {'cmd':  'forceProcess',
                   'dir': brandnewpath,
                   'apikey': self.lazylibrarian_apikey,
                   'ignorekeepseeding': 'True',}

        logger.info('[LAZYLIBRARIAN] Posting url: %s' % url)
        logger.info('[LAZYLIBRARIAN] Posting to completed download handling now: %s' % payload)

        r = requests.post(url, data=payload, headers=self.lazylibrarian_headers)
        data = r.text
        logger.info('content: %s' % data)
        logger.info('[LAZYLIBRARIAN] Successfully post-processed : ' + self.snstat['name'])
        return True
