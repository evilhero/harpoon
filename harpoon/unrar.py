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

import os
import re
import optparse
import subprocess
from subprocess import CalledProcessError, check_output
from harpoon import logger

class UnRAR(object):

    def __init__(self, path=None):

        if path is None:
            parser = optparse.OptionParser()
            parser.add_option('-p', '--path', dest='path', help='Full path to scan for rar\'s.')
            (options, args) = parser.parse_args()

            if options.path:
                self.path = options.path
            else:
                self.path = False
        else:
            self.path = path

        #logging.basicConfig(level=logging.DEBUG)
        #logger = logging.getLogger()

        # Setup file logger
        #filename = os.path.join('/home/hero/harpoon/unrar.log')
        #file_formatter = logging.Formatter('%(asctime)s - %(levelname)-7s :: %(threadName)s : %(message)s', '%d-%b-%Y %H:%M:%S')
        #file_handler = handlers.RotatingFileHandler(filename, maxBytes=1000000, backupCount=5)
        #file_handler.setLevel(logging.DEBUG)

        #file_handler.setFormatter(file_formatter)
        #logger.addHandler(file_handler)

    def main(self):
        status = 'None'
        dirlist = self.traverse_directories(self.path)
        rar_found = []

        for fname in dirlist:
            filename = fname['filename']

            rar_ex = r'\.(?:rar|r\d\d|\d\d\d)$'
            rar_chk = re.findall(rar_ex, filename, flags=re.IGNORECASE)
            if rar_chk:
                #append the rars found to the rar_found tuple
                rar_found.append({"directory": self.path,
                                  "filename":  filename})


        #if it needs to get unrar'd - we should do it here.
        if len(rar_found) > 0:
            rar_info = self.rar_check(rar_found)
            if rar_info is None:
                logger.warn('[RAR-DETECTION-FAILURE] Incomplete rar set detected - ignoring.')
            else:
                logger.info('[RAR-DETECTION] Detected rar\'s within ' + rar_info[0]['directory'] + '. Initiating rar extraction.')
                if len(rar_info) > 0:
                    for rk in rar_info:
                        if rk['start_rar'] is None:
                            continue
                        logger.info('[RAR MANAGER] [ ' + str(len(rk['info'])) + ' ] ') # : ' + str(rar_info))
                        logger.info('[RAR MANAGER] First Rar detection initated for : ' + str(rk['start_rar']))
                        # extract the rar's biatch.
                        try:
                            rar_status = self.unrar_it(rk)
                        except Exception as e:
                            logger.warn('[RAR MANAGER] Error extracting rar: %s' % e)
                            continue
                        else:
                            if rar_status == "success":
                                logger.info('[RAR MANAGER] Successfully extracted rar\'s.')
                                for rs in rk['info']:
                                    os.remove(os.path.join(self.path, rs['filename']))
                                    logger.info('[RAR MANAGER] Removal of : ' + os.path.join(self.path, rs['filename']))
                                #remove the crap in the directory that got logged earlier ( think its done later though )
                                logger.info('[RAR MANAGER] Removal of start rar: ' + rk['start_rar'])
                                os.remove(rk['start_rar'])
                                status = 'success'

        if status == 'success':
            logger.info('Success!')
            dirlist = self.traverse_directories(self.path)
        else:
            if len(rar_found) > 0:
                logger.warn('Unable to unrar items')
            else:
                logger.debug('No items to unrar.')
        return dirlist

    def rar_check(self, rarlist):
        #used to determine the first rar of the set so that unraring won't fail
        #it will return a tuple indicating the 'start_rar' and the 'info' for the remainder of the rars
        rar_keep = {}
        rar_temp = []
        rar_keepsake = []
        startrar = None
        rar_ex1 = r'(\.001|\.part0*1\.rar|^((?!part\d*\.rar$).)*\.rar)$'
        #this might have to get sorted so that rar comes before r01, r02, etc
        for f in rarlist:
            first_rarchk = re.findall(rar_ex1, f['filename'], flags=re.IGNORECASE)
            if first_rarchk:
                startrar = f['filename']
                unrardir = f['directory']
                logger.info('[RAR DETECTION] First RAR detected as :' + f['filename'])
            else:
                rar_temp.append(f)
        if startrar is not None:
            rar_keep['start_rar'] = startrar
            rar_keep['directory'] = unrardir
            rar_keep['info'] = rar_temp
            rar_keepsake.append(rar_keep)
            #logger.info(rar_keepsake)
            return rar_keepsake
        else:
            return None


    def unrar_it(self, rar_set):
        logger.info('[RAR MANAGER] Extracting ' + str(len(rar_set['info'])) + ' rar\'s for set : ' + os.path.join(rar_set['directory']))
        #arbitrarily pick the first entry and change directories.
        unrar_folder = rar_set['directory']
        #os.makedirs( unrar_folder )
        os.chdir( unrar_folder )
        logger.info('[RAR MANAGER] Changing to : ' + str(unrar_folder))
        unrar_cmd = '/usr/bin/unrar'
        baserar = rar_set['start_rar']
        # Extract.
        try:
            output = subprocess.check_output( [ unrar_cmd, 'x', baserar ] )
        except CalledProcessError as e:
            if e.returncode == 3:
                logger.warn('[RAR MANAGER] [Unrar Error 3] - Broken Archive.')
            elif e.returncode == 1:
                logger.warn('[RAR MANAGER] [Unrar Error 1] - No files to extract.')
            return "unrar error"
        except Exception as e:
            logger.warn('[RAR MANAGER] Error: %s' % e)
            return "unrar error"

        return "success"

    def traverse_directories(self, dir, filesfirst=False):
        filelist = []
        for (dirname, subs, files) in os.walk(dir, followlinks=True):

            for fname in files:

                filelist.append({"directory":  dirname,
                                 "filename":   fname})


        if len(filelist) > 0:
            logger.info('there are ' + str(len(filelist)) + ' files.')

        if filesfirst:
            return sorted(filelist, key=lambda x: (x['filename'], x['directory']), reverse=False)
        else:
            return sorted(filelist, key=lambda x: (x['directory'], os.path.splitext(x['filename'])[1]), reverse=True)


if __name__ == '__main__':
    test = UnRAR()
    test.main()

