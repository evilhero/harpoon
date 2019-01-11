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
from urlparse import urlparse

from lib.rtorrent import RTorrent

class TorrentClient(object):
    def __init__(self):
        self.conn = None

    def getVerifySsl(self, rtorr_verify):
        #rtorr_verify = 0
        # Ensure verification has been enabled
        if not rtorr_verify:
            return False

        # Use default ssl verification
        return True

    def connect(self, host, username, password, auth, rpc_url, rtorr_ssl, rtorr_verify):
        if self.conn is not None:
            return self.conn

        if not host:
            return False

        url = self.cleanHost(host, protocol = True, ssl = rtorr_ssl)

        # Automatically add '+https' to 'httprpc' protocol if SSL is enabled
        if rtorr_ssl and url.startswith('httprpc://'):
            url = url.replace('httprpc://', 'httprpc+https://')

        parsed = urlparse(url)

        # rpc_url is only used on http/https scgi pass-through
        if parsed.scheme in ['http', 'https']:
            url += rpc_url

        if username and password:
            try:
                self.conn = RTorrent(
                    url,(auth, username, password),
                    verify_server=True,
                    verify_ssl=self.getVerifySsl(rtorr_verify)
            )
            except:
                return False
        else:
            try:
                self.conn = RTorrent(host)
            except:
                return False

        return self.conn

    def find_torrent(self, hash=None, filepath=None):
        return self.conn.find_torrent(info_hash=hash, filepath=filepath)

    def get_files(self, hash):
        a = self.conn.get_files(hash)
        return a

    def get_torrent (self, torrent):
        if not torrent:
            return False
        torrent_files = []
        torrent_directory = os.path.normpath(torrent.directory)
        try:
            for f in torrent.get_files():
                if not os.path.normpath(f.path).startswith(torrent_directory):
                    file_path = os.path.join(torrent_directory, f.path.lstrip('/'))
                else:
                    file_path = f.path

                torrent_files.append(file_path)
            torrent_info = {
                'hash': torrent.info_hash,
                'name': torrent.name,
                'label': torrent.get_custom1() if torrent.get_custom1() else '',
                'folder': torrent_directory,
                'completed': torrent.complete,
                'files': torrent_files,
                'upload_total': torrent.get_up_total(),
                'download_total': torrent.get_down_total(),
                'ratio': torrent.get_ratio(),
                'total_filesize': torrent.get_size_bytes(),
                'time_started': torrent.get_time_started()
                }

        except Exception:
            raise

        return torrent_info if torrent_info else False

    def load_torrent(self, filepath, rtorr_label, start, applylabel=None, rtorr_dir=None):
        print('filepath to torrent file set to : ' + filepath)

        torrent = self.conn.load_torrent(filepath, verify_load=True)
        if not torrent:
            return False

        if rtorr_label:
            torrent.set_custom(1, rtorr_label)
            print('Setting label for torrent to : ' + rtorr_label)

        if all([applylabel is True, rtorr_label is not None]):
            new_location = os.path.join(rtorr_dir, rtorr_label)
            torrent.set_directory(new_location)
            print('Setting directory for torrent to : %s' % new_location)

        print('Successfully loaded torrent.')

        #note that if set_directory is enabled, the torrent has to be started AFTER it's loaded or else it will give chunk errors and not seed
        if start:
            print('[' + str(start) + '] Now starting torrent.')
            torrent.start()
        else:
            print('[' + str(start) + '] Not starting torrent due to configuration setting.')
        return True

    def start_torrent(self, torrent):
        return torrent.start()

    def stop_torrent(self, torrent):
        return torrent.stop()

    def delete_torrent(self, torrent):
        deleted = []
        try:
            for file_item in torrent.get_files():
                file_path = os.path.join(torrent.directory, file_item.path)
                os.unlink(file_path)
                deleted.append(file_item.path)

            if torrent.is_multi_file() and torrent.directory.endswith(torrent.name):
                try:
                    for path, _, _ in os.walk(torrent.directory, topdown=False):
                        os.rmdir(path)
                        deleted.append(path)
                except:
                    pass
        except Exception:
            raise

        torrent.erase()

        return deleted

    def cleanHost(self, host, protocol = True, ssl = False, username = None, password = None):
        """  Return a cleaned up host with given url options set
            taken verbatim from CouchPotato
    Changes protocol to https if ssl is set to True and http if ssl is set to false.
    >>> cleanHost("localhost:80", ssl=True)
    'https://localhost:80/'
    >>> cleanHost("localhost:80", ssl=False)
    'http://localhost:80/'

    Username and password is managed with the username and password variables
    >>> cleanHost("localhost:80", username="user", password="passwd")
    'http://user:passwd@localhost:80/'

    Output without scheme (protocol) can be forced with protocol=False
    >>> cleanHost("localhost:80", protocol=False)
    'localhost:80'
        """

        if not '://' in host and protocol:
            host = ('https://' if ssl else 'http://') + host

        if not protocol:
            host = host.split('://', 1)[-1]

        if protocol and username and password:
            try:
                auth = re.findall('^(?:.+?//)(.+?):(.+?)@(?:.+)$', host)
                if auth:
                    log.error('Cleanhost error: auth already defined in url: %s, please remove BasicAuth from url.', host)
                else:
                    host = host.replace('://', '://%s:%s@' % (username, password), 1)
            except:
                pass
        host = host.rstrip('/ ')
        if protocol:
            host += '/'

        return host
