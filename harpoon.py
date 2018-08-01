#!/usr/bin/python
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

import sys, os
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'lib'))

import Queue
import threading
import SocketServer
import ConfigParser
import optparse
import re
import time
import json
import requests
import datetime
import hashlib
import bencode
import shutil
from StringIO import StringIO

import harpoon
from harpoon import rtorrent, sabnzbd, unrar, logger, sonarr, radarr, plex, sickrage, mylar, lazylibrarian, lidarr

from apscheduler.scheduler import Scheduler

#global variables
#this is required here to get the log path below
DATADIR = os.path.dirname(os.path.realpath(__file__))
CONF_LOCATION = os.path.join(DATADIR, 'conf', 'harpoon.conf')

config = ConfigParser.SafeConfigParser()
config.read(CONF_LOCATION)

try:
    logpath = config.get('general', 'logpath')
except ConfigParser.NoOptionError:
    logpath = os.path.join(DATADIR, 'logs')

if not os.path.isdir(logpath):
    os.mkdir(logpath)

logger.initLogger(logpath)

try:
    SOCKET_API = config.get('general', 'socket_api')
except ConfigParser.NoOptionError:
    SOCKET_API = None

#secondary queue to keep track of what's not been done, scheduled to be done, and completed.
# 4 stages = to-do, current, reload, completed.
CKQUEUE = []
SNQUEUE = Queue.Queue()

