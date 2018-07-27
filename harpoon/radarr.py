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

class Radarr(object):

    def __init__(self, radarr_info):
       self.radarr_url = radarr_info['radarr_url']
       self.radarr_label = radarr_info['radarr_label']
       self.radarr_headers = radarr_info['radarr_headers']
       self.applylabel = radarr_info['applylabel']
       self.defaultdir = radarr_info['defaultdir']
       self.radarr_rootdir = radarr_info['radarr_rootdir']
       self.torrentfile_dir = radarr_info['torrentfile_dir']
       self.keep_original_foldernames = radarr_info['keep_original_foldernames']
       self.snstat = radarr_info['snstat']
       self.dir_hd_movies = radarr_info['dir_hd_movies']
       self.dir_sd_movies = radarr_info['dir_sd_movies']
       self.dir_web_movies = radarr_info['dir_web_movies']

       #these 2 will only be not None if keep_original_foldernames is enabled as it will return the movie_id & name after the 1st pass of post-processing
       self.radarr_id = radarr_info['radarr_id']
       self.radarr_movie = radarr_info['radarr_movie']

       self.hd_movies_defs = ('720p', '1080p', '4k', '2160p', 'bluray')
       self.sd_movies_defs = ('screener', 'r5', 'dvdrip', 'xvid', 'dvd-rip', 'dvdscr', 'dvdscreener', 'ac3', 'webrip', 'bdrip')
       self.web_movies_defs = ('web-dl', 'webdl','hdrip', 'webrip')

    def post_process(self):
        try:
            with open(os.path.join(self.torrentfile_dir, self.radarr_label, self.snstat['hash'] + '.hash')) as dfile:
                data = json.load(dfile)
        except:
            path = self.torrentfile_dir

            url = self.radarr_url + '/api/history'
            payload = {'pageSize': 1000,
                       'page': 1,
                       'filterKey': 'eventType',
                       'filterValue': 1,
                       'sortKey': 'date',
                       'sortDir': 'desc'}

            check = True
            logger.info('[RADARR] Querying against history now: %s' % payload)
            r = requests.get(url, params=payload, headers=self.radarr_headers)
            logger.info(r.status_code)
            result = r.json()
            hash = None
            #eventType = 'grabbed'
            #downloadClient = 'RTorrent'

            for x in result['records']:
                try:
                    if x['downloadId']:
                        if self.snstat['hash'] == x['downloadId']:
                            hash = x['downloadId']
                            data = x
                            logger.info('[RADARR] file located: %s' % hash)
                            check = False
                            break
                except:
                    continue

        if check is True:
            logger.warn('[RADARR] Unable to locate movie within most recently snatched items. For this to work, the download MUST be initiated via Radarr.')
            return {'status':       False,
                    'radarr_id':    self.radarr_id,
                    'radarr_movie': self.radarr_movie}

        logger.info(data)
        radarr_id = data['movieId']
        radarr_movie = data['movie']['title']
        radarr_root_path = data['movie']['path']
        logger.info('2')
        #we can't run the downloadmoviescan (ie. manual post-processing) since for some reason radarr will push the new download
        #to the original location regardless of any setting previously (it must be storing it in the download table or something)
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
            logger.warn('[RADARR] This is an individual movie, but Radarr will only import from a directory. Creating a temporary directory and moving this so it can proceed.')
            newdir = os.path.join(os.path.abspath(os.path.join(newpath, os.pardir)), os.path.splitext(self.snstat['name'])[0])
            logger.info("[RADARR] Creating directory: %s" % newdir)
            os.makedirs(newdir)
            logger.info('[RADARR] Moving ' + newpath + ' -TO- ' + newdir)
            shutil.move(newpath, newdir)
            newpath = newdir
            logger.info('[RADARR] New path location now set to : ' + newpath)

        url = self.radarr_url + '/api/command'
        payload = {'name': 'downloadedmoviesscan',
                   'path': newpath,
                   'downloadClientID': self.snstat['hash'],
                   'importMode': 'Move'}

        logger.info('[RADARR] Posting to completed download handling now so the file gets moved as per normal: ' + str(payload))
        r = requests.post(url, json=payload, headers=self.radarr_headers)
        data = r.json()

        check = True
        while check:
            try:
                url = self.radarr_url + '/api/command/' + str(data['id'])
                r = requests.get(url, params=None, headers=self.radarr_headers)
                dt = r.json()
            except:
                logger.warn('error returned from sonarr call. Aborting.')
                return False
            else:
                if dt['state'] == 'completed':
                    logger.info('[RADARR] Successfully post-processed : ' + self.snstat['name'])
                    check = False
                else:
                    logger.info('[RADARR] Post-Process of file currently running - will recheck in 60s to see if completed')
                    time.sleep(60)

        if check is False:
            return {'status':       True,
                    'radarr_id':    radarr_id,
                    'radarr_movie': radarr_movie,
                    'radarr_root':  radarr_root_path}
        else:
            return {'status':       False,
                    'radarr_id':    radarr_id,
                    'radarr_movie': radarr_movie,
                    'radarr_root':  radarr_root_path}

    def og_folders(self):
        if self.keep_original_foldernames is True:
            url = self.radarr_url + '/api/movie/' + str(self.radarr_id)

            logger.info('[RADARR] Retrieving existing movie information for %s' % self.radarr_movie)

            r = requests.get(url, headers=self.radarr_headers)
            existingdata = r.json()

            #try updating the path
            logger.info("[RADARR] OLD_PATH: %s" % existingdata['path'])
            existingfilename = None
            try:
                existingfilename = existingdata['movieFile']['relativePath']
                logger.info("[RADARR] OLD_FILENAME: %s" % existingfilename)
            except:
                pass

            #now we check the movieinfo to see what directory we sling it to...
            if all([self.dir_hd_movies is None, self.dir_sd_movies is None, self.dir_web_movies is None]):
                destdir = self.radarr_rootdir
            else:
                logger.info('[RADARR Now checking movie file for further information as to where to sling the final file.')
                destdir = self.moviecheck(existingdata)

            logger.info('[RADARR] Current/Existing Directory: %s' % destdir)

            newpath = os.path.join(destdir, self.snstat['name'])
            logger.info('[RADARR] New Directory: %s' % newpath)

            #makes sure we have enough free space on new location for the move
            st = os.statvfs(destdir)

            dst_freesize = st.f_bavail * st.f_frsize
            src_filesize = 0
            for dirpath, dirnames, filenames in os.walk(existingdata['path']):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    src_filesize += os.path.getsize(fp)

            logger.info('[FREESPACE-CHECK] ' + destdir + ' has ' + str(self.sizeof_fmt(dst_freesize)) + ' free.')
            logger.info('[FREESPACE-CHECK] ' + self.snstat['name'] + ' will consume ' + str(self.sizeof_fmt(src_filesize)) + '.')
            if dst_freesize > src_filesize:
                logger.info('[FREESPACE-CHECK] PASS. Free space available after move: ' + str(self.sizeof_fmt(dst_freesize - src_filesize)) + '.')
            else:
                logger.warn('[FREESPACE-CHECK] FAIL. There is not enough free space on the destination to move file.')
                sys.exit('Not enough free space on destination:' + destdir)

            #move the dir to the new location (if in same dir will do a rename, otherwise will do a copy, then delete)
            shutil.move(existingdata['path'], newpath)
            logger.info("[RADARR] MOVE/RENAME successful to : %s " % newpath)

            url = self.radarr_url + '/api/command'
            refreshpayload = {'name': 'refreshmovie',
                              'movieId': int(self.radarr_id)}

            logger.info("[RADARR] Refreshing movie to make sure old location could not be located anymore: %s" % refreshpayload)
            r = requests.post(url, json=refreshpayload, headers=self.radarr_headers)
            datachk = r.json()
            check = True
            while check:
                url = self.radarr_url + '/api/command/' + str(datachk['id'])
                logger.info("[RADARR] API Submitting: %s" % url)
                r = requests.get(url, params=None, headers=self.radarr_headers)
                dchk = r.json()
                if dchk['state'] == 'completed':
                    check = False
                else:
                    logger.info('[RADARR] Refreshing of movie currently running - will recheck in 10s to see if completed')
                    time.sleep(10)


            url = self.radarr_url + '/api/movie/' + str(self.radarr_id)

            logger.info('[RADARR] Retrieving existing movie information for %s' % self.radarr_movie)

            r = requests.get(url, headers=self.radarr_headers)
            data = r.json()

            data['path'] = u"" + newpath.decode('utf-8')
            data['folderName'] = u"" + self.snstat['name'].decode('utf-8')
            url = self.radarr_url + '/api/movie'
            #set the new path in the json - assume that the torrent name is ALSO the folder name
            #could set folder name to file name via an option..possible to-do.

            logger.info('[RADARR] Updating data for movie: ' + str(data))
            r = requests.put(url, json=data, headers=self.radarr_headers)

            url = self.radarr_url + '/api/command'
            refreshpayload = {'name': 'refreshmovie',
                              'movieId': int(self.radarr_id)}

            logger.info("[RADARR] Refreshing movie to make sure new location is now recognized: %s" % refreshpayload)
            r = requests.post(url, json=refreshpayload, headers=self.radarr_headers)
            datachk = r.json()
            check = True
            while check:
                url = self.radarr_url + '/api/command/' + str(datachk['id'])
                logger.info("[RADARR] API Submitting: %s" % url)
                r = requests.get(url, params=None, headers=self.radarr_headers)
                dchk = r.json()
                if dchk['state'] == 'completed':
                    check = False
                else:
                    logger.info('[RADARR] Refreshing of movie currently running - will recheck in 10s to see if completed')
                    time.sleep(10)

            url = self.radarr_url + '/api/movie/' + str(self.radarr_id)

            logger.info('[RADARR] Retrieving existing movie information for %s' % self.radarr_movie)

            r = requests.get(url, headers=self.radarr_headers)
            data = r.json()

            data['path'] = u"" + newpath.decode('utf-8')
            data['folderName'] = u"" + self.snstat['name'].decode('utf-8')
            url = self.radarr_url + '/api/movie'
            #set the new path in the json - assume that the torrent name is ALSO the folder name
            #could set folder name to file name via an option..possible to-do.

            logger.info('[RADARR] Updating data for movie: ' + str(data))
            r = requests.put(url, json=data, headers=self.radarr_headers)

            url = self.radarr_url + '/api/command'
            refreshpayload = {'name': 'refreshmovie',
                              'movieId': int(self.radarr_id)}

            logger.info("[RADARR] Refreshing movie to make sure new location is now recognized: %s" % refreshpayload)
            r = requests.post(url, json=refreshpayload, headers=self.radarr_headers)
            datachk = r.json()
            check = True
            while check:
                url = self.radarr_url + '/api/command/' + str(datachk['id'])
                logger.info("[RADARR] API Submitting: %s" % url)
                r = requests.get(url, params=None, headers=self.radarr_headers)
                dchk = r.json()
                if dchk['state'] == 'completed':
                    logger.info('[RADARR] Successfully updated paths to original foldername for ' + self.radarr_movie)
                    check = False
                else:
                    logger.info('[RADARR] Refreshing of movie currently running - will recheck in 10s to see if completed')
                    time.sleep(10)


    def moviecheck(self, movieinfo):
        movie_type = None
        logger.info('movieinfo: %s' % movieinfo)
        filename = movieinfo['movieFile']['relativePath']
        logger.info('filename: %s' % filename)
        vsize = str(movieinfo['movieFile']['mediaInfo']['width'])
        logger.info('vsize: %s' % vsize)
        logger.info('[RADARR] Checking for WEB-DL information')
        for webdl in self.web_movies_defs:
            if webdl.lower() in filename.lower():
                logger.info('[RADARR] HD - WEB-DL Movie detected')
                movie_type = 'WEBDL' #movie_type = hd   - will store the hd def (ie. 720p, 1080p)
                break

        logger.info('[RADARR] Checking for HD information')
        if movie_type is None or movie_type == 'HD':   #check the hd to get the match_type since we already know it's HD.
            for hd in self.hd_movies_defs:
                if hd.lower() in filename.lower():
                    logger.info('[MOVIE] HD - Movie detected')
                    movie_type = 'HD' #movie_type = hd   - will store the hd def (ie. 720p, 1080p)
                    break

        logger.info('[RADARR] Checking for SD information')
        if movie_type is None:
            for sd in self.sd_movies_defs:
                if sd.lower() in filename.lower():
                    logger.info('[MOVIE] SD - Movie detected')
                    movie_type = 'SD' #movie_type = sd
                    break

        logger.info('HERE')
        #not sure if right spot, we can determine movie_type (HD/SD) by checking video dimensions.
        #1920/1280 = HD
        #720/640 = SD
        SD_Dimensions = ('720', '640')
        if vsize.startswith(SD_Dimensions):
            logger.info('[MOVIE] SD Movie detected as Dimensions are : ' + str(vsize))
            movie_type = 'SD'
            match_type = 'dimensions'

        logger.info('THERE')
        if movie_type == 'HD':
            dest = self.dir_hd_movies
        elif movie_type == 'WEBDL':
            dest = self.dir_web_movies
        else:
            dest = self.dir_sd_movies

        return dest

    def sizeof_fmt(self, num, suffix='B'):
        for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)

