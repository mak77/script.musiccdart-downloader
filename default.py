#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import sys
import time
import socket
import urllib2

if sys.version_info < (2, 7):
  import simplejson
else:
  import json as simplejson

import xbmc
import xbmcvfs
import xbmcgui
import xbmcaddon

__addon__        = xbmcaddon.Addon()
__addonid__      = __addon__.getAddonInfo('id')
__addonname__    = __addon__.getAddonInfo('name')
__author__       = __addon__.getAddonInfo('author')
__version__      = __addon__.getAddonInfo('version')
__addonpath__    = __addon__.getAddonInfo('path')
__icon__         = __addon__.getAddonInfo('icon')

FTV_API_URL = 'http://webservice.fanart.tv/v3/music/albums/%s?api_key=4b5f48023a25b80f26eff44851afcdeb'
MBZ_ALBUM_API_URL = 'http://musicbrainz.org/ws/2/release/%s?inc=release-groups&fmt=json'

socket.setdefaulttimeout(10)

tempdir = xbmc.translatePath('special://temp/');
silent = __addon__.getSetting('silent')

def main():
  xbmc.log('## Starting Add-on %s (%s)' % (str(__addonname__), str(__version__)), xbmc.LOGNOTICE)

  dialog = None
  if not silent:
    dialog = xbmcgui.DialogProgress();
    dialog.create(__addonname__, 'Music CDArt Downloader', '', '')

  try:
    results = getAlbums()
    albums = []
    count = 0
    for album in results:
      # Allow the main thread to breath for Cancel to work properly.
      xbmc.sleep(5)
      if dialog and dialog.iscanceled():
        break
      if xbmc.abortRequested:
        break
      if not 'musicbrainzalbumid' in album or not album['musicbrainzalbumid']:
        continue
      count += 1
      if dialog:
        dialog.update(0,
                      album['title'].encode("utf-8"),
                      album['displayartist'].encode("utf-8"),
                      str(count));
      # For each album get the first track to find the album path.
      track = getFirstTrackOfAlbum(album['albumid']);
      if 'file' in track:
        albums.append({ 'path'               : os.path.split(track['file'])[0],
                        'musicbrainzalbumid' : album['musicbrainzalbumid'],
                        'musicbrainzartistid': track['musicbrainzartistid'],
                        'title'              : album['title'].encode("utf-8")
                      })

    albums_len = len(albums)
    xbmc.log('Processing %d albums with MusicBrainz ids' % albums_len, xbmc.LOGNOTICE)

    processed = 0
    for album in albums:
      # Allow the main thread to breath for Cancel to work properly.
      xbmc.sleep(5)
      if dialog and dialog.iscanceled():
        break
      if xbmc.abortRequested:
        break
      processed += 1
      if dialog:
        dialog.update(int(float(processed) / float(albums_len) * 100.0),
                      '%d / %d - %s' % (processed, albums_len, album['title']),
                      album['path'],
                      '\n');

      # Check if a CDArt exists already
      cdart_path = os.path.join(album['path'], 'cdart.png')
      if xbmcvfs.exists(cdart_path):
        # xbmc.log('Found cdart in %s ' % cdart_path, xbmc.LOGNOTICE)
        continue

      # Fetch all alternative ids for the album id.
      release_group = getReleaseGroup(album['musicbrainzalbumid'])
      if not release_group:
        continue
      # xbmc.log('Release group %s' % release_group, xbmc.LOGNOTICE)

      cdart_url = getCDArtUrl(release_group)
      if not cdart_url:
        continue

      # xbmc.log('Found cdart %s' % cdart_url, xbmc.LOGNOTICE)
      if dialog:
        dialog.update(int(float(processed) / float(albums_len) * 100.0),
                      '%d / %d - %s' % (processed, albums_len, album['title']),
                      album['path'],
                      '>>> cdart.png');

      downloadArt(cdart_url, cdart_path)

  finally:
    if dialog:
      dialog.close();
    xbmc.log('## Stopping Add-on %s' % str(__addonname__), xbmc.LOGNOTICE)

def getReleaseGroup(id):
  response = remoteJSON(MBZ_ALBUM_API_URL % id)
  if 'release-group' in response:
    return response['release-group']['id']
  return ""

def getCDArtUrl(id):
  result = remoteJSON(FTV_API_URL % id)
  if 'albums' in result and id in result['albums']:
    album = result['albums'][id]
    if 'cdart' in album:
      return album['cdart'][0]['url']
  return ""

def remoteJSON(url):
  response = {}
  try:
    response = urllib2.urlopen(urllib2.Request(url))
    response = simplejson.loads(response.read())
    if response:
      return response
  except urllib2.HTTPError, e:
    # xbmc.log('HTTPError %s' % str(e.code), xbmc.LOGNOTICE)
    return {}
  except Exception, e:
    xbmc.log(str(e), xbmc.LOGNOTICE)
  return {}

def downloadArt(sourceurl, targetpath):
  try:
    sourcepath = os.path.join(tempdir, os.path.basename(targetpath))
    tempfile = open(sourcepath, "wb")
    response = urllib2.urlopen(sourceurl)
    tempfile.write(response.read())
    tempfile.close()
    response.close()
    if not xbmcvfs.copy(sourcepath.encode("utf-8"), targetpath.encode("utf-8")):
      xbmc.log('unable to copy cdart to %s' % targetpath, xbmc.LOGNOTICE)
  except urllib2.HTTPError, e:
    xbmc.log('HTTPError %d' % e.code, xbmc.LOGNOTICE)
  except Exception, e:
    xbmc.log(str(e), xbmc.LOGNOTICE)

def getAlbums():
  result = xbmcJSONRPC('{"jsonrpc": "2.0", "method": "AudioLibrary.GetAlbums", "params": { "properties": ["displayartist", "title", "musicbrainzalbumid"], "sort": { "order": "ascending", "method": "album", "ignorearticle": true } }, "id": "libAlbums"}')
  if 'albums' in result:
    return result['albums']
  return []

def getFirstTrackOfAlbum(albumid):
  result = xbmcJSONRPC('{"jsonrpc": "2.0", "method": "AudioLibrary.GetSongs", "params": { "properties": ["file", "musicbrainzartistid"], "limits": { "start": 0, "end": 1}, "filter": { "albumid": %d } }, "id": "libTrack"}' % albumid)
  if 'songs' in result:
    return result['songs'][0]
  return {}

def xbmcJSONRPC(json):
  request = xbmc.executeJSONRPC(json)
  request = unicode(request, 'utf-8', errors='ignore')
  response = simplejson.loads(request)
  if 'result' in response:
    return response['result']
  return {}

if __name__ == "__main__":
  main()
