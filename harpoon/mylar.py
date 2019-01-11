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
import json
import requests
from harpoon import logger

class Mylar(object):

    def __init__(self, mylar_info):
       self.mylar_url = mylar_info['mylar_url']
       self.mylar_apikey = mylar_info['mylar_apikey']
       self.mylar_label = mylar_info['mylar_label']
       self.mylar_headers = mylar_info['mylar_headers']
       self.applylabel = mylar_info['applylabel']
       self.torrentfile_dir = mylar_info['torrentfile_dir']
       self.defaultdir = mylar_info['defaultdir']
       self.issueid = mylar_info['issueid']
       self.snstat = mylar_info['snstat']

    def post_process(self):
       logger.info('snstat: %s' % self.snstat)
       issueid = None
       comicid = None
       nzb_name = None
       nzb = False
       try:
           logger.debug('Attempting to open: %s' % os.path.join(self.torrentfile_dir, self.mylar_label, self.snstat['hash'] + '.mylar.hash'))
           with open(os.path.join(self.torrentfile_dir, self.mylar_label, self.snstat['hash'] + '.mylar.hash')) as dfile:
               data = json.load(dfile)
       except Exception as e:
           logger.error('[%s] not able to load .mylar.hash file.' % e)
           #for those that were done outside of Mylar or using the -s switch on the cli directly by hash
           nzb_name = 'Manual Run'
       else:
           logger.debug('loaded .mylar.hash successfully - extracting info.')
           try:
               nzb_name = data['mylar_release_name']
           except:
               try:
                   if 'mylar_release_nzbname' in data.keys():
                       # nzb_name HAS TO BE the filename itself so it can pp directly
                       nzb_name = os.path.basename(self.snstat['folder'])
                       nzb = True
               except:
                   #if mylar_release_name doesn't exist, fall back to the torrent_filename.
                   #mylar retry issue will not have a release_name
                   nzb_name = data['mylar_torrent_filename']

           if self.issueid is None:
               if data['mylar_issuearcid'] != 'None':
                   issueid = data['mylar_issuearcid']
               else:
                   if data['mylar_release_pack'] == 'False':
                       issueid = data['mylar_issueid']
                   else:
                       issueid = None
               comicid = data['mylar_comicid']
               if comicid == 'None':
                   comicid = None
           else:
               issueid = self.issueid
               comicid = None

       if self.issueid is not None and nzb_name == 'Manual Run':
           issueid = self.issueid
           comicid = None
           nzb_name = self.snstat['name']

       url = self.mylar_url + '/api'
       if all([self.applylabel is True, self.snstat['label'] != 'None']):
           if nzb is True:
               newpath = os.path.join(self.defaultdir, self.snstat['label'], self.snstat['extendedname'])
           else:
               if os.path.isdir(os.path.join(self.defaultdir, self.snstat['label'], self.snstat['name'])):
                   newpath = os.path.join(self.defaultdir, self.snstat['label'], self.snstat['name'])
               else:
                   if os.path.isdir(os.path.join(self.defaultdir, self.snstat['label'])):
                       newpath = os.path.join(self.defaultdir, self.snstat['label'])
       else:
           if nzb is True:
               newpath = os.path.join(self.defaultdir, self.snstat['extendedname'])
           else:
               newpath = os.path.join(self.defaultdir, self.snstat['name'])

       payload = {'cmd':         'forceProcess',
                  'apikey':      self.mylar_apikey,
                  'nzb_name':    nzb_name,
                  'issueid':     issueid,
                  'comicid':     comicid,
                  'nzb_folder':  newpath}

       logger.info('[MYLAR] Posting url: %s' % url)
       logger.info('[MYLAR] Posting to completed download handling now: %s' % payload)

       try:
           r = requests.post(url, params=payload, headers=self.mylar_headers, timeout=0.001)
       except Exception as e:
           if any(['Connection refused' in e, 'Timeout' in e]):
               logger.warn('Unable to connect to Mylar server. Please check that it is online [%s].' % e)
           else:
               logger.warn('%s' % e)
           return False

       #response = r.json()
       logger.debug('content: %s' % r.content)

       logger.debug('[MYLAR] status_code: %s' % r.status_code)
       logger.info('[MYLAR] Successfully post-processed : ' + self.snstat['name'])

       return True
