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

import urllib
import requests
import os
import sys
import re
import time
import harpoon
from harpoon import logger

class SABnzbd(object):
    def __init__(self, params=None, saburl=None):
        self.params = params
        self.sab_url = saburl + '/api'
        self.sab_apikey = params['apikey']
        self.params['output'] = 'json'


    def sender(self, files=None):
        try:
            from requests.packages.urllib3 import disable_warnings
            disable_warnings()
        except:
            logger.info('Unable to disable https warnings. Expect some spam if using https nzb providers.')

        try:
            logger.info('parameters set to %s' % self.params)
            logger.info('sending now to %s' % self.sab_url)
            if files:
                sendit = requests.post(self.sab_url, data=self.params, files=files, verify=False)
            else:
                sendit = requests.post(self.sab_url, data=self.params, verify=False)
        except:
            logger.info('Failed to send to client.')
            return {'status': False}
        else:
            sendresponse = sendit.json()
            logger.info(sendresponse)
            if sendresponse['status'] is True:
                queue_params = {'status': True,
                                'nzo_id': ''.join(sendresponse['nzo_ids']),
                                'queue':  {'mode':   'queue',
                                           'search':  ''.join(sendresponse['nzo_ids']),
                                           'output':  'json',
                                           'apikey':  self.sab_apikey}}

            else:
                queue_params = {'status': False}

            return queue_params

    def query(self):
        sendresponse = self.params['nzo_id']
        queue = {'mode': 'queue',
                 'search': self.params['nzo_id'],
                 'output': 'json',
                 'apikey': self.sab_apikey}
        try:
            logger.info('sending now to %s' % self.sab_url)
            logger.debug('parameters set to %s' % queue)
            h = requests.get(self.sab_url, params=queue, verify=False)
        except Exception as e:
            logger.error('uh-oh: %s' % e)
            return {'completed': False}
        else:
            queueresponse = h.json()
            logger.info('successfully queried the queue for status')
            try:
                queueinfo = queueresponse['queue']
                logger.info('queue: %s' % queueresponse)
                logger.info('Queue status : %s' % queueinfo['status'])
                logger.info('Queue mbleft : %s' % queueinfo['mbleft'])
                if any([str(queueinfo['status']) == 'Downloading', str(queueinfo['status']) == 'Idle']) and float(queueinfo['mbleft']) > 0:
                    logger.info('[SABNZBD] Dowwnload is not yet finished')
                    return {'completed': False}
            except Exception as e:
                logger.error('error: %s' % e)
                return {'completed': False}

            logger.info('[SABNZBD] Download completed.  Querying history.')
            hist_params = {'mode':      'history',
                           'failed':    0,
                           'output':    'json',
                           'apikey':    self.sab_apikey}
            hist = requests.get(self.sab_url, params=hist_params, verify=False)
            historyresponse = hist.json()
            histqueue = historyresponse['history']
            found = None
            try:
                for hq in histqueue['slots']:
                    # logger.info('nzo_id: %s --- %s [%s]' % (hq['nzo_id'], sendresponse, hq['status']))
                    if hq['nzo_id'] == sendresponse and hq['status'] == 'Completed':
                        logger.info('[SABNZBD] Found matching completed item in history. Job has a status of %s' % hq['status'])
                        logger.info('[SABNZBD] Location found @ %s' % hq['storage'])
                        path_folder = hq['storage']
                        nzbname = os.path.basename(hq['storage'])
                        found = {'completed': True,
                                 'name': re.sub('.nzb', '', hq['nzb_name']).strip(),
                                 'extendedname' : nzbname,
                                 'folder': path_folder,
                                 'mirror': True,  # Change this
                                 'multiple': None,
                                 'label': hq['category'],
                                 'hash': hq['nzo_id'],
                                 'failed': False,
                                 'files': []}
                        break
                    elif hq['nzo_id'] == sendresponse and hq['status'] == 'Failed':
                        # get the stage / error message and see what we can do
                        stage = hq['stage_log']
                        for x in stage[0]:
                            if 'Failed' in x['actions'] and any([x['name'] == 'Unpack', x['name'] == 'Repair']):
                                if 'moving' in x['actions']:
                                    logger.warn(
                                        '[SABNZBD] There was a failure in SABnzbd during the unpack/repair phase that caused a failure: %s' %
                                        x['actions'])
                                else:
                                    logger.warn(
                                        '[SABNZBD] Failure occured during the Unpack/Repair phase of SABnzbd. This is probably a bad file: %s' %
                                        x['actions'])
                                break
            except Exception as e:
                logger.warn('error %s' % e)

            return found

    def cleanup(self):
        sendresponse = self.params['nzo_id']
        queue = {'mode': 'history',
                 'name': 'delete',
                 'del_files': 1,
                 'value': self.params['nzo_id'],
                 'output': 'json',
                 'apikey': self.sab_apikey,
                 'limit': 500}
        try:
            logger.info('sending now to %s' % self.sab_url)
            logger.debug('parameters set to %s' % queue)
            h = requests.get(self.sab_url, params=queue, verify=False)
        except Exception as e:
            logger.error('uh-oh: %s' % e)
            return {'status': False}
        else:
            queueresponse = h.json()
            if queueresponse['status']:
                logger.info('[SABNZBD] Successfully deleted the item from SABnzbd.')
            else:
                logger.warn('[SABNZBD] Unable to delete item from SABnzbd.')
        return queueresponse
