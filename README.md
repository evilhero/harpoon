**---Harpoon.....-->**
version - 0.75

**Description**
---------
This is a python-cli based application that can either be run from the cli directly, or as a daemon to automatically send and/or monitor torrents to a remote torrent client and monitor for completion and retrieve the completed files back to the local machine where automatic post-processing against specific clients can be initiated.

**Requirements**
----------
- LINUX only
- Python 2.7.9+ (for SNI support)
- lftp
- rutorrent client (running remotely - ie.seedbox)
- sonarr        (optional)
- radarr        (optional)
- lidarr        (optional)
- mylar         (optional)
- lazylibrarian (optional)
- sickrage      (optional)
- plex          (optional)


**Options via command line**
-----------------------
``-h, --help``                      Show this help message and exit

``-a filename, --add=filename``     Specify a filename to snatch from specified torrent client when daemon monitor is running already.

``-s HASH, --hash=HASH``            Specify a HASH to snatch from specified torrent client.

``-l LABEL, --label=LABEL``         For use ONLY with -t, specify a label that the HASH has that harpoon can check against when querying the torrent client.

``-t, --exists``                    In combination with -s (Specify a HASH) & -l (Specify a label) with this enabled it will not download the torrent (it must exist in the designated location already) but perform post-processing
  
``-f FILE, --file=FILE``            Specify an exact filename to snatch from specified torrent client. (Will do recursive if more than one file)