class QueueR(object):


    def __init__(self):

        #accept parser options for cli usage
        description = ("Harpoon. "
                       "A python-based CLI daemon application that will monitor a remote location "
                       "(ie.seedbox) & then download from the remote location to the local "
                       "destination which is running an automation client. "
                       "Unrar, cleanup and client-side post-processing as required. "
                       "Also supports direct dropping of .torrent files into a watch directory. "
                       "Supported client-side applications: "
                       "Sonarr, Radarr, Lidarr, Mylar, LazyLibrarian, SickRage")

        parser = optparse.OptionParser(description=description)
        parser.add_option('-a', '--add', dest='add', help='Specify a filename to snatch from specified torrent client when monitor is running already.')
        parser.add_option('-s', '--hash', dest='hash', help='Specify a HASH to snatch from specified torrent client.')
        parser.add_option('-l', '--label', dest='label', help='For use ONLY with -t, specify a label that the HASH has that harpoon can check against when querying the torrent client.')
        parser.add_option('-t', '--exists', dest='exists', action='store_true', help='In combination with -s (Specify a HASH) & -l (Specify a label) with this enabled and it will not download the torrent (it must exist in the designated location already')
        parser.add_option('-f', '--file', dest='file', help='Specify an exact filename to snatch from specified torrent client. (Will do recursive if more than one file)')
        parser.add_option('-i', '--issueid', dest='issueid', help='In conjunction with -s,-l allows you to specify an exact issueid post-process against (MYLAR ONLY).')
        parser.add_option('-b', '--partial', dest='partial', action='store_true', help='Grab the torrent regardless of completion status (for cherrypicked torrents)')
        parser.add_option('-m', '--monitor', dest='monitor', action='store_true', help='Monitor a designated file location for new files to harpoon.')
        parser.add_option('-d', '--daemon', dest='daemon', action='store_true', help='Daemonize the complete program so it runs in the background.')
        parser.add_option('-p', '--pidfile', dest='pidfile', help='specify a pidfile location to store pidfile for daemon usage.')
        (options, args) = parser.parse_args()

        if options.daemon:
            if sys.platform == 'win32':
                print "Daemonize not supported under Windows, starting normally"
                self.daemon = False
            else:
                self.daemon = True
                options.monitor = True
        else:
            self.daemon = False
        if options.monitor:
            self.monitor = True
        else:
            self.monitor = False

        if options.exists:
            self.exists = True
        else:
            self.exists = False

        if options.issueid:
            self.issueid = options.issueid
        else:
            self.issueid = None

        if options.partial:
            self.partial = True
        else:
            self.partial = False

        if options.pidfile:
            self.pidfile = str(options.pidfile)

            # If the pidfile already exists, harpoon may still be running, so exit
            if os.path.exists(self.pidfile):
                sys.exit("PID file '" + self.pidfile + "' already exists. Exiting.")

            # The pidfile is only useful in daemon mode, make sure we can write the file properly
            if self.daemon:
                self.createpid = True
                try:
                    file(self.pidfile, 'w').write("pid\n")
                except IOError, e:
                    raise SystemExit("Unable to write PID file: %s [%d]" % (e.strerror, e.errno))
            else:
                self.createpid = False
                logger.warn("Not running in daemon mode. PID file creation disabled.")

        else:
            self.pidfile = None
            self.createpid = False

        self.file = options.file
        self.hash = options.hash

        self.working_hash = None
        self.hash_reload = False
        self.not_loaded = 0

        self.conf_location = os.path.join(DATADIR, 'conf', 'harpoon.conf')
        self.applylabel = self.configchk('general', 'applylabel', bool)
        self.defaultdir = self.configchk('general', 'defaultdir', str)
        self.torrentfile_dir = self.configchk('general', 'torrentfile_dir', str)
        self.torrentclient = self.configchk('general', 'torrentclient', str)
        self.lcmdparallel = self.configchk('general', 'lcmd_parallel', int)
        self.lcmdsegments = self.configchk('general', 'lcmd_segments', int)
        if self.lcmdsegments is 0:
            self.lcmdsegments = 6
        if self.lcmdparallel is 0:
            self.lcmdparallel = 2
        #defaultdir is the default download directory on your rtorrent client. This is used to determine if the download
        #should initiate a mirror vs a get (multiple file vs single vs directories)
        self.tvdir = self.configchk('label_directories', 'tvdir', str)
        self.moviedir = self.configchk('label_directories', 'moviedir', str)
        self.musicdir = self.configchk('label_directories', 'musicdir', str)
        self.xxxdir = self.configchk('label_directories', 'xxxdir', str)
        self.comicsdir = self.configchk('label_directories', 'comicsdir', str)
        self.bookdir = self.configchk('label_directories', 'bookdir', str)

        #sabnzbd
        #sab_enable is only used for harpoonshot so it doesn't create extra sab entries ...
        self.sab_enable = self.configchk('sabnzbd', 'sab_enable', bool)
        self.sab_cleanup = self.configchk('sabnzbd', 'sab_cleanup', bool)
        self.sab_url = self.configchk('sabnzbd', 'sab_url', str)
        self.sab_apikey = self.configchk('sabnzbd', 'sab_apikey', str)

        #lftp/transfer
        self.pp_host = self.configchk('post-processing', 'pp_host', str)
        self.pp_sshport = self.configchk('post-processing', 'pp_sshport', int)
        if self.pp_sshport == 0:
            self.pp_sshport = 22
        self.pp_user = self.configchk('post-processing', 'pp_user', str)
        self.pp_passwd = self.configchk('post-processing', 'pp_passwd', str)
        self.pp_keyfile = self.configchk('post-processing', 'pp_keyfile', str)
        self.pp_host2 = self.configchk('post-processing2', 'pp_host2', str)
        self.pp_sshport2 = self.configchk('post-processing2', 'pp_sshport2', int)
        if self.pp_sshport2 == 0:
            self.pp_sshport2 = 22
        self.pp_user2 = self.configchk('post-processing2', 'pp_user2', str)
        self.pp_passwd2 = self.configchk('post-processing2', 'pp_passwd2', str)
        self.pp_keyfile2 = self.configchk('post-processing2', 'pp_keyfile2', str)

        #sickrage
        self.sickrage_label = self.configchk('sickrage', 'sickrage_label', str)
        self.sickrage_conf = {'sickrage_headers': {'Accept': 'application/json'},
                              'sickrage_url':   self.configchk('sickrage', 'url', str),
                              'sickrage_label': self.sickrage_label,
                              'sickrage_delete': self.configchk('sickrage', 'delete', bool),
                              'sickrage_failed': self.configchk('sickrage', 'failed', bool),
                              'sickrage_force_next': self.configchk('sickrage', 'force_next', bool),
                              'sickrage_force_replace': self.configchk('sickrage', 'force_replace', bool),
                              'sickrage_is_priority': self.configchk('sickrage', 'is_priority', bool),
                              'sickrage_process_method': self.configchk('sickrage', 'process_method', str),
                              'sickrage_type': self.configchk('sickrage', 'type', str)}

        #sonarr
        self.sonarr_headers = {'X-Api-Key': self.configchk('sonarr', 'apikey', str),
                               'Accept': 'application/json'}
        self.sonarr_url = self.configchk('sonarr', 'url', str)
        self.sonarr_label = self.configchk('sonarr', 'sonarr_label', str)

        if self.sonarr_url is not None:
            self.tv_choice = 'sonarr'
        elif CONFIG.has_option('sickrage', 'url') is not None:
            self.tv_choice = 'sickrage'
        else:
            self.tv_choice = None

        self.extensions = ['mkv', 'avi', 'mp4', 'mpg', 'mov', 'cbr', 'cbz', 'flac', 'mp3', 'alac', 'epub', 'mobi', 'pdf', 'azw3', '4a', 'm4b', 'm4a']
        newextensions = self.configchk('general', 'extensions', str)
        if newextensions is not None:
            for x in newextensions.split(","):
                if x != "":
                    self.extensions.append(x)

        #radarr
        self.radarr_headers = {'X-Api-Key': self.configchk('radarr', 'apikey', str),
                               'Accept': 'application/json'}
        self.radarr_url = self.configchk('radarr', 'url', str)
        self.radarr_label = self.configchk('radarr', 'radarr_label', str)
        self.radarr_rootdir = self.configchk('radarr', 'radarr_rootdir', str)
        self.radarr_keep_original_foldernames = self.configchk('radarr', 'keep_original_foldernames', bool)
        self.dir_hd_movies = self.configchk('radarr', 'radarr_dir_hd_movies', str)
        self.dir_sd_movies = self.configchk('radarr', 'radarr_dir_sd_movies', str)
        self.dir_web_movies = self.configchk('radarr', 'radarr_dir_web_movies', str)
        self.hd_movies_defs = ('720p', '1080p', '4k', '2160p', 'bluray', 'remux')
        self.sd_movies_defs = ('screener', 'r5', 'dvdrip', 'xvid', 'dvd-rip', 'dvdscr', 'dvdscreener', 'ac3', 'webrip', 'bdrip')
        self.web_movies_defs = ('web-dl', 'webdl', 'hdrip', 'webrip')

        #lidarr
        self.lidarr_headers = {'X-Api-Key': self.configchk('lidarr', 'apikey', str),
                               'Accept': 'application/json'}
        self.lidarr_url = self.configchk('lidarr', 'url', str)
        self.lidarr_label = self.configchk('lidarr', 'lidarr_label', str)


        #mylar
        self.mylar_headers = {'X-Api-Key': 'None', #self.configchk('mylar', 'apikey'),
                              'Accept': 'application/json'}
        self.mylar_apikey = self.configchk('mylar', 'apikey', str)
        self.mylar_url = self.configchk('mylar', 'url', str)
        self.mylar_label = self.configchk('mylar', 'mylar_label', str)

        #lazylibrarian
        self.lazylibrarian_headers = {'Accept': 'application/json'}
        self.lazylibrarian_apikey = self.configchk('lazylibrarian', 'apikey', str)
        self.lazylibrarian_url = self.configchk('lazylibrarian', 'url', str)
        self.lazylibrarian_label = self.configchk('lazylibrarian', 'lazylibrarian_label', str)

        #plex
        self.plex_update = self.configchk('plex', 'plex_update', bool)
        self.plex_host_ip = self.configchk('plex', 'plex_host_ip', str)
        self.plex_host_port = self.configchk('plex', 'plex_host_port', int)
        if self.pp_sshport2 == 0:
            self.plex_host_port = 32400
        self.plex_login = self.configchk('plex', 'plex_login', str)
        self.plex_password = self.configchk('plex', 'plex_password', str)
        self.plex_token = self.configchk('plex', 'plex_token', str)

        self.confinfo = {'sonarr': {'sonarr_headers': self.sonarr_headers,
                                    'sonarr_url':     self.sonarr_url,
                                    'sonarr_label':   self.sonarr_label},
                         'radarr': {'radarr_headers': self.radarr_headers,
                                    'radarr_url':     self.radarr_url,
                                    'radarr_label':   self.radarr_label},
                         'lidarr': {'lidarr_headers': self.lidarr_headers,
                                    'lidarr_url':     self.lidarr_url,
                                    'lidarr_label':   self.lidarr_label},
                         'lazylibrarian': {'lazylibrarian_headers': self.lazylibrarian_headers,
                                    'lazylibrarian_url':     self.lazylibrarian_url,
                                    'lazylibrarian_label':   self.lazylibrarian_label,
                                    'lazylibrarian_apikey':  self.lazylibrarian_apikey},
                         'mylar':  {'mylar_headers':  self.mylar_headers,
                                    'mylar_url':      self.mylar_url,
                                    'mylar_label':    self.mylar_label},
                         'sickrage': {'sickrage_headers': self.sickrage_conf['sickrage_headers'],
                                      'sickrage_url':     self.sickrage_conf['sickrage_url'],
                                      'sickrage_label':   self.sickrage_label},
                         'sab_url':                   self.sab_url,
                         'sab_apikey':                self.sab_apikey,
                         'torrentfile_dir':           self.torrentfile_dir,
                         'conf_location':             self.conf_location}

        if options.daemon:
            self.daemonize()

        logger.info("Initializing background worker thread for queue manipulation.")

        #for multiprocessing (would cause some problems)
        #self.SNQUEUE = Queue()
        #self.SNPOOL = Process(target=self.worker_main, args=(self.SNQUEUE,))
        #self.SNPOOL.daemon = True
        #self.SNPOOL.start()

        #for threading
        self.SNQUEUE = SNQUEUE
        self.SNPOOL = threading.Thread(target=self.worker_main, args=(self.SNQUEUE,))
        self.SNPOOL.setdaemon = True
        self.SNPOOL.start()

        logger.info('TV-Client set to : %s' % self.tv_choice)

        if self.daemon is True:
            #if it's daemonized, fire up the soccket listener to listen for add requests.
            logger.info('[HARPOON] Initializing the API-AWARE portion of Harpoon.')
            #socketlisten.listentome(self.SNQUEUE,)
            #sockme = threading.Thread(target=socketlisten.listentome, args=(self.SNQUEUE,))
            #sockme.setdaemon = True
            #sockme.start()

            HOST, PORT = "localhost", 50007
            server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
            server_thread = threading.Thread(target=server.serve_forever)
            #server_thread.daemon = True
            server_thread.start()
            logger.info('Started...')

        if options.add:
            logger.info('Adding file to queue %s' % options.add)
            self.SNQUEUE.put(options.add)
            return

        if self.monitor:
            self.SCHED = Scheduler()
            logger.info('Setting directory scanner to monitor %s every 2 minutes for new files to harpoon' % self.confinfo['torrentfile_dir'])
            self.scansched = self.ScheduleIt(self.SNQUEUE, self.confinfo, self.working_hash)
            job = self.SCHED.add_interval_job(func=self.scansched.Scanner, minutes=2)
            # start the scheduler now
            self.SCHED.start()
            #run the scanner immediately on startup.
            self.scansched.Scanner()

        elif self.file is not None:
            logger.info('Adding file to queue via FILE %s [label:%s]' % (self.file, options.label))
            self.SNQUEUE.put({'mode':  'file-add',
                              'item':  self.file,
                              'label': options.label})
        elif self.hash is not None:
            logger.info('Adding file to queue via HASH %s [label:%s]' % (self.hash, options.label))
            self.SNQUEUE.put({'mode':  'hash-add',
                              'item':  self.hash,
                              'label': options.label})
        else:
            logger.info('Not enough information given - specify hash / filename')
            return

        while True:
            self.worker_main(self.SNQUEUE)

    def worker_main(self, queue):

        while True:
            if self.monitor:
                if not len(self.SCHED.get_jobs()):
                    logger.debug('Restarting Scanner Job')
                    job = self.scansched.add_interval_job(func=self.scansched.Scanner, minutes=2)
                    self.SCHED.start()
            if self.hash_reload is False:
                if queue.empty():
                    #do a time.sleep here so we don't use 100% cpu
                    time.sleep(5)
                    return #continue
                item = queue.get(True)
                if item['mode'] == 'exit':
                    logger.info('Cleaning up workers for shutdown')
                    return self.shutdown()

                if item['item'] == self.working_hash and item['mode'] == 'current':
                    #file is currently being processed...ignore.
                    logger.warn('hash item from queue ' + item['item'] + ' is already being processed as [' + str(self.working_hash) + ']')
                    return #continue
                else:
                    logger.info('Setting working_hash to [' + item['item'] + ']')
                    ck = [x for x in CKQUEUE if x['hash'] == item['item']]
                    if not ck:
                        CKQUEUE.append({'hash':   item['item'],
                                        'stage':  'current'})
                    self.working_hash = item['item']

                logger.info('[' + item['mode'] +'] Now loading from queue: %s (%s items remaining in queue)' % (item['item'], self.SNQUEUE.qsize()))
            else:
                self.hash_reload = False

            # Check for client type.  If no client set, assume rtorrent.

            if 'client' not in item.keys():
                item['client'] = 'rtorrent'

            #Sonarr stores torrent names without the extension which throws things off.
            #use the below code to reference Sonarr to poll the history and get the hash from the given torrentid
            if item['client'] == 'sabnzbd':
                sa_params = {}
                sa_params['nzo_id'] = item['item']
                sa_params['apikey'] = self.sab_apikey
                try:
                    sab = sabnzbd.SABnzbd(params=sa_params, saburl=self.sab_url)
                    snstat = sab.query()

                except Exception as e:
                    logger.info('ERROR - %s' %e)
                    snstat = None
            else:
                try:
                    if any([item['mode'] == 'file', item['mode'] == 'file-add']):
                        logger.info('sending to rtorrent as file...')
                        rt = rtorrent.RTorrent(file=item['item'], label=item['label'], partial=self.partial, conf=self.conf_location)
                    else:
                        rt = rtorrent.RTorrent(hash=item['item'], label=item['label'], conf=self.conf_location)
                    snstat = rt.main()
                except Exception as e:
                    logger.info('ERROR - %s' % e)
                    snstat = None

                #import torrent.clients.deluge as delu
                #dp = delu.TorrentClient()
                #if not dp.connect():
                #    logger.warn('Not connected to Deluge!')
                #snstat = dp.get_torrent(torrent_hash)


            logger.info('---')
            logger.info(snstat)
            logger.info('---')

            if (snstat is None or not snstat['completed']) and self.partial is False:
                if snstat is None:
                    self.not_loaded +=1
                    logger.warn('[Current attempt: ' + str(self.not_loaded) + '] Cannot locate torrent on client. Ignoring this result for up to 5 retries / 2 minutes')
                    if self.not_loaded > 5:
                        logger.warn('Unable to locate torrent on client. Ensure settings are correct and client is turned on.')
                        self.not_loaded = 0
                        continue

                logger.info('Still downloading in client....let\'s try again in 30 seconds.')
                time.sleep(30)
                #we already popped the item out of the queue earlier, now we need to add it back in.
                queue.put({'mode':  item['mode'],
                           'item':  item['item'],
                           'label': item['label'],
                           'client': item['client']})
            else:
                if self.exists is False:
                    import shlex, subprocess
                    logger.info('Torrent is completed and status is currently Snatched. Attempting to auto-retrieve.')
                    tmp_script = os.path.join(DATADIR, 'snatcher', 'getlftp.sh')
                    with open(tmp_script, 'r') as f:
                        first_line = f.readline()

                    if tmp_script.endswith('.sh'):
                        shell_cmd = re.sub('#!', '', first_line)
                        if shell_cmd == '' or shell_cmd is None:
                            shell_cmd = '/bin/bash'
                    else:
                        shell_cmd = sys.executable

                    curScriptName = shell_cmd + ' ' + str(tmp_script).decode("string_escape")
                    if snstat['mirror'] is True:
                        #downlocation = snstat['folder']
                        logger.info('trying to convert : %s' % snstat['folder'])
                        try:
                            downlocation = snstat['folder'].encode('utf-8')
                            logger.info('[HARPOON] downlocation: %s' % downlocation)
                        except Exception as e:
                            logger.info('utf-8 error: %s' % e)
                    else:
                        try:
                            tmpfolder = snstat['folder'].encode('utf-8')
                            tmpname = snstat['name'].encode('utf-8')
                            logger.info('[UTF-8 SAFETY] tmpfolder, tmpname: %s' % os.path.join(tmpfolder, tmpname))
                        except:
                            pass

                        logger.info('snstat[files]: %s' % snstat['files'][0])
                        #if it's one file in a sub-directory vs one-file in the root...
                        #if os.path.join(snstat['folder'], snstat['name']) != snstat['files'][0]:
                        if os.path.join(tmpfolder, tmpname) != snstat['files'][0]:
                            downlocation = snstat['files'][0].encode('utf-8')
                        else:
                            #downlocation = os.path.join(snstat['folder'], snstat['files'][0])
                            downlocation = os.path.join(tmpfolder, snstat['files'][0].encode('utf-8'))

                    labelit = None
                    if self.applylabel is True:
                        if any([snstat['label'] != 'None', snstat['label'] is not None]):
                            labelit = snstat['label']

                    if snstat['multiple'] is None:
                        multiplebox = '0'
                    else:
                        multiplebox = snstat['multiple']

                    harpoon_env = os.environ.copy()

                    harpoon_env['conf_location'] = self.conf_location
                    harpoon_env['harpoon_location'] = re.sub("'", "\\'",downlocation)
                    harpoon_env['harpoon_location'] = re.sub("!", "\\!",downlocation)
                    harpoon_env['harpoon_label'] = labelit
                    harpoon_env['harpoon_applylabel'] = str(self.applylabel).lower()
                    harpoon_env['harpoon_defaultdir'] = self.defaultdir
                    harpoon_env['harpoon_multiplebox'] = multiplebox

                    if any([downlocation.endswith(ext) for ext in self.extensions]) or snstat['mirror'] is False:
                        combined_lcmd = 'pget -n %s \"%s\"' % (self.lcmdsegments, downlocation)
                        logger.debug('[HARPOON] file lcmd: %s' % combined_lcmd)
                    else:
                        combined_lcmd = 'mirror -P %s --use-pget-n=%s \"%s\"' % (self.lcmdparallel, self.lcmdsegments, downlocation)
                        logger.debug('[HARPOON] folder   lcmd: %s' % combined_lcmd)

                    harpoon_env['harpoon_lcmd'] = combined_lcmd

                    if any([multiplebox == '1', multiplebox == '0']):
                        harpoon_env['harpoon_pp_host'] = self.pp_host
                        harpoon_env['harpoon_pp_sshport'] = str(self.pp_sshport)
                        harpoon_env['harpoon_pp_user'] = self.pp_user
                        if self.pp_keyfile is not None:
                            harpoon_env['harpoon_pp_keyfile'] = self.pp_keyfile
                        else:
                            harpoon_env['harpoon_pp_keyfile'] = ''
                        if self.pp_passwd is not None:
                            harpoon_env['harpoon_pp_passwd'] = self.pp_passwd
                        else:
                            harpoon_env['harpoon_pp_passwd'] = ''
                    else:
                        harpoon_env['harpoon_pp_host'] = self.pp_host2
                        harpoon_env['harpoon_pp_sshport'] = str(self.pp_sshport2)
                        harpoon_env['harpoon_pp_user'] = self.pp_user2
                        if self.pp_keyfile2 is not None:
                            harpoon_env['harpoon_pp_keyfile'] = self.pp_keyfile2
                        else:
                            harpoon_env['harpoon_pp_keyfile'] = ''
                        if self.pp_passwd2 is not None:
                            harpoon_env['harpoon_pp_passwd'] = self.pp_passwd2
                        else:
                            harpoon_env['harpoon_pp_passwd'] = ''

                    logger.info('Downlocation: %s' % re.sub("'", "\\'", downlocation))
                    logger.info('Label: %s' % labelit)
                    logger.info('Multiple Seedbox: %s' % multiplebox)

                    script_cmd = shlex.split(curScriptName)# + [downlocation, labelit, multiplebox]
                    logger.info(u"Executing command " + str(script_cmd))

                    try:
                        p = subprocess.Popen(script_cmd, env=dict(harpoon_env), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                        output, error = p.communicate()
                        if error:
                            logger.warn('[ERROR] %s' % error)
                        if output:
                            logger.info('[OUTPUT] %s'% output)
                    except Exception as e:
                        logger.warn('Exception occured: %s' % e)
                        continue
                    else:
                        snatch_status = 'COMPLETED'

                if all([snstat['label'] == self.sonarr_label, self.tv_choice == 'sonarr']):  #probably should be sonarr_label instead of 'tv'

                    #unrar it, delete the .rar's and post-process against the items remaining in the given directory.
                    cr = unrar.UnRAR(os.path.join(self.defaultdir, self.sonarr_label ,snstat['name']))
                    chkrelease = cr.main()
                    if all([len(chkrelease) == 0, len(snstat['files']) > 1, not os.path.isdir(os.path.join(self.defaultdir, self.sonarr_label, snstat['name']))]):
                        #if this hits, then the retrieval from the seedbox failed probably due to another script moving into a finished/completed directory (ie. race-condition)
                        logger.warn('[SONARR] Problem with snatched files - nothing seems to have downloaded. Retrying the snatch again in case the file was moved from a download location to a completed location on the client.')
                        time.sleep(10)
                        self.hash_reload = True
                        continue


                    logger.info('[SONARR] Placing call to update Sonarr')
                    sonarr_info = {'sonarr_url':      self.sonarr_url,
                                   'sonarr_headers':  self.sonarr_headers,
                                   'applylabel':      self.applylabel,
                                   'defaultdir':      self.defaultdir,
                                   'snstat':          snstat}

                    ss = sonarr.Sonarr(sonarr_info)
                    sonarr_process = ss.post_process()

                    if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                        logger.info('[HARPOON] Removing completed file from queue directory.')
                        try:
                            os.remove(os.path.join(self.torrentfile_dir, self.sonarr_label, item['item'] + '.' + item['mode']))
                            logger.info('[HARPOON] File removed')
                        except:
                            logger.warn('[HARPOON] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading')

                    if sonarr_process is True:
                        logger.info('[SONARR] Successfully post-processed : ' + snstat['name'])
                        if self.sab_enable is True:
                            self.cleanup_check(item, script_cmd, downlocation)
                    else:
                        logger.info('[SONARR] Unable to confirm successful post-processing - this could be due to running out of hdd-space, an error, or something else occuring to halt post-processing of the episode.')
                        logger.info('[SONARR] HASH: %s / label: %s' % (snstat['hash'], snstat['label']))

                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    if all([self.plex_update is True, sonarr_process is True]):
                        #sonarr_file = os.path.join(self.torrentfile_dir, self.sonarr_label, str(snstat['hash']) + '.hash')
                        #with open(filepath, 'w') as outfile:
                        #    json_sonarr = json.load(sonarr_file)
                        #root_path = json_sonarr['path']

                        logger.info('[PLEX-UPDATE] Now submitting update library request to plex')
                        plexit = plex.Plex({'plex_update':     self.plex_update,
                                            'plex_host_ip':    self.plex_host_ip,
                                            'plex_host_port':  str(self.plex_host_port),
                                            'plex_token':      self.plex_token,
                                            'plex_login':      self.plex_login,
                                            'plex_password':   self.plex_password,
                                            'plex_label':      snstat['label'],
                                            'root_path':       None,})

                        pl = plexit.connect()

                        if pl['status'] is True:
                            logger.info('[HARPOON-PLEX-UPDATE] Completed (library is currently being refreshed)')
                        else:
                            logger.warn('[HARPOON-PLEX-UPDATE] Failure - library could NOT be refreshed')

                elif all([snstat['label'] == self.sickrage_label, self.tv_choice == 'sickrage']):
                    #unrar it, delete the .rar's and post-process against the items remaining in the given directory.
                    cr = unrar.UnRAR(os.path.join(self.defaultdir, self.sickrage_label ,snstat['name']))
                    chkrelease = cr.main()
                    if all([len(chkrelease) == 0, len(snstat['files']) > 1, not os.path.isdir(os.path.join(self.defaultdir, self.sickrage_label, snstat['name']))]):
                        #if this hits, then the retrieval from the seedbox failed probably due to another script moving into a finished/completed directory (ie. race-condition)
                        logger.warn('[SICKRAGE] Problem with snatched files - nothing seems to have downloaded. Retrying the snatch again in case the file was moved from a download location to a completed location on the client.')
                        time.sleep(10)
                        self.hash_reload = True
                        continue

                    logger.info('[SICKRAGE] Placing call to update Sickrage')
                    sickrage_info = {'sickrage_conf': self.sickrage_conf,
                                     'applylabel':    self.applylabel,
                                     'defaultdir':    self.defaultdir,
                                     'snstat':        snstat}
                    sr = sickrage.Sickrage(sickrage_info)
                    sickrage_process = sr.post_process()

                    if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                        logger.info('[HARPOON] Removing completed file from queue directory.')
                        try:
                            os.remove(os.path.join(self.torrentfile_dir, self.sickrage_label, item['item'] + '.' + item['mode']))
                            logger.info('[HARPOON] File removed')
                        except:
                            logger.warn('[HARPOON] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading')

                    if sickrage_process is True:
                        logger.info('[SICKRAGE] Successfully post-processed : ' + snstat['name'])
                        self.cleanup_check(item, script_cmd, downlocation)

                    else:
                        logger.info('[SICKRAGE] Unable to confirm successful post-processing - this could be due to running out of hdd-space, an error, or something else occuring to halt post-processing of the episode.')
                        logger.info('[SICKRAGE] HASH: %s / label: %s' % (snstat['hash'], snstat['label']))

                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    if all([self.plex_update is True, sickrage_process is True]):

                        logger.info('[PLEX-UPDATE] Now submitting update library request to plex')
                        plexit = plex.Plex({'plex_update':     self.plex_update,
                                            'plex_host_ip':    self.plex_host_ip,
                                            'plex_host_port':  self.plex_host_port,
                                            'plex_token':      self.plex_token,
                                            'plex_login':      self.plex_login,
                                            'plex_password':   self.plex_password,
                                            'plex_label':      snstat['label'],
                                            'root_path':       None,})

                        pl = plexit.connect()

                        if pl['status'] is True:
                            logger.info('[HARPOON-PLEX-UPDATE] Completed (library is currently being refreshed)')
                        else:
                            logger.warn('[HARPOON-PLEX-UPDATE] Failure - library could NOT be refreshed')

                elif snstat['label'] == self.radarr_label:
                    #check list of files for rar's here...
                    cr = unrar.UnRAR(os.path.join(self.defaultdir, self.radarr_label ,snstat['name']))
                    chkrelease = cr.main()
                    if all([len(chkrelease) == 0, len(snstat['files']) > 1, not os.path.isdir(os.path.join(self.defaultdir, self.radarr_label, snstat['name']))]):
                        #if this hits, then the retrieval from the seedbox failed probably due to another script moving into a finished/completed directory (ie. race-condition)
                        logger.warn('[RADARR] Problem with snatched files - nothing seems to have downloaded. Retrying the snatch again in case the file was moved from a download location to a completed location on the client.')
                        time.sleep(60)
                        self.hash_reload = True
                        continue

                    logger.info('[RADARR] UNRAR - %s' % chkrelease)

                    logger.info('[RADARR] Placing call to update Radarr')

                    radarr_info = {'radarr_url':                self.radarr_url,
                                   'radarr_label':              self.radarr_label,
                                   'radarr_headers':            self.radarr_headers,
                                   'applylabel':                self.applylabel,
                                   'defaultdir':                self.defaultdir,
                                   'radarr_rootdir':            self.radarr_rootdir,
                                   'torrentfile_dir':           self.torrentfile_dir,
                                   'keep_original_foldernames': self.radarr_keep_original_foldernames,
                                   'dir_hd_movies':             self.dir_hd_movies,
                                   'dir_sd_movies':             self.dir_sd_movies,
                                   'dir_web_movies':            self.dir_web_movies,
                                   'radarr_id':                 None,
                                   'radarr_movie':              None,
                                   'snstat':                    snstat}

                    rr = radarr.Radarr(radarr_info)
                    radarr_process = rr.post_process()

                    if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                        logger.info('[HARPOON] Removing completed file from queue directory.')
                        try:
                            os.remove(os.path.join(self.torrentfile_dir, self.radarr_label, item['item'] + '.' + item['mode']))
                            logger.info('[HARPOON] File removed')
                        except:
                            logger.warn('[HARPOON] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading.')

                    if self.radarr_keep_original_foldernames is True:
                        logger.info('[HARPOON] Keep Original FolderNames are enabled for Radarr. Altering paths ...')
                        radarr_info['radarr_id'] = radarr_process['radarr_id']
                        radarr_info['radarr_movie'] = radarr_process['radarr_movie']

                        rof = radarr.Radarr(radarr_info)
                        radarr_keep_og = rof.og_folders()

                    if radarr_process['status'] is True:
                        logger.info('[RADARR] Successfully post-processed : ' + snstat['name'])
                        self.cleanup_check(item, script_cmd, downlocation)
                    else:
                        logger.info('[RADARR] Unable to confirm successful post-processing - this could be due to running out of hdd-space, an error, or something else occuring to halt post-processing of the movie.')
                        logger.info('[RADARR] HASH: %s / label: %s' % (snstat['hash'], snstat['label']))

                    logger.info('[RADARR] Successfully completed post-processing of ' + snstat['name'])
                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    if all([self.plex_update is True, radarr_process['status'] is True]):
                        logger.info('[PLEX-UPDATE] Now submitting update library request to plex')
                        plexit = plex.Plex({'plex_update':     self.plex_update,
                                            'plex_host_ip':    self.plex_host_ip,
                                            'plex_host_port':  self.plex_host_port,
                                            'plex_token':      self.plex_token,
                                            'plex_login':      self.plex_login,
                                            'plex_password':   self.plex_password,
                                            'plex_label':      snstat['label'],
                                            'root_path':       radarr_process['radarr_root']})
                        pl = plexit.connect()

                        if pl['status'] is True:
                            logger.info('[HARPOON-PLEX-UPDATE] Completed (library is currently being refreshed)')
                        else:
                            logger.warn('[HARPOON-PLEX-UPDATE] Failure - library could NOT be refreshed')

                elif snstat['label'] == self.lidarr_label:
                    #check list of files for rar's here...
                    cr = unrar.UnRAR(os.path.join(self.defaultdir, self.lidarr_label ,snstat['name']))
                    chkrelease = cr.main()
                    if all([len(chkrelease) == 0, len(snstat['files']) > 1, not os.path.isdir(os.path.join(self.defaultdir, self.lidarr_label, snstat['name']))]):
                        #if this hits, then the retrieval from the seedbox failed probably due to another script moving into a finished/completed directory (ie. race-condition)
                        logger.warn('[LIDARR] Problem with snatched files - nothing seems to have downloaded. Retrying the snatch again in case the file was moved from a download location to a completed location on the client.')
                        time.sleep(60)
                        self.hash_reload = True
                        continue

                    logger.info('[LIDARR] UNRAR - %s' % chkrelease)

                    logger.info('[LIDARR] Placing call to update Lidarr')

                    lidarr_info = {'lidarr_url':                self.lidarr_url,
                                   'lidarr_label':              self.lidarr_label,
                                   'lidarr_headers':            self.lidarr_headers,
                                   'applylabel':                self.applylabel,
                                   'defaultdir':                self.defaultdir,
                                   'torrentfile_dir':           self.torrentfile_dir,
                                   'snstat':                    snstat}

                    lr = lidarr.Lidarr(lidarr_info)
                    lidarr_process = lr.post_process()

                    if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                        logger.info('[HARPOON] Removing completed file from queue directory.')
                        try:
                            os.remove(os.path.join(self.torrentfile_dir, self.lidarr_label, item['item'] + '.' + item['mode']))
                            logger.info('[HARPOON] File removed')
                        except:
                            logger.warn('[HARPOON] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading.')

                    if lidarr_process is True:
                        logger.info('[LIDARR] Successfully post-processed : ' + snstat['name'])
                        self.cleanup_check(item, script_cmd, downlocation)
                    else:
                        logger.info('[LIDARR] Unable to confirm successful post-processing - this could be due to running out of hdd-space, an error, or something else occuring to halt post-processing of the movie.')
                        logger.info('[LIDARR] HASH: %s / label: %s' % (snstat['hash'], snstat['label']))

                    logger.info('[LIDARR] Successfully completed post-processing of ' + snstat['name'])
                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    if all([self.plex_update is True, lidarr_process is True]):
                        logger.info('[PLEX-UPDATE] Now submitting update library request to plex')
                        plexit = plex.Plex({'plex_update':     self.plex_update,
                                            'plex_host_ip':    self.plex_host_ip,
                                            'plex_host_port':  self.plex_host_port,
                                            'plex_token':      self.plex_token,
                                            'plex_login':      self.plex_login,
                                            'plex_password':   self.plex_password,
                                            'plex_label':      snstat['label']})
                        pl = plexit.connect()

                        if pl['status'] is True:
                            logger.info('[HARPOON-PLEX-UPDATE] Completed (library is currently being refreshed)')
                        else:
                            logger.warn('[HARPOON-PLEX-UPDATE] Failure - library could NOT be refreshed')

                elif snstat['label'] == self.lazylibrarian_label:
                    #unrar it, delete the .rar's and post-process against the items remaining in the given directory.
                    cr = unrar.UnRAR(os.path.join(self.defaultdir, self.lazylibrarian_label ,snstat['name']))
                    chkrelease = cr.main()
                    if all([len(chkrelease) == 0, len(snstat['files']) > 1, not os.path.isdir(os.path.join(self.defaultdir, self.lazylibrarian_label, snstat['name']))]):
                        #if this hits, then the retrieval from the seedbox failed probably due to another script moving into a finished/completed directory (ie. race-condition)
                        logger.warn('[LAZYLIBRARIAN] Problem with snatched files - nothing seems to have downloaded. Retrying the snatch again in case the file was moved from a download location to a completed location on the client.')
                        time.sleep(10)
                        self.hash_reload = True
                        continue

                    logger.info('[LAZYLIBRARIAN] Placing call to update LazyLibrarian')
                    ll_file = os.path.join(self.torrentfile_dir, self.lazylibrarian_label, item['item'] + '.' + item['mode'])
                    if os.path.isfile(ll_file):
                        ll_filedata = json.load(open(ll_file))
                        logger.info('[LAZYLIBRARIAN] File data loaded.')
                    else:
                        ll_filedata = None
                        logger.info('[LAZYLIBRARIAN] File data NOT loaded.')
                    ll_info = {'lazylibrarian_headers': self.lazylibrarian_headers,
                                          'lazylibrarian_url': self.lazylibrarian_url,
                                          'lazylibrarian_label': self.lazylibrarian_label,
                                          'lazylibrarian_apikey': self.lazylibrarian_apikey,
                                          'lazylibrarian_filedata': ll_filedata,
                                          'applylabel':    self.applylabel,
                                          'defaultdir':    self.defaultdir,
                                          'snstat':        snstat}
                    ll = lazylibrarian.LazyLibrarian(ll_info)
                    logger.info('[LAZYLIBRARIAN] Processing')
                    lazylibrarian_process = ll.post_process()

                    if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                        logger.info('[HARPOON] Removing completed file from queue directory.')
                        try:
                            os.remove(os.path.join(self.torrentfile_dir, self.lazylibrarian_label, item['item'] + '.' + item['mode']))
                            logger.info('[HARPOON] File removed')
                        except:
                            logger.warn('[HARPOON] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading')

                    if lazylibrarian_process is True:
                        logger.info('[LAZYLIBRARIAN] Successfully post-processed : ' + snstat['name'])
                        self.cleanup_check(item, script_cmd, downlocation)

                    else:
                        logger.info('[LAZYLIBRARIAN] Unable to confirm successful post-processing - this could be due to running out of hdd-space, an error, or something else occuring to halt post-processing of the episode.')
                        logger.info('[LAZYLIBRARIAN] HASH: %s / label: %s' % (snstat['hash'], snstat['label']))

                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    if all([self.plex_update is True, lazylibrarian_process is True]):

                        logger.info('[PLEX-UPDATE] Now submitting update library request to plex')
                        plexit = plex.Plex({'plex_update':     self.plex_update,
                                            'plex_host_ip':    self.plex_host_ip,
                                            'plex_host_port':  self.plex_host_port,
                                            'plex_token':      self.plex_token,
                                            'plex_login':      self.plex_login,
                                            'plex_password':   self.plex_password,
                                            'plex_label':      snstat['label'],
                                            'root_path':       None,})

                        pl = plexit.connect()

                        if pl['status'] is True:
                            logger.info('[HARPOON-PLEX-UPDATE] Completed (library is currently being refreshed)')
                        else:
                            logger.warn('[HARPOON-PLEX-UPDATE] Failure - library could NOT be refreshed')


                elif snstat['label'] == 'music':
                    logger.info('[MUSIC] Successfully auto-snatched!')
                    self.cleanup_check(item, script_cmd, downlocation)
                    if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                        logger.info('[MUSIC] Removing completed file from queue directory.')
                        try:
                            os.remove(os.path.join(self.torrentfile_dir, snstat['label'], item['item'] + '.' + item['mode']))
                            logger.info('[MUSIC] File removed from system so no longer queuable')
                        except:
                            try:
                                os.remove(os.path.join(self.torrentfile_dir, snstat['label'], snstat['hash'] + '.hash'))
                                logger.info('[MUSIC] File removed by hash from system so no longer queuable')
                            except:
                                logger.warn('[MUSIC] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading.')
                    else:
                        logger.info('[MUSIC] Completed status returned for manual post-processing of file.')

                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    logger.info('Auto-Snatch of torrent completed.')

                elif snstat['label'] == 'xxx':
                    logger.info('[XXX] Successfully auto-snatched!')
                    self.cleanup_check(item, script_cmd, downlocation)
                    if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                        logger.info('[XXX] Removing completed file from queue directory.')
                        try:
                            os.remove(os.path.join(self.torrentfile_dir, snstat['label'], item['item'] + '.' + item['mode']))
                            logger.info('[XXX] File removed')
                        except:
                            try:
                                os.remove(os.path.join(self.torrentfile_dir, snstat['label'], snstat['hash'] + '.hash'))
                                logger.info('[MUSIC] XXX removed by hash from system so no longer queuable')
                            except:
                                logger.warn('[XXX] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading.')
                    else:
                        logger.info('[XXX] Completed status returned for manual post-processing of file.')

                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    logger.info('Auto-Snatch of torrent completed.')

                elif snstat['label'] == self.mylar_label:

                    logger.info('[MYLAR] Placing call to update Mylar')
                    mylar_info = {'mylar_url':        self.mylar_url,
                                  'mylar_headers':    self.mylar_headers,
                                  'mylar_apikey':     self.mylar_apikey,
                                  'mylar_label':      self.mylar_label,
                                  'applylabel':       self.applylabel,
                                  'issueid':          self.issueid,
                                  'torrentfile_dir':  self.torrentfile_dir,
                                  'defaultdir':       self.defaultdir,
                                  'snstat':           snstat}

                    my = mylar.Mylar(mylar_info)
                    mylar_process = my.post_process()

                    logger.info('[MYLAR] Successfully auto-snatched!')
                    self.cleanup_check(item, script_cmd, downlocation)
                    if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                        logger.info('[MYLAR] Removing completed file from queue directory.')
                        try:
                            os.remove(os.path.join(self.torrentfile_dir, snstat['label'], item['item'] + '.' + item['mode']))
                            logger.info('[MYLAR] File removed')
                        except:
                            try:
                                os.remove(os.path.join(self.torrentfile_dir, snstat['label'], snstat['hash'] + '.hash'))
                                logger.info('[MYLAR] File removed by hash from system so no longer queuable')
                            except:
                                logger.warn('[MYLAR] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading.')
                    else:
                        logger.info('[MYLAR] Completed status returned for manual post-processing of file.')

                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    logger.info('Auto-Snatch of torrent completed.')

                else:
                    logger.info('Successfully auto-snatched!')
                    self.cleanup_check(item, script_cmd, downlocation)

                    if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                        logger.info('Removing completed file from queue directory.')
                        try:
                            os.remove(os.path.join(self.torrentfile_dir, snstat['label'], item['item'] + '.' + item['mode']))
                            logger.info('File removed')
                        except:
                            try:
                                os.remove(os.path.join(self.torrentfile_dir, snstat['label'], snstat['hash'] + '.hash'))
                                logger.info('File removed by hash from system so no longer queuable')
                            except:
                                logger.warn('Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading.')
                    else:
                        logger.info('Completed status returned for manual post-processing of file.')

                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    logger.info('Auto-Snatch of torrent completed.')

                if any([item['mode'] == 'hash-add', item['mode'] == 'file-add']) and self.daemon is False:
                    queue.put({'mode': 'exit',
                               'item': 'None'})

    def cleanup_check(self, item, script_cmd, downlocation):
        logger.info('[CLEANUP-CHECK] item: %s' % item)
        if 'client' in item.keys() and self.sab_cleanup and item['client'] == 'sabnzbd':
            import subprocess
            sa_params = {}
            sa_params['nzo_id'] = item['item']
            sa_params['apikey'] = self.sab_apikey
            try:
                sab = sabnzbd.SABnzbd(params=sa_params, saburl=self.sab_url)
                cleanup = sab.cleanup()
            except Exception as e:
                logger.info('ERROR - %s' % e)
                cleanup = None
            harpoon_lcmd = 'rm -r \"%s\"' % downlocation
            try:
                p = subprocess.Popen(script_cmd, env=dict(os.environ, harpoon_lcmd=harpoon_lcmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                output, error = p.communicate()
                if error:
                    logger.warn('[ERROR] %s' % error)
                if output:
                    logger.info('[OUTPUT] %s' % output)
            except Exception as e:
                logger.warn('Exception occured: %s' % e)

    def sizeof_fmt(self, num, suffix='B'):
        for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)


    def configchk(self, section, id, type):
        if config.has_option(section, id):
            try:
                if type == bool:
                    return config.getboolean(section, id)
                elif type == int:
                    return config.getint(section, id)
                elif type == str:
                    return config.get(section, id)
            except ValueError:
                #will be raised if option is left blank in conf, so set it to default value.
                pass
        if type == bool:
            return False
        elif type == int:
            return 0
        elif type == str:
            return None


    def moviecheck(self, movieinfo):
        movie_type = None
        filename = movieinfo['movieFile']['relativePath']
        vsize = str(movieinfo['movieFile']['mediaInfo']['width'])
        for webdl in self.web_movies_defs:
            if webdl.lower() in filename.lower():
                logger.info('[RADARR] HD - WEB-DL Movie detected')
                movie_type = 'WEBDL' #movie_type = hd   - will store the hd def (ie. 720p, 1080p)
                break

        if movie_type is None or movie_type == 'HD':   #check the hd to get the match_type since we already know it's HD.
            for hd in self.hd_movies_defs:
                if hd.lower() in filename.lower():
                    logger.info('[MOVIE] HD - Movie detected')
                    movie_type = 'HD' #movie_type = hd   - will store the hd def (ie. 720p, 1080p)
                    break

        if movie_type is None:
            for sd in self.sd_movies_defs:
                if sd.lower() in filename.lower():
                    logger.info('[MOVIE] SD - Movie detected')
                    movie_type = 'SD' #movie_type = sd
                    break

        #not sure if right spot, we can determine movie_type (HD/SD) by checking video dimensions.
        #1920/1280 = HD
        #720/640 = SD
        SD_Dimensions = ('720', '640')
        if vsize.startswith(SD_Dimensions):
            logger.info('[MOVIE] SD Movie detected as Dimensions are : ' + str(vsize))
            movie_type = 'SD'
            match_type = 'dimensions'

        if movie_type == 'HD':
            dest = self.dir_hd_movies
        elif movie_type == 'WEBDL':
            dest = self.dir_web_movies
        else:
            dest = self.dir_sd_movies

        return dest

    def daemonize(self):

        if threading.activeCount() != 1:
            logger.warn('There are %r active threads. Daemonizing may cause \
                            strange behavior.' % threading.enumerate())

        sys.stdout.flush()
        sys.stderr.flush()

        # Do first fork
        try:
            pid = os.fork()
            if pid == 0:
                pass
            else:
                # Exit the parent process
                logger.debug('Forking once...')
                os._exit(0)
        except OSError, e:
            sys.exit("1st fork failed: %s [%d]" % (e.strerror, e.errno))

        os.setsid()

        # Make sure I can read my own files and shut out others
        prev = os.umask(0)  # @UndefinedVariable - only available in UNIX
        os.umask(prev and int('077', 8))

        # Do second fork
        try:
            pid = os.fork()
            if pid > 0:
                logger.debug('Forking twice...')
                os._exit(0) # Exit second parent process
        except OSError, e:
            sys.exit("2nd fork failed: %s [%d]" % (e.strerror, e.errno))

        dev_null = file('/dev/null', 'r')
        os.dup2(dev_null.fileno(), sys.stdin.fileno())

        si = open('/dev/null', "r")
        so = open('/dev/null', "a+")
        se = open('/dev/null', "a+")

        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        pid = os.getpid()
        logger.info('Daemonized to PID: %s' % pid)
        if self.createpid:
            logger.info("Writing PID %d to %s", pid, self.pidfile)
            with file(self.pidfile, 'w') as fp:
                fp.write("%s\n" % pid)

    def shutdown(self):
        logger.info('Now Shutting DOWN')
        try:
            self.SNPOOL.join(10)
            logger.info('Joined pool for termination - Successful')
        except KeyboardInterrupt:
            SNQUEUE.put('exit')
            self.SNPOOL.join(5)
        except AssertionError:
            os._exit(0)

        if self.createpid:
            logger.info('Removing pidfile %s' % self.pidfile)
            os.remove(self.pidfile)

        os._exit(0)

    class ScheduleIt:

        def __init__(self, queue, confinfo, working_hash):
        #if queue.empty():
        #    logger.info('Nothing to do')
        #    return
            self.queue = queue
            self.conf_info = confinfo
            self.current_hash = working_hash

        def Scanner(self):
            extensions = ['.file','.hash','.torrent','.nzb']
            for (dirpath, dirnames, filenames) in os.walk(self.conf_info['torrentfile_dir'],followlinks=True):
                for f in filenames:
                    if any([f.endswith(ext) for ext in extensions]):
                        if f.endswith('.file'):
                            client = None
                            #history only works with sonarr/radarr...
                            #if any([f[-11:] == 'sonarr', f[-11:] == 'radarr']):
                            hash, client = self.history_poll(f[:-5])
                            logger.info('Client: %s' % client)
                            logger.info('hash:' + str(hash))
                            logger.info('working_hash:' + str(self.current_hash))
                            dupchk = [x for x in CKQUEUE if x['hash'] == hash]
                            if all([hash is not None, not dupchk]):
                                logger.info('Adding : ' + f + ' to queue.')

                                if 'sonarr' in f[-11:]:
                                    label = self.conf_info['sonarr']['sonarr_label']
                                elif 'radarr' in f[-11:]:
                                    label = self.conf_info['radarr']['radarr_label']
                                elif 'mylar' in f[-10:]:
                                    label = self.conf_info['mylar']['mylar_label']
                                elif 'sickrage' in f[-13:]:
                                    label = self.conf_info['sickrage']['sickrage_label']
                                elif 'lidarr' in f[-11:]:
                                    label = self.conf_info['lidarr']['lidarr_label']
                                else:
                                    #label = os.path.basename(dirpath)
                                    label = None
                                if client:
                                    self.queue.put({'mode': 'hash',
                                                    'item': hash,
                                                    'label': label,
                                                    'client': client})
                                else:
                                    self.queue.put({'mode': 'hash',
                                                    'item':  hash,
                                                    'label': label})
                                CKQUEUE.append({'hash':   hash,
                                                'stage':  'to-do'})

                                if label is not None:
                                    fpath = os.path.join(self.conf_info['torrentfile_dir'], label, f)
                                else:
                                    fpath = os.path.join(self.conf_info['torrentfile_dir'], f)

                                try:
                                    os.remove(fpath)
                                    logger.info('Succesfully removed file : ' + fpath)
                                except:
                                    logger.warn('Unable to remove file : ' + fpath)
                            else:
                                logger.warn('HASH is already present in queue - but has not been converted to hash for some reason. Ignoring at this time cause I dont know what to do.')
                                logger.warn(CKQUEUE)

                        else:
                            #here we queue it up to send to the client and then monitor.
                            if f.endswith('.torrent'):
                                client = 'rtorrent' # Assumes rtorrent, if we add more torrent clients, this needs to change.
                                subdir = os.path.basename(dirpath)
                                #torrents to snatch should be subfolders in order to apply labels if required.
                                fpath = os.path.join(self.conf_info['torrentfile_dir'], subdir, f)
                                logger.info('label to be set to : ' + str(subdir))
                                logger.info('Filepath set to : ' + str(fpath))
                                tinfo = rtorrent.RTorrent(file=fpath, add=True, label=subdir, conf=self.conf_info['conf_location'])
                                torrent_info = tinfo.main()
                                logger.info(torrent_info)
                                if torrent_info:
                                    hashfile = str(torrent_info['hash']) + '.hash'
                                    os.rename(fpath, os.path.join(self.conf_info['torrentfile_dir'], subdir, hashfile))
                                else:
                                    logger.warn('something went wrong. Exiting')
                                    sys.exit(1)
                                hashfile = hashfile[:-5]
                                mode = 'hash'
                                label = torrent_info['label']
                            elif f.endswith('.nzb'):
                                client = 'sabnzbd' # Assumes sab, if we add more nbz clients, this needs to change
                                subdir = os.path.basename(dirpath)
                                fpath = os.path.join(self.conf_info['torrentfile_dir'], subdir, f)
                                logger.info('Label to be set to : ' + str(subdir))
                                logger.info('Filepath set to : ' + str(fpath))
                                sab_params = {}
                                sab_params['mode'] = 'addfile'
                                sab_params['cat'] = subdir
                                sab_params['apikey'] = self.conf_info['sab_apikey']
                                nzb_connection = sabnzbd.SABnzbd(params=sab_params, saburl=self.conf_info['sab_url'])
                                nzb_info = nzb_connection.sender(files={'name': open(fpath, 'rb')})
                                mode = 'hash'
                                label = str(subdir)
                                logger.debug('SAB Response: %s' % nzb_info)
                                if nzb_info:
                                    hashfile = str(nzb_info['nzo_id']) + '.hash'
                                    os.rename(fpath, os.path.join(self.conf_info['torrentfile_dir'], subdir, hashfile))
                                else:
                                    logger.warn('something went wrong')
                                hashfile = hashfile[:-5]
                            else:
                                label = None
                                if 'mylar' in f[-10:]:
                                    label = self.conf_info['mylar']['mylar_label']
                                    hashfile = f[:-11]
                                elif 'sickrage' in f[-13:]:
                                    label = self.conf_info['sickrage']['sickrage_label']
                                    hashfile = f[:-14]
                                elif 'lazylibrarian' in f[-18:]:
                                    label = self.conf_info['lazylibrarian']['lazylibrarian_label']
                                    hashfile = f[:-19]
                                else:
                                    hashfile = f[:-5]
                                dirp = os.path.basename(dirpath)
                                if label is None and os.path.basename(self.conf_info['torrentfile_dir']) != dirp:
                                    label = dirp
                                mode = f[-4:]
                                actualfile = os.path.join(dirpath, f)
                                try:
                                    filecontent = json.load(open(actualfile))
                                    if filecontent:
                                        if 'data' in filecontent.keys():
                                            if 'downloadClient' in filecontent['data'].keys():
                                                client = filecontent['data']['downloadClient'].lower()
                                        elif 'Source' in filecontent.keys():
                                            client = filecontent['Source'].lower()
                                        elif 'mylar_client' in filecontent.keys():
                                            client = filecontent['mylar_client'].lower()
                                        else:
                                            client = None
                                except Exception as e:
                                    try:
                                        with open(actualfile) as unknown_file:
                                            c = unknown_file.read(1)
                                            if c == '<':
                                                client = 'sabnzbd'
                                            else:
                                                client = 'rtorrent'
                                    except Exception as e:
                                        client = 'rtorrent' # Couldn't read file, assume it's a torrent.

                            #test here to make sure the file isn't being worked on currently & doesnt exist in queue already
                            dupchk = [x for x in CKQUEUE if x['hash'] == hashfile]
                            duplist = []
                            if dupchk:
                                for xc in dupchk:
                                    if xc['stage'] == 'completed':
                                        try:
                                            logger.info('Status is now completed - forcing removal of HASH from queue.')
                                            self.queue.pop(xc['hash'])
                                        except Exception as e:
                                            logger.warn('Unable to locate hash in queue. Was already removed most likely. This was the error returned: %s' % e)
                                            continue
                                    else:
                                        pass
                                        #logger.info('HASH already exists in queue in a status of ' + xc['stage'] + ' - avoiding duplication: ' + hashfile)
                            else:
                                logger.info('HASH not in queue - adding : ' + hashfile)
                                logger.info('Client: %s' % client)
                                CKQUEUE.append({'hash':   hashfile,
                                                'stage':  'to-do'})
                                if client:
                                    self.queue.put({'mode':   mode,
                                                    'item':   hashfile,
                                                    'label':  label,
                                                    'client': client})
                                else:
                                    self.queue.put({'mode':   mode,
                                                    'item':   hashfile,
                                                    'label':  label})
                                hashfile = str(hashfile) + '.hash'
                                if label is not None:
                                    fpath = os.path.join(self.conf_info['torrentfile_dir'], label, f)
                                    npath = os.path.join(self.conf_info['torrentfile_dir'], label, hashfile)
                                else:
                                    fpath = os.path.join(self.conf_info['torrentfile_dir'], f)
                                    npath = os.path.join(self.conf_info['torrentfile_dir'], hashfile)

                                try:
                                    os.rename(fpath,npath)
                                    logger.info('Succesfully renamed file to ' + npath)
                                except Exception as e:
                                    logger.warn('[%s] Unable to rename file %s to %s' % (e, fpath, npath))
                                    continue

        def history_poll(self, torrentname):
            path = self.conf_info['torrentfile_dir']
            if 'sonarr' in torrentname[-6:]:
                historyurl = self.conf_info['sonarr']['sonarr_url']
                headers = self.conf_info['sonarr']['sonarr_headers']
                label = self.conf_info['sonarr']['sonarr_label']
                url = historyurl + '/api/history'
                mode = 'sonarr'
            elif 'radarr' in torrentname[-6:]:
                historyurl = self.conf_info['radarr']['radarr_url']
                headers = self.conf_info['radarr']['radarr_headers']
                label = self.conf_info['radarr']['radarr_label']
                url = historyurl + '/api/history'
                mode = 'radarr'
            elif 'lidarr' in torrentname[-6:]:
                historyurl = self.conf_info['lidarr']['lidarr_url']
                headers = self.conf_info['lidarr']['lidarr_headers']
                label = self.conf_info['lidarr']['lidarr_label']
                url = historyurl + '/api/v1/history'

            torrentname = torrentname[:-7]
            payload = {'pageSize': 1000,
                       'page': 1,
                       'filterKey': 'eventType',
                       'filterValue': 1,
                       'sortKey': 'date',
                       'sortDir': 'desc'}

            logger.info('Quering against history now: %s' % payload)
            r = requests.get(url, params=payload, headers=headers)
            logger.info(r.status_code)
            result = r.json()
            hash = None
            client = None
            logger.info(torrentname)
            for x in result['records']:
                #logger.info(x)
                if self.filesafe(torrentname.lower()) == self.filesafe(x['sourceTitle'].lower()):
                    hash = x['downloadId']
                    client = x['data']['downloadClient'].lower()
                    info = x
                    logger.info('file located as HASH: %s' % hash)
                    break

            if hash is not None:

                filepath = os.path.join(path, label, str(hash) + '.hash')

                #create empty file with the given filename and update the mtime
                with open(filepath, 'w') as outfile:
                    json.dump(info, outfile)

                logger.info("wrote to snatch queue-directory %s" % filepath)
#            try:
#                os.remove(os.path.join(path, torrentname + '.' + mode + '.file'))
#            except:
#                logger.warn('file doesnt exist...ignoring deletion of .file remnant')

            else:
                logger.info('No hash discovered - this requires the torrent name, NOT the filename')

            return hash, client

        def get_the_hash(self, filepath):
            # Open torrent file
            torrent_file = open(filepath, "rb")
            metainfo = bencode.decode(torrent_file.read())
            info = metainfo['info']
            thehash = hashlib.sha1(bencode.encode(info)).hexdigest().upper()
            logger.info('Hash: ' + thehash)
            return thehash

        def get_free_space(self, folder, min_threshold=100000000):
            #threshold for minimum amount of freespace available (#100mb)
            st = os.statvfs(folder)
            dst_freesize = st.f_bavail * st.f_frsize
            logger.debug('[FREESPACE-CHECK] %s has %s free' % (folder, self.sizeof_fmt(dst_freesize)))
            if min_threshold > dst_freesize:
                logger.warn('[FREESPACE-CHECK] There is only %s space left on %s' % (dst_freesize, folder))
                return False
            else:
                return True

        def sizeof_fmt(self, num, suffix='B'):
            for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
                if abs(num) < 1024.0:
                    return "%3.1f%s%s" % (num, unit, suffix)
                num /= 1024.0
            return "%.1f%s%s" % (num, 'Yi', suffix)

        def filesafe(self, name):
            import unicodedata

            try:
                name = name.decode('utf-8')
            except:
                pass

            if u'\u2014' in name:
                name = re.sub(u'\u2014', ' - ', name)
            try:
                u_name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').strip()
            except TypeError:
                u_name = name.encode('ASCII', 'ignore').strip()

            name_filesafe = re.sub('[\:\'\"\,\?\!\\\]', '', u_name)
            name_filesafe = re.sub('[\/\*]', '-', name_filesafe)

            return name_filesafe


class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):

    def handle(self):
        d = self.request.recv(1024)
        dt = d.split("\n")[1]
        data = json.loads(dt)
        #logger.info(type(data))
        if data['apikey'] == SOCKET_API:
            if data['mode'] == 'add':
                logger.info('[API-AWARE] Request received via API for item [%s] to be remotely added to queue:' % data['hash'])
                addq = self.add_queue(data)
                queue_position = self.IndexableQueue(data['hash'])
                if addq is True:
                    self.send({'Status': True, 'Message': 'Successful authentication', 'Added': True, 'QueuePosition': queue_position})
                else:
                    self.send({'Status': True, 'Message': 'Successful authentication', 'Added': False})
            elif data['mode'] == 'queue':
                logger.info('[API-AWARE] Request received via API for listing of current queue')
                currentqueue = None
                if SNQUEUE.qsize() != 0:
                    for x in reversed(CKQUEUE):
                        if x['stage'] == 'current':
                            currentqueue = x
                            logger.info('currentqueue: %s' % currentqueue)
                            break
                self.send({'Status': True, 'QueueSize': SNQUEUE.qsize(), 'CurrentlyInProgress': currentqueue, 'QueueContent': list(SNQUEUE.queue)})
        else:
            self.send({'Status': False, 'Message': 'Invalid APIKEY', 'Added': False})
            return

    def recv(self):
        return self._recv(self.request)

    def send(self, data):
        self._send(self.request, data)
        return self

    def _send(self, socket, data):
        try:
            serialized = json.dumps(data)
        except (TypeError, ValueError), e:
            raise Exception('You can only send JSON-serializable data')
        # send the length of the serialized data first
        socket.send('%d\n' % len(serialized))
        # send the serialized data
        socket.sendall(serialized)

    def _recv(self, socket):
        # read the length of the data, letter by letter until we reach EOL
        length_str = ''
        char = socket.recv(1)
        while char != '\n':
            length_str += char
            char = socket.recv(1)
        total = int(length_str)
        # use a memoryview to receive the data chunk by chunk efficiently
        view = memoryview(bytearray(total))
        next_offset = 0
        while total - next_offset > 0:
            recv_size = socket.recv_into(view[next_offset:], total - next_offset)
            next_offset += recv_size
        try:
            deserialized = json.loads(view.tobytes())
        except (TypeError, ValueError), e:
            raise Exception('Data received was not in JSON format')
        return deserialized

    def add_queue(self, data):
        try:
            item = data['file']
            mode = 'file'
        except:
            item = data['hash']
            mode = 'hash'
        try:
            if mode == 'file':
                logger.info('[API-AWARE] Adding file to queue via FILE %s [label:%s]' % (data['file'], data['label']))
                SNQUEUE.put({'mode':  'file-add',
                             'item':  data['file'],
                             'label': data['label']})

            elif mode == 'hash':
                logger.info('[API-AWARE] Adding file to queue via HASH %s [label:%s]' % (data['hash'], data['label']))
                SNQUEUE.put({'mode':  'hash-add',
                             'item':  data['hash'],
                             'label': data['label']})
            else:
                logger.info('[API-AWARE] Unsupported mode or error in parsing. Ignoring request [%s]' % data)
                return False
        except:
            logger.info('[API-AWARE] Unsupported mode or error in parsing. Ignoring request [%s]' % data)
            return False
        else:
            logger.warn('[API-AWARE] Successfully added to queue - Prepare for GLORIOUS retrieval')
            return True

    def IndexableQueue(self, item):
        import collections
        d = list(SNQUEUE.queue)
        queue_position = [i for i,t in enumerate(d) if t['item'] == item]
        queue_pos = '%s/%s' % (''.join(str(e) for e in queue_position), SNQUEUE.qsize())
        logger.info('queue position of %s' % queue_pos)
        return queue_pos

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass

if __name__ == '__main__':
    gf = QueueR()

