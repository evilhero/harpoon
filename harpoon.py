#!/usr/bin/python
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

import harpoon
from harpoon import rtorrent, unrar, logger, sonarr, radarr, plex, sickrage

from apscheduler.scheduler import Scheduler

#this is required here to get the log path below
DATADIR = os.path.dirname(os.path.realpath(__file__))

config = ConfigParser.SafeConfigParser()
config.read(os.path.join(DATADIR, 'conf', 'harpoon.conf'))

logpath = config.get('general', 'logpath')
logger.initLogger(logpath)

#secondary queue to keep track of what's not been done, scheduled to be done, and completed.
# 4 stages = to-do, current, reload, completed.
CKQUEUE = []
SNQUEUE = Queue.Queue()

class QueueR(object):


    def __init__(self):

        #accept parser options for cli usage
        parser = optparse.OptionParser()
        parser.add_option('-a', '--add', dest='add', help='Specify a filename to snatch from specified torrent client when monitor is running already.')
        parser.add_option('-s', '--hash', dest='hash', help='Specify a HASH to snatch from specified torrent client.')
        parser.add_option('-l', '--label', dest='label', help='For use ONLY with -t, specify a label that the HASH has that harpoon can check against when querying the torrent client.')
        parser.add_option('-t', '--exists', dest='exists', action='store_true', help='In combination with -s (Specify a HASH) & -l (Specify a label) with this enabled and it will not download the torrent (it must exist in the designated location already')
        parser.add_option('-f', '--file', dest='file', help='Specify an exact filename to snatch from specified torrent client. (Will do recursive if more than one file)')
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

        if options.partial:
            self.partial = True
        else:
            self.partial = False

        if options.pidfile:
            self.pidfile = str(options.pidfile)

            # If the pidfile already exists, mylar may still be running, so exit
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
        self.socket_api = config.get('general', 'socket_api')
        self.applylabel = config.get('general', 'applylabel')
        self.defaultdir = config.get('general', 'defaultdir')
        self.torrentfile_dir = config.get('general', 'torrentfile_dir')
        self.torrentclient = config.get('general', 'torrentclient')

        #defaultdir is the default download directory on your rtorrent client. This is used to determine if the download
        #should initiate a mirror vs a get (multiple file vs single vs directories)
        self.tvdir = config.get('label_directories', 'tvdir')
        self.moviedir = config.get('label_directories', 'moviedir')
        self.musicdir = config.get('label_directories', 'musicdir')
        self.xxxdir = config.get('label_directories', 'xxxdir')
        self.comicsdir = config.get('label_directories', 'comicsdir')

        #sickrage
        self.sickrage_label = config.has_option('sickrage', 'sickrage_label')
        self.sickrage_conf = {'sickrage_headers': {'Accept': 'application/json'},
                              'sickrage_url':   config.has_option('sickrage', 'url'),
                              'sickrage_label': self.sickrage_label,
                              'sickrage_delete': config.has_option('sickrage', 'sickrage_delete'),
                              'sickrage_failed': config.has_option('sickrage', 'sickrage_failed'),
                              'sickrage_force_next': config.has_option('sickrage', 'sickrage_force_next'),
                              'sickrage_force_replace': config.has_option('sickrage', 'sickrage_force_replace'),
                              'sickrage_is_priority': config.has_option('sickrage', 'sickrage_is_priority'),
                              'sickrage_process_method': config.has_option('sickrage', 'sickrage_proces_method'),
                              'sickrage_type': config.has_option('sickrage', 'sickrage_type')}

        #sonarr
        self.sonarr_headers = {'X-Api-Key': config.get('sonarr', 'apikey'),
                               'Accept': 'application/json'}
        self.sonarr_url = config.get('sonarr', 'url')
        self.sonarr_label = config.get('sonarr', 'sonarr_label')

        if self.sonarr_url is not None:
            self.tv_choice = 'sonarr'
        elif config.has_option('sickrage', 'url') is not None:
            self.tv_choice = 'sickrage'
        else:
            self.tv_choice = None


        #radarr
        self.radarr_headers = {'X-Api-Key': config.get('radarr', 'apikey'),
                               'Accept': 'application/json'}
        self.radarr_url = config.get('radarr', 'url')
        self.radarr_label = config.get('radarr', 'radarr_label')
        self.radarr_rootdir = config.get('radarr', 'radarr_rootdir')
        self.radarr_keep_original_foldernames = config.getboolean('radarr', 'keep_original_foldernames')
        self.dir_hd_movies = config.get('radarr', 'radarr_dir_hd_movies')
        self.dir_sd_movies = config.get('radarr', 'radarr_dir_sd_movies')
        self.dir_web_movies = config.get('radarr', 'radarr_dir_web_movies')
        self.hd_movies_defs = ('720p', '1080p', '4k', '2160p', 'bluray', 'remux')
        self.sd_movies_defs = ('screener', 'r5', 'dvdrip', 'xvid', 'dvd-rip', 'dvdscr', 'dvdscreener', 'ac3', 'webrip', 'bdrip')
        self.web_movies_defs = ('web-dl', 'webdl', 'hdrip', 'webrip')


        #mylar
        self.mylar_headers = {'X-Api-Key': 'None', #config.get('mylar', 'apikey'),
                              'Accept': 'application/json'}
        self.mylar_url = config.get('mylar', 'url')
        self.mylar_label = config.get('mylar', 'mylar_label')

        #plex
        self.plex_update = config.getboolean('plex', 'plex_update')
        self.plex_host_ip = config.get('plex', 'plex_host_ip')
        self.plex_host_port = config.get('plex', 'plex_host_port')
        self.plex_login = config.get('plex', 'plex_login')
        self.plex_password = config.get('plex', 'plex_password')
        self.plex_token = config.get('plex', 'plex_token')

        self.confinfo = {'sonarr': {'sonarr_headers': self.sonarr_headers,
                                    'sonarr_url':     self.sonarr_url,
                                    'sonarr_label':   self.sonarr_label},
                         'radarr': {'radarr_headers': self.radarr_headers,
                                    'radarr_url':     self.radarr_url,
                                    'radarr_label':   self.radarr_label},
                         'mylar':  {'mylar_headers':  self.mylar_headers,
                                    'mylar_url':      self.mylar_url,
                                    'mylar_label':    self.mylar_label},
                         'sickrage': {'sickrage_headers': self.sickrage_conf['sickrage_headers'],
                                      'sickrage_url':     self.sickrage_conf['sickrage_url'],
                                      'sickrage_label':   self.sickrage_label},

                         'torrentfile_dir':           self.torrentfile_dir}

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
            SCHED = Scheduler()
            logger.info('Setting directory scanner to monitor %s every 2 minutes for new files to harpoon' % self.confinfo['torrentfile_dir'])
            s = self.ScheduleIt(self.SNQUEUE, self.confinfo, self.working_hash)
            job = SCHED.add_interval_job(func=s.Scanner, minutes=2)
            # start the scheduler now
            SCHED.start()
            #run the scanner immediately on startup.
            s.Scanner()

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

                logger.info('[' + item['mode'] +'] Now loading from queue: ' + item['item'])
            else:
                self.hash_reload = False

            #Sonarr stores torrent names without the extension which throws things off.
            #use the below code to reference Sonarr to poll the history and get the hash from the given torrentid

            if any([item['mode'] == 'file', item['mode'] == 'file-add']):
                logger.info('sending to rtorrent as file...')
                rt = rtorrent.RTorrent(file=item['item'], label=item['label'], partial=self.partial)
            else:
                rt = rtorrent.RTorrent(hash=item['item'], label=item['label'])
            snstat = rt.main()

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
                           'label': item['label']})
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
                        except Exception as e:
                            logger.info('utf-8 error: %s' % e)
                    else:
                        try:
                            tmpfolder = snstat['folder'].encode('utf-8')
                            tmpname = snstat['name'].encode('utf-8')
                            logger.info('[UTF-8 SAFETY] tmpfolder, tmpname: %s' % os.path.join(tmpfolder, tmpname))
                        except:
                            pass

                        logger.info('sntat[files]: %s' % snstat['files'][0])
                        #if it's one file in a sub-directory vs one-file in the root...
                        #if os.path.join(snstat['folder'], snstat['name']) != snstat['files'][0]:
                        if os.path.join(tmpfolder, tmpname) != snstat['files'][0]:
                            downlocation = snstat['files'][0].encode('utf-8')
                        else:
                            #downlocation = os.path.join(snstat['folder'], snstat['files'][0])
                            downlocation = os.path.join(tmpfolder, snstat['files'][0].encode('utf-8'))

                    labelit = None
                    if self.applylabel == 'true':
                        if any([snstat['label'] != 'None', snstat['label'] is not None]):
                            labelit = snstat['label']

                    if snstat['multiple'] is None:
                        multiplebox = '0'
                    else:
                        multiplebox = snstat['multiple']

                    os.environ['conf_location'] = self.conf_location
                    os.environ['harpoon_location'] = re.sub("'", "\\'",downlocation)
                    os.environ['harpoon_label'] = labelit
                    os.environ['harpoon_multiplebox'] = multiplebox
                    logger.info('Downlocation: %s' % re.sub("'", "\\'", downlocation))
                    logger.info('Label: %s' % labelit)
                    logger.info('Multiple Seedbox: %s' % multiplebox)

                    script_cmd = shlex.split(curScriptName)# + [downlocation, labelit, multiplebox]
                    logger.info(u"Executing command " + str(script_cmd))

                    p = subprocess.Popen(script_cmd, env=dict(os.environ))
                    p.communicate()

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

                    if sonarr_process is True:
                        if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                            logger.info('[HARPOON] Removing completed file from queue directory.')
                            try:
                                os.remove(os.path.join(self.torrentfile_dir, self.sonarr_label, item['item'] + '.' + item['mode']))
                                logger.info('[HARPOON] File removed')
                            except:
                                logger.warn('[HARPOON] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading')
                        else:
                            logger.info('[HARPOON] Completed status returned for manual post-processing of file.')

                        logger.info('[SONARR] Successfully post-processed : ' + snstat['name'])
                    else:
                        logger.info('[SONARR] Unable to confirm successful post-processing - this could be due to running out of hdd-space, an error, or something else occuring to halt post-processing of the episode.')

                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    if self.plex_update is True:
                        #sonarr_file = os.path.join(self.torrentfile_dir, self.sonarr_label, str(snstat['hash']) + '.hash')
                        #with open(filepath, 'w') as outfile:
                        #    json_sonarr = json.load(sonarr_file)
                        #root_path = json_sonarr['path']

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

                elif all([snstat['label'] == self.sickrage_label, self.tv_choice == 'sickrage']):
                    #unrar it, delete the .rar's and post-process against the items remaining in the given directory.
                    cr = unrar.UnRAR(os.path.join(self.defaultdir, self.sickrage_label ,snstat['name']))
                    chkrelease = cr.main()
                    if all([len(chkrelease) == 0, len(snstat['files']) > 1, not os.path.isdir(os.path.join(self.defaultdir, self.sickrage_label, snstat['name']))]):
                        #if this hits, then the retrieval from the seedbox failed probably due to another script moving into a finished/completed directory (ie. race-condition)
                        logger.warn('[SONARR] Problem with snatched files - nothing seems to have downloaded. Retrying the snatch again in case the file was moved from a download location to a completed location on the client.')
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

                    if sickrage_process is True:
                        if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                            logger.info('[HARPOON] Removing completed file from queue directory.')
                            try:
                                os.remove(os.path.join(self.torrentfile_dir, self.sickrage_label, item['item'] + '.' + item['mode']))
                                logger.info('[HARPOON] File removed')
                            except:
                                logger.warn('[HARPOON] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading')
                        else:
                            logger.info('[HARPOON] Completed status returned for manual post-processing of file.')

                        logger.info('[SICKRAGE] Successfully post-processed : ' + snstat['name'])
                    else:
                        logger.info('[SICKRAGE] Unable to confirm successful post-processing - this could be due to running out of hdd-space, an error, or something else occuring to halt post-processing of the episode.')

                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    if self.plex_update is True:

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

                    if radarr_process['status'] is True:
                        if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                            logger.info('[HARPOON] Removing completed file from queue directory.')
                            try:
                                os.remove(os.path.join(self.torrentfile_dir, self.radarr_label, item['item'] + '.' + item['mode']))
                                logger.info('[HARPOON] File removed')
                            except:
                                logger.warn('[HARPOON] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading.')
                        else:
                            logger.info('[HARPOON] Completed status returned for manual post-processing of file.')

                        logger.info('[SONARR] Successfully post-processed : ' + snstat['name'])
                    else:
                        logger.info('[SONARR] Unable to confirm successful post-processing - this could be due to running out of hdd-space, an error, or something else occuring to halt post-processing of the movie.')
                        logger.info('[HARPOON] Removing completed file from queue directory.')
                        if not any([item['mode'] == 'hash-add', item['mode'] == 'file-add']):
                            try:
                                os.remove(os.path.join(self.torrentfile_dir, self.radarr_label, item['item'] + '.' + item['mode']))
                                logger.info('[HARPOON] File removed from queue location so as to not re-download/post-process due to previous error (ie. snatch it properly?)')
                            except:
                                logger.warn('[HARPOON] Unable to remove file from snatch queue directory [' + item['item'] + '.' + item['mode'] + ']. You should delete it manually to avoid re-downloading.')

                        CKQUEUE.append({'hash':   snstat['hash'],
                                        'stage':  'completed'})
                        continue

                    if self.radarr_keep_original_foldernames is True:
                        logger.info('[HARPOON] Keep Original FolderNames are enabled for Radarr. Altering paths ...')
                        radarr_info['radarr_id'] = radarr_process['radarr_id']
                        radarr_info['radarr_movie'] = radarr_process['radarr_movie']

                        rof = radarr.Radarr(radarr_info)
                        radarr_keep_og = rof.og_folders()

                    logger.info('[RADARR] Successfully completed post-processing of ' + snstat['name'])
                    CKQUEUE.append({'hash':   snstat['hash'],
                                    'stage':  'completed'})

                    if self.plex_update is True:
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


                elif snstat['label'] == 'music':
                    logger.info('[MUSIC] Successfully auto-snatched!')