``-b, --partial``                   Grab the torrent regardless of completion status (for cherrypicked torrents since they'll never be 100% complete)

``-m, --monitor``                   Monitor a designated file location for new files to harpoon.

``-d, --daemon``                    Daemonize the complete program so it runs in the background.

``-p PIDFILE, --pidfile=PIDFILE``   Specify a pidfile location to store pidfile for daemon usage.


**Configuration options (harpoon.conf)**
-----------------------------
(leave configuration options blank if not being used and it's a full path/local path value requirement.

**[general]**

``APPLYLABEL`` [*true/false*] = whether or not to apply a label when adding local .torrent files to the torrent client.

``DEFAULTDIR`` [*full path*] = final local destination path where finished downloads are to be stored

``TORRENTFILE_DIR`` [*full path*] = location where .torrent files are dropped to prior to sending to client (required for daemon usage)

``LOGPATH`` [*full path*] = local path destination for log files for harpoon

``MULTIPLE_SEEDBOXES`` [*true/false*] = if multiple seedboxes are being used, enable this option to be able to monitor more than one seedbox

``MULTIPLE1`` [*labels*] = set this to all of the labels that are present on the 1st seedbox that are to be monitored

``MULTIPLE2`` [*labels*] = if multiple_seedboxes is true, set this to the additional labels on the second seedbox that are to be monitored (labels should not overlap)

``TORRENTCLIENT`` [*clientname*] = set this to rtorrent. Later versions will incorporate additional clients such as deluge

**[rtorrent]**

``RTORR_HOST`` [*host*] = the ip / hostname of the rtorrent client

``RTORR_PORT`` [*port*] = the port that the rtorrent client resides on (80 = http, 443 = https)

``RTORR_USER`` [*user*] = the username on the rtorrent client

``RTORR_PASSWD`` [*pass*] = the password for the given username

``RPC_URL`` [*remote url*] = the remote url (ie. username/RPC1, username/httprpc/action.php, etc)

``AUTHENTICATION`` [*basic/digest*] = set the authentication based on the torrent client being used

``SSL`` [*true/false*] = if ssl is enabled on the rtorrent client 

``VERIFY_SSL`` [*true/false*] = whether or not to verify the ssl connection 

``STARTONLOAD`` [*true/false*] = start the torrent automatically when loading a .torrent file

**[post-processing]**

``PP_HOST`` [*host*] = the ip/hostname of the seedbox

``PP_SSHPORT`` [*port*] = the ssh port of the seedbox

``PP_USER`` [*user*] = the username that has access to the torrent files on the seedbox

``PP_PASSWD`` [*pass*] = the ssh password for the given username

``PP_BASEDIR`` [*remote path*] = the full remote path where the base directory of the torrent files are located

**[labels]**

``TVDIR`` [*local path*] = the full local path where tv labelled torrents are to be downloaded to

``MUSICDIR`` [*local path*] = the full local path where music labelled torrents are to be downloaded to

``MOVIEDIR`` [*local path*] = the full local path where movie labelled torrents are to be downloaded to

``XXXDIR`` [*local path*] = the full local path where xxx labelled torrents are to be downloaded to

``COMICSDIR`` [*local path*] = the full local path where comic labelled torrents are to be downloaded to

**[sonarr]**

``URL`` [*local url*] = full url [host:port/path] to where sonarr resides (usually you have to include the /sonarr at the end)

``APIKEY`` [*apikey*] = the apikey for sonarr

``SONARR_LABEL`` [*label*] = the label that sonarr gives to torrents on the client (normally just 'tv')

**[sickrage]**

``URL`` [*local url*] = full url [host:port/path] to where sickrage resides

``APIKEY`` [*apikey*] - the apikey for sickrage

``DELETE`` [*true/false*] = deletes the files and folders after completion of the manual Post-Processing.

``FORCE_REPLACE`` [*true/false*] = Forces already Post Processed Dir/Files, use only in case you have problems.

``FORCE_NEXT`` [*true/false*] = Waits for the current processing queue item to finish and returns result of this request

``PROCESS_METHOD`` [*copy/move/symlink/hardlink*] = what action to use when post-processing given file(s).

``IS_PRIORITY`` [*true/false*] = Replaces an existing file if it already exists in higher quality.

``FAILED`` [*true/false*] = Lets you mark the downloaded episode as failed, and lets SickRage search/snatch an alternative file.

``TYPE`` [*auto/manual*] = the type of post-processing being run.

``SICKRAGE_LABEL`` [*label*] = the label that sickrage gives to torrents on the client

**[radarr]**

``URL`` [*local url*] = full url [host:port/path] where radarr resides

``APIKEY`` [*apikey*] = the apikey for radarr

``RADARR_LABEL`` [*label*] = the label that radarr assigns to torrents on the given client (normally 'movies')

``KEEP_ORIGINAL_FOLDERNAMES`` [*true/false*] = whether or not to keep the original folder names (this is built-in to radarr now, but the option is here regardless)

``RADARR_ROOTDIR`` [*root folder*] = the default root folder path that you want things to default to if original filenames is enabled.

``RADARR_DIR_HD_MOVIES`` [*path*] = if original_filenames is enabled, you can distinguish a seperate hd movies here (will move to this directory after post-processing, and then refresh radarr so that it will see new path as a final static path)...

``RADARR_DIR_WEB_MOVIES`` [*path*] = if original_filenames is enabled, you can distinguish a seperate Web-dl movies here (will move to this directory after post-processing, and then refresh radarr so that it will see new path as a final static path)...

``RADARR_DIR_SD_MOVIES`` [*path*] = if original_filenames is enabled, you can distinguish a seperate directory for SD movies here (will move to this directory after post-processing, and then refresh radarr so that it will see new path as a final static path)...

**[lidarr]**

``URL`` [*local url*] = full url [host:port/path] where lidarr resides

``APIKEY`` [*apikey*] = the apikey for lidarr

``LIDARR_LABEL`` [*label*] = the label that lidarr assigns to torrents on the given client (normally 'music')

**[mylar]**

``URL`` [*local url*] = full url [host:port/path] where mylar resides

``APIKEY`` [*apikey*] = the apikey for mylar

``MYLAR_LABEL`` [*label*] = the label that mylar assigns to torrents on the given client (normally 'comics')

**[lazylibrarian]**

``URL`` [*local url*] = full url [host:port/path] where lazylibrarian resides

``APIKEY`` [*apikey*] = the apikey for lazylibrarian

``LAZYLIBRARIAN_LABEL`` [*label*] = the label that lazylibrarian assigns to torrents on the given client (normally 'books' or 'lazylibrarian')

**[plex]**

``PLEX_UPDATE`` [*true/false*] = enable the option to perform a plex rescan of the given library that's just been downloaded/post-processed

``PLEX_HOST_IP`` [*url*] = full url to plex (ie. http://127.0.0.1)

``PLEX_HOST_PORT`` [*port*] = port to plex 

``PLEX_LOGIN`` [*user*] = username for plex account signon (email)

``PLEX_PASSWORD`` [*pass*] = password for plex account signon

``PLEX_TOKEN`` [*blank*] = leave this blank, atm it's to store the plex token - in a later version, eventually once the token is established the login/password can be removed....

**[multiple seedboxes and the conf file]**

If there is a 2nd seedbox to monitor (multiple_seedboxes = True), copy the entire rtorrent section again and label the second section ``[rtorrent2]`` with the changed information therein.

Same applies to post-processing, copy so that an additional section called ``[post-processing2]`` is setup, and modify 2 fields so that they are ``PP_HOST2`` and ``PP_SSHPORT2`` therein instead of the default ones.


**Usage (Daemon mode)**
----------
Harpoon can monitor a given directory (ie. watch directory) for actual .torrent files. Once the torrent files are recognized they are sent to the remote torrent client for monitoring and automatic retrieval back to the local client upon completion.

For organizational/operational usage it is best to create a folder for .torrent files to be monitored and then subfolders for each label that is required. Post-processing can then be accomplished using these labels as the requirement to call the given post-processing application via direct api calls (ie. tv = sonarr, movies = radarr, comics = mylar, etc).

**For Sonarr/Radarr/Lidarr**
----------

**NOTE FOR SONARR > V2.0.0.5301** Remote Mapping MUST be enabled - your remote mapping folder is the location where sonarr puts your tv-related torrents on your seedobox, local is where harpoon drops them prior to post-processing

In any of the above applications, go to Settings / Connections and create a custom script. Give the name something obvious 'HARPOON', and set the On Grab option to Yes, and the On Download option to No.  Set the Path option to the location of your python executable (ie. /usr/bin/python), and then in the arguments set it to the complete path to the harpoonshot.py file which is currently located in the root of the harpoon folder with the application name at the end of the argument line (ie. /opt/harpoon/harpoonshot.py radarr OR /opt/harpoon/harpoonshot.py sonarr).

Save the script and make sure it's enabled. That's it - now whenever sonarr/radarr/lidarr snatch a torrent it will still send it directly to the given client, but it will also run the harpoonshot.py script right after which contains information that allows harpoon to monitor the file by hash on the torrent client. It will create a file in the given watch directory folder, under the specific label, as the hash of the file with the extension of either .radarr.hash, .sonarr.hash, or lidarr.hash once it's been successfully added to the watch queue (once post-processing has been successfully completed, these files in the watch directory are automatically removed).

**For Mylar**
---------
In Configuration: 

- Quality & Post-Processing tab, Post-Processing section, *Run script AFTER an item has been snatched and sent to client* is enabled. Enter full path location to harpoonshot.py in the On Snatch Script Location field.

- Web Interface tab, API, *Enable API* (if not already enabled). *Generate* Mylar API Key if one doesn't exist already.

- Save configuration and restart Mylar so ApiKey will be valid.

- Set values in harpoon.conf for Mylar usage as indicated above.


**For LazyLibrarian**
----------

Go to Config, Notifications, *Enable Custom Notifications*.  Select *Notify on Snatch*, and enter the full path to harpoonshot.py.  Save the configuration.  You may test the script, if you like.   Whenever lazylibrarian snatches a torrent, it will run harpoonshot.py, and allow harpoon to monitor the file on the torrent client.

....more to be added
