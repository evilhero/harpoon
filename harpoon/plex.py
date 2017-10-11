import requests
import os
import sys
import base64
import xml.etree.cElementTree as ET

import harpoon
from harpoon import logger

class Plex(object):

    def __init__(self, plexinfo):
        self.plex_update = plexinfo['plex_update']

        if plexinfo['plex_host_port'] is None:
            plex_port = '32400'
        else:
            plex_port = str(plexinfo['plex_host_port'])

        self.plex_host = plexinfo['plex_host_ip'] + ':' + plex_port
        self.plex_login = plexinfo['plex_login']
        self.plex_password = plexinfo['plex_password']
        self.plex_token = plexinfo['plex_token']
        self.plex_label = plexinfo['plex_label']   #the label of the download.
        self.root_path = plexinfo['root_path']
        #self.manual_plex = plexinfo['manual_plex']

    def connect(self):
        tokenchk = self.auth()
        if tokenchk['status'] is False:
            return tokenchk

        sections = self.sections()
        logger.info('[HARPOON-PLEX] Sections Present on PMS: %s' % sections)
        if sections['status'] is True:
            updater = self.update(sections)
            return updater
        else:
            return sections

    def auth(self):
        if self.plex_token == '':
            #step 1 - post request to plex.tv/users/sign_in.json to get x-plex-token since every application needs a unique token.
            url = 'https://plex.tv/users/sign_in.json'
            base64string = base64.encodestring('%s:%s' % (self.plex_login, self.plex_password)).replace('\n', '')

            headers = {'X-Plex-Client-Identifier': 'harpoon2017',
                       'X-Plex-Product':           'Harpoon-PLEX-UPDATER',
                       'X-Plex-Version':           '0.5j',
                       'Authorization':            'Basic %s' % base64string}

            logger.info('[HARPOON-PLEX] Requesting token from Plex.TV for application usage')

            r = requests.post(url, headers=headers, verify=True)
            logger.info('[HARPOON-PLEX] Status Code: %s' % r.status_code)
            if any([r.status_code == 201, r.status_code == 200]):
                data = r.json()
                self.plex_token = data['user']['authToken']
                self.plex_uuid = data['user']['uuid']
                logger.info('[HARPOON-PLEX] Successfully retrieved authorization token for PMS integration')
                logger.info(data)
                return {'status': True}
            else:
                logger.info('[HARPOON-PLEX] Unable to succesfully authenticate - check your settings and will try again next time..')
                return {'status': False}


    def sections(self):
        #step 2 - get the sections
        url = self.plex_host + '/library/sections'
        headers = {'X-Plex-Token': str(self.plex_token)}

        logger.info('[HARPOON-PLEX] Querying plex for library / sections required for application usage.')

        r = requests.get(url, headers=headers)
        logger.info('[HARPOON-PLEX] Status Code: %s' % r.status_code)
        if any([r.status_code == 200, r.status_code == 201]):
            root = ET.fromstring(r.content)
            sections = []
            libraries = {}
            locations = []
            for child in root.iter('Directory'):
                for ch in child.iter('Location'):
                    locations.append({'id':   ch.get('id'),
                                      'path': ch.get('path')})

                sections.append({'title':     child.get('title'),
                                 'key':       child.get('key'),
                                 'locations': locations})
                locations = []

            libraries['sections'] = sections
            libraries['status'] = True
            return libraries
        else:
            logger.info('[HARPOON-PLEX] Unable to retrieve sections from server - cannot update library due to this.')
            return {'status': False}

    def update(self, libraries):
        #step 3 - update the specific section for the harpoon'd item.
        secfound = False
        sect = []
        logger.info('Libraries discovered in PMS: %s' % str(len(libraries['sections'])))
        for x in libraries['sections']:
            if self.root_path is not None:
                for xl in x['locations']:
                    if self.root_path.lower().startswith(xl['path'].lower()):
                        sect.append({'key':    x['key'],
                                     'title':  x['title']})
                        break
            else:
                if self.plex_label.lower() in x['title'].lower():
                    if secfound is False:
                        sect.append({'key':    x['key'],
                                     'title':  x['title']})
                        secfound = True
                    else:
                        logger.info('multiple sections discovered with the same category - will update all')
                        sect.append({'key':    x['key'],
                                     'title':  x['title']})
        logger.info('[HARPOON-PLEX] section match to %s ' % sect)

        status = False
        for x in sect:
            url = self.plex_host + '/library/sections/' + str(x['key']) + '/refresh'
            headers = {'X-Plex-Token': self.plex_token}
            payload = {'force': 0}

            logger.info('[HARPOON-PLEX] Submitting refresh request to specific library %s [%s]' % (x['title'],x['key']))

            r = requests.get(url, data=payload, headers=headers)
            logger.info('[HARPOON-PLEX] Status Code: %s' % r.status_code)
            if r.status_code == 200:
                logger.info('[HARPOON-PLEX] Succesfully submitted for background refresh of library %s' % x['title'])
                status = True
            else:
                logger.info('[HARPOON-PLEX] Unable to submit for background refresh of library %s' % x['title'])
                status = False

        return {'status': status}

#if __name__ == '__main__':
    #pl = Plex()
    #pl.auth()
