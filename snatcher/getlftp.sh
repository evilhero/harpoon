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

if [[ "${applylabel}" == "true" ]]; then
    if [[ "${defaultdir}" == */ ]]; then
        cd ${defaultdir}${label}
    else
        cd ${defaultdir}/${label}
    fi
else
    cd ${defaultdir}
fi


if [[ $fileEXT == "mkv" || $fileEXT == "avi" || $fileEXT == "mp4" || $fileEXT == "mpg" || $fileEXT == "mov" || $fileEXT == "cbr" || $fileEXT == "cbz" ]]; then
    LCMD="pget -n 6 '$filename'"
else
    LCMD="mirror -P 2 --use-pget-n=6 '$filename'"
fi
if [[ $multiple -eq 0 || $multiple -eq 1 ]]; then
    HOST="$harpoon_pp_host"
    PORT="$harpoon_pp_sshport"
    USER="$harpoon_pp_user"
    PASS="$harpoon_pp_passwd"
else
    HOST="$harpoon_pp_host2"
    PORT="$harpoon_pp_sshport2"
    USER="$harpoon_pp_user2"
    PASS="$harpoon_pp_passwd2"
fi

lftp<<END_SCRIPT
open sftp://${HOST}:${PORT}
user ${USER} ${PASS}
$LCMD
bye
END_SCRIPT
