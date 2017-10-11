import os
import time
import requests
from harpoon import logger

class Sickrage(object):

    def __init__(self, sickrage_info):
       logger.info(sickrage_info)
       self.sickrage_url = sickrage_info['sickrage_conf']['sickrage_url']
       self.sickrage_apikey = sickrage_info['sickrage_conf']['sickrage_apikey']
       self.sickrage_forcereplace = sickrage_info['sickrage_conf']['sickrage_forcereplace']
       self.sickrage_forcenext = sickrage_info['sickrage_conf']['sickrage_forcenext']
       self.sickrage_process_method = sickrage_info['sickrage_conf']['sickrage_process_method']
       self.sickrage_is_priority = sickrage_info['sickrage_conf']['sickrage_is_priority']
       self.sickrage_failed = sickrage_info['sickrage_conf']['sickrage_failed']
       self.sickrage_delete = sickrage_info['sickrage_conf']['sickrage_delete']
       self.sickrage_type = sickrage_info['sickrage_conf']['sickrage_type']
       self.sickrage_headers = sickrage_info['sickrage_conf']['sickrage_headers']
       self.applylabel = sickrage_info['applylabel']
       self.defaultdir = sickrage_info['defaultdir']
       self.snstat = sickrage_info['snstat']

    def post_process(self):
        url = self.sickrage_url + '/api/' + self.sickrage_apikey
        if self.applylabel == 'true':
            if self.snstat['label'] == 'None':
                newpath = os.path.join(self.defaultdir, self.snstat['name'])
            else:
                newpath = os.path.join(self.defaultdir, self.snstat['label'], self.snstat['name'])
        else:
            newpath = os.path.join(self.defaultdir, self.snstat['name'])

        payload = {'cmd':  'postprocess',
                   'path': newpath,
                   'delete': bool(self.sickrage_delete),
                   'force_next': 0,
                   'force_replace': bool(self.sickrage_force_replace),
                   'is_priority': bool(self.sickrage_is_priority),
                   'process_method':  self.sickrage_process_method,
                   'return_data': 1,
                   'failed': bool(self.sickrage_failed),
                   'type': self.sickrage_type}

        logger.info('[SICKRAGE] Posting url: %s' % url)
        logger.info('[SICKRAGE] Posting to completed download handling now: %s' % payload)

        r = requests.post(url, json=payload, headers=self.sickrage_headers)
        data = r.json()
        logger.info('content: %s' % data)
        logger.info('[SICKRAGE] Successfully post-processed : ' + self.snstat['name'])
        return True
