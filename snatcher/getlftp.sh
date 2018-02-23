#!/bin/bash
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

filename="$harpoon_location"
label="$harpoon_label"
multiple="$harpoon_multiplebox"
applylabel="$harpoon_applylabel"
defaultdir="$harpoon_defaultdir"
fileEXT=`echo "${filename##*.}" | tr '[A-Z]' '[a-z]'`
HOST="$harpoon_pp_host"
PORT="$harpoon_pp_sshport"
USER="$harpoon_pp_user"
PASS="$harpoon_pp_passwd"
KEYFILE="$harpoon_pp_keyfile"


if [[ "${applylabel}" == "true" ]]; then
    if [[ "${defaultdir}" == */ ]]; then
        cd ${defaultdir}${label}
    else
        cd ${defaultdir}/${label}
    fi
else
    cd ${defaultdir}
fi


if [[ $fileEXT == "mkv" || $fileEXT == "avi" || $fileEXT == "mp4" || $fileEXT == "mpg" || $fileEXT == "mov" || $fileEXT == "cbr" || $fileEXT == "cbz" || $fileEXT == "epub" || $fileEXT == "mobi" || $fileEXT == "azw3" || $fileEXT == "pdf" || $fileEXT == "mp3" || $fileEXT == "flac" ]]; then
    LCMD="pget -n 6 '$filename'"
else
    LCMD="mirror -P 2 --use-pget-n=6 '$filename'"
fi

if [[ -z $KEYFILE ]]; then
    PARAM="$USER $PASS"
else
    PARAM="$USER $KEYFILE"
fi

lftp<<END_SCRIPT
open sftp://${HOST}:${PORT}
user ${PARAM}
$LCMD
bye
END_SCRIPT