#                    beets_shellcmd = '/bin/bash'
#                    beetsScriptName = beets_shellcmd + ' ' + str('/home/hero/harpoon/harpoon/beets_import.sh').decode("string_escape")
#                    beet_info = {}
#                    beet_info['dirpath'] = re.sub("'", "\\'",downlocation)
#                    beets_scriptcmd = shlex.split(beetsScriptName)
#                    logger.info(u"Executing command " + str(beets_scriptcmd))
#                    p, out = subprocess.Popen(beets_scriptcmd, env=beet_info)
#                    p.communicate()
#                    logger.info(p, out)
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

                elif snstat['label'] == 'comics':
                    logger.info('[MYLAR] Successfully auto-snatched!')
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


    def sizeof_fmt(self, num, suffix='B'):
        for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)


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
            extensions = ['.file','.hash','.torrent']
            for (dirpath, dirnames, filenames) in os.walk(self.conf_info['torrentfile_dir']):
                for f in filenames:
                    if any([f.endswith(ext) for ext in extensions]):
                        if f.endswith('.file'):
                            #history only works with sonarr/radarr...
                            #if any([f[-11:] == 'sonarr', f[-11:] == 'radarr']):
                            hash = self.history_poll(f[:-5])
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
                                else:
                                    #label = os.path.basename(dirpath)
                                    label = None

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
                                logger.warn('HASH is already present in queue - but has not been converted to hash for some reason. Ignoring at this time caus I dont know what to do.')
                                logger.warn(CKQUEUE)

                        else:
                            #here we queue it up to send to the client and then monitor.
                            if f.endswith('.torrent'):
                                subdir = os.path.basename(dirpath)
                                #torrents to snatch should be subfolders in order to apply labels if required.
                                fpath = os.path.join(self.conf_info['torrentfile_dir'], subdir, f)
                                logger.info('label to be set to : ' + str(subdir))
                                logger.info('Filepath set to : ' + str(fpath))
                                tinfo = rtorrent.RTorrent(file=fpath, add=True, label=subdir)
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
                            else:
                                label = None
                                if 'mylar' in f[-10:]:
                                    label = self.conf_info['mylar']['mylar_label']
                                    hashfile = f[:-11]
                                elif 'sickrage' in f[-13:]:
                                    label = self.conf_info['sickrage']['sickrage_label']
                                    hashfile = f[:-14]
                                else:
                                    hashfile = f[:-5]
                                dirp = os.path.basename(dirpath)
                                if label is None and os.path.basename(self.conf_info['torrentfile_dir']) != dirp:
                                    label = dirp
                                mode = f[-4:] 

                            #test here to make sure the file isn't being worked on currently & doesnt exist in queue already
                            dupchk = [x for x in CKQUEUE if x['hash'] == hashfile]
                            duplist = []
                            if dupchk:
                                for xc in dupchk:
                                    if xc['stage'] == 'completed':
                                        logger.info('Status is now completed - forcing removal of HASH from queue.')
                                        self.queue.pop(xc['hash'])
                                    else:
                                        logger.info('HASH already exists in queue in a status of ' + xc['stage'] + ' - avoiding duplication: ' + hashfile)
                            else:
                                logger.info('HASH not in queue - adding : ' + hashfile)
                                CKQUEUE.append({'hash':   hashfile,
                                                'stage':  'to-do'})
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
                                except:
                                    logger.warn('Unable to rename file : ' + fpath)

        def history_poll(self, torrentname):
            path = self.conf_info['torrentfile_dir']
            if 'sonarr' in torrentname[-6:]:
                historyurl = self.conf_info['sonarr']['sonarr_url']
                headers = self.conf_info['sonarr']['sonarr_headers']
                label = self.conf_info['sonarr']['sonarr_label']
                mode = 'sonarr'
            elif 'radarr' in torrentname[-6:]:
                historyurl = self.conf_info['radarr']['radarr_url']
                headers = self.conf_info['radarr']['radarr_headers']
                label = self.conf_info['radarr']['radarr_label']
                mode = 'radarr'

            torrentname = torrentname[:-7]
            url = historyurl + '/api/history'
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
            logger.info(torrentname)
            for x in result['records']:
                #logger.info(x)
                if self.filesafe(torrentname.lower()) == self.filesafe(x['sourceTitle'].lower()):
                    hash = x['downloadId']
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

            return hash

        def get_the_hash(self, filepath):
            # Open torrent file
            torrent_file = open(filepath, "rb")
            metainfo = bencode.decode(torrent_file.read())
            info = metainfo['info']
            thehash = hashlib.sha1(bencode.encode(info)).hexdigest().upper()
            logger.info('Hash: ' + thehash)
            return thehash

        def filesafe(self, name):
            import unicodedata
            logger.info('name: %s' % name)

            try:
                name = name.decode('utf-8')
            except:
                pass

            if u'\u2014' in name:
                name = re.sub(u'\u2014', ' - ', name)
            try:
                u_name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').strip()
                logger.info('u_name1: %s' % u_name)
            except TypeError:
                u_name = name.encode('ASCII', 'ignore').strip()
                logger.info('u_name2: %s' % u_name)

            name_filesafe = re.sub('[\:\'\"\,\?\!\\\]', '', u_name)
            name_filesafe = re.sub('[\/\*]', '-', name_filesafe)

            return name_filesafe


class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):

    def handle(self):
        d = self.request.recv(1024)
        dt = d.split("\n")[1]
        data = json.loads(dt)
        logger.info(data)
        logger.info(type(data))
        if data['apikey'] == self.socket_api:
            addq = self.add_queue(data)
            if addq is True:
                self.send({'Status': True, 'Message': 'Successful authentication', 'Added': True})
            else:
                self.send({'Status': True, 'Message': 'Successful authentication', 'Added': False})
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

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass

if __name__ == '__main__':
    gf = QueueR()
#    gf.worker_main()

