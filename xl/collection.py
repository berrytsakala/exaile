# Copyright (C) 2008-2010 Adam Olsen
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
#
# The developers of the Exaile media player hereby grant permission
# for non-GPL compatible GStreamer and Exaile plugins to be used and
# distributed together with GStreamer and Exaile. This permission is
# above and beyond the permissions granted by the GPL license by which
# Exaile is covered. If you modify this code, you may extend this
# exception to your version of the code, but you are not obligated to
# do so. If you do not wish to do so, delete this exception statement
# from your version.

"""
Classes representing collections and libraries

A collection is a database of tracks. It is based on :class:`TrackDB` but has
the ability to be linked with libraries.

A library finds tracks in a specified directory and adds them to an associated
collection.
"""

from __future__ import with_statement
from collections import deque
import glib
import gobject
import gio
import logging
import os
import os.path
import shutil
import threading
import time

from xl.nls import gettext as _
from xl import (
    common,
    event,
    metadata,
    settings,
    trax,
    xdg
)

logger = logging.getLogger(__name__)

COLLECTIONS = set()

def get_collection_by_loc(loc):
    """
        gets the collection by a location.

        :param loc: Location of the collection
        :return: collection at location or None
        :rtype: Collection
    """
    for c in COLLECTIONS:
        if c.loc_is_member(loc):
            return c
    return None

class CollectionScanThread(common.ProgressThread):
    """
        Scans the collection
    """
    def __init__(self, collection):
        """
            Initializes the thread

            :param collection: the collection to scan
        """
        common.ProgressThread.__init__(self)

        self.collection = collection

    def stop(self):
        """
            Stops the thread
        """
        self.collection.stop_scan()
        common.ProgressThread.stop(self)

    def on_scan_progress_update(self, type, collection, progress):
        """
            Notifies about progress changes
        """
        if progress < 100:
            self.emit('progress-update', progress)
        else:
            self.emit('done')

    def run(self):
        """
            Runs the thread
        """
        event.add_callback(self.on_scan_progress_update,
            'scan_progress_update')

        self.collection.rescan_libraries()

        # idle_add is a hack to ensure it only gets removed AFTER all
        # events have been sent. remove when we get a better solution.
        glib.idle_add(event.remove_callback, self.on_scan_progress_update,
            'scan_progress_update')

class Collection(trax.TrackDB):
    """
        Manages a persistent track database.

        :param args: see :class:`xl.trax.trackdb.TrackDB`

        Simple usage:

        >>> from xl.collection import *
        >>> from xl.trax import search
        >>> collection = Collection("Test Collection")
        >>> collection.add_library(Library("./tests/data"))
        >>> collection.rescan_libraries()
        >>> tracks = [i.track for i in search.search_tracks_from_string(
        ...     collection, ('artist==TestArtist'))]
        >>> print len(tracks)
        5
        >>>
    """
    def __init__(self, name, location=None, pickle_attrs=[]):
        global COLLECTIONS
        self.libraries = {}
        self._scanning = False
        self._scan_stopped = False
        self._running_count = 0
        self._running_total_count = 0
        self._frozen = False
        self._libraries_dirty = False
        pickle_attrs += ['_serial_libraries']
        trax.TrackDB.__init__(self, name, location=location,
                pickle_attrs=pickle_attrs)
        COLLECTIONS.add(self)

    def freeze_libraries(self):
        """
            Prevents "libraries_modified" events from being sent from individual
            add and remove library calls.

            Call this before making bulk changes to the libraries. Call
            thaw_libraries when you are done; this sends a single event if the
            libraries were modified.
        """
        self._frozen = True

    def thaw_libraries(self):
        """
            Re-allow "libraries_modified" events from being sent from individual
            add and remove library calls. Also sends a "libraries_modified"
            event if the libraries have ben modified since the last call to
            freeze_libraries.
        """
        # TODO: This method should probably be synchronized.
        self._frozen = False
        if self._libraries_dirty:
            self._libraries_dirty = False
            event.log_event('libraries_modified', self, None)

    def add_library(self, library):
        """
            Add this library to the collection

            :param library: the library to add
            :type library: :class:`Library`
        """
        loc = library.get_location()
        if loc not in self.libraries:
            self.libraries[loc] = library
            library.set_collection(self)
        self.serialize_libraries()
        self._dirty = True

        if self._frozen:
            self._libraries_dirty = True
        else:
            event.log_event('libraries_modified', self, None)

    def remove_library(self, library):
        """
            Remove a library from the collection

            :param library: the library to remove
            :type library: :class:`Library`
        """
        for k, v in self.libraries.iteritems():
            if v == library:
                del self.libraries[k]
                break

        to_rem = []
        if not "://" in library.location:
            location = u"file://" + library.location
        else:
            location = library.location
        for tr in self.tracks:
            if tr.startswith(location):
                to_rem.append(self.tracks[tr]._track)
        self.remove_tracks(to_rem)

        self.serialize_libraries()
        self._dirty = True

        if self._frozen:
            self._libraries_dirty = True
        else:
            event.log_event('libraries_modified', self, None)

    def stop_scan(self):
        """
            Stops the library scan
        """
        self._scan_stopped = True

    def get_libraries(self):
        """
            Gets a list of all the Libraries associated with this
            Collection

            :rtype: list of :class:`Library`
        """
        return self.libraries.values()

    def rescan_libraries(self):
        """
            Rescans all libraries associated with this Collection
        """
        if self._scanning:
            raise Exception("Collection is already being scanned")
        if len(self.libraries) == 0:
            event.log_event('scan_progress_update', self, 100)
            return # no libraries, no need to scan :)

        self._scanning = True
        self._scan_stopped = False

        self.file_count = -1 # negative means we dont know it yet

        self.__count_files()

        scan_interval = 20

        for library in self.libraries.itervalues():
            event.add_callback(self._progress_update, 'tracks_scanned',
                library)
            library.rescan(notify_interval=scan_interval)
            event.remove_callback(self._progress_update, 'tracks_scanned',
                library)
            self._running_total_count += self._running_count
            if self._scan_stopped:
                break
        else: # didnt break
            try:
                self.save_to_location()
            except AttributeError:
                common.log_exception(log=logger)

        event.log_event('scan_progress_update', self, 100)

        self._running_total_count = 0
        self._running_count = 0
        self._scanning = False
        self.file_count = -1

    @common.threaded
    def __count_files(self):
        file_count = 0
        for library in self.libraries.values():
            if self._scan_stopped:
                self._scanning = False
                return
            file_count += library._count_files()
        self.file_count = file_count
        logger.debug("File count: %s"%self.file_count)

    def _progress_update(self, type, library, count):
        """
            Called when a progress update should be emitted while scanning
            tracks
        """
        self._running_count = count
        count = count + self._running_total_count

        if self.file_count < 0:
            event.log_event('scan_progress_update', self, 0)
            return

        try:
            event.log_event('scan_progress_update', self,
                int((float(count) / float(self.file_count)) * 100))
        except ZeroDivisionError:
            pass

    def serialize_libraries(self):
        """
            Save information about libraries

            Called whenever the library's settings are changed
        """
        _serial_libraries = []
        for k, v in self.libraries.iteritems():
            l = {}
            l['location'] = v.location
            l['monitored'] = v.monitored
            l['_realtime'] = v.monitored
            l['scan_interval'] = v.scan_interval
            _serial_libraries.append(l)
        return _serial_libraries

    def unserialize_libraries(self, _serial_libraries):
        """
            restores libraries from their serialized state.

            Should only be called once, from the constructor.
        """
        for l in _serial_libraries:
            self.add_library( Library( l['location'],
                    l.get('monitored', l.get('_realtime')),
                    l['scan_interval'] ))

    _serial_libraries = property(serialize_libraries, unserialize_libraries)

    def close(self):
        """
            close the collection. does any work like saving to disk,
            closing network connections, etc.
        """
        #TODO: make close() part of trackdb
        COLLECTIONS.remove(self)

    def delete_tracks(self, tracks):
        for tr in tracks:
            for prefix, lib in self.libraries.iteritems():
                lib.delete(tr.get_loc_for_io())

class LibraryMonitor(gobject.GObject):
    """
        Monitors library locations for changes
    """
    __gproperties__ = {
        'monitored': (
            gobject.TYPE_BOOLEAN,
            'monitoring state',
            'Whether to monitor this library',
            False,
            gobject.PARAM_READWRITE
        )
    }
    __gsignals__ = {
        'location-added': (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            [gio.File]
        ),
        'location-removed': (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            [gio.File]
        )
    }
    
    def __init__(self, library):
        """
            :param root: the library to monitor
            :type root: :class:`Library`
        """
        gobject.GObject.__init__(self)

        self.__library = library
        self.__root = gio.File(library.location)
        self.__monitored = False
        self.__monitors = {}
        self.__lock = threading.RLock()

    def do_get_property(self, property):
        """
            Gets GObject properties
        """
        if property.name == 'monitored':
            return self.__monitored
        else:
            raise AttributeError('unkown property %s' % property.name)

    def do_set_property(self, property, value):
        """
            Sets GObject properties
        """
        if property.name == 'monitored':
            if value != self.__monitored:
                self.__monitored = value
                update_thread = threading.Thread(target=self.__update_monitors)
                update_thread.daemon = True
                update_thread.start()
        else:
            raise AttributeError('unkown property %s' % property.name)

    def __update_monitors(self):
        """
            Sets up or removes library monitors
        """
        with self.__lock:
            if self.props.monitored:
                logger.debug('Setting up library monitors')

                for directory in common.walk_directories(self.__root):
                    monitor = directory.monitor_directory()
                    monitor.connect('changed', self.on_location_changed)
                    self.__monitors[directory] = monitor

                    self.emit('location-added', directory)
            else:
                logger.debug('Removing library monitors')

                for directory, monitor in self.__monitors.iteritems():
                    monitor.cancel()

                    self.emit('location-removed', directory)

                self.__monitors = {}

    def on_location_changed(self, monitor, gfile, other_gfile, event):
        """
            Updates the library on changes of the location
        """
        if event == gio.FILE_MONITOR_EVENT_CREATED:
            added_tracks = trax.util.get_tracks_from_uri(gfile.get_uri())
            self.__library.collection.add_tracks(added_tracks)

            # Set up new monitor if directory
            fileinfo = gfile.query_info('standard::type')

            if fileinfo.get_file_type() == gio.FILE_TYPE_DIRECTORY and \
               gfile not in self.__monitors:
                monitor = gfile.monitor_directory()
                monitor.connect('changed', self.on_location_changed)
                self.__monitors[gfile] = monitor

                self.emit('location-added', gfile)
        elif event == gio.FILE_MONITOR_EVENT_DELETED:
            removed_tracks = []

            track = trax.Track(gfile.get_uri())

            if track in self.__library.collection:
                # Deleted file was a regular track
                removed_tracks += [track]
            else:
                # Deleted file was most likely a directory
                for track in self.collection:
                    track_gfile = gio.File(track.get_loc_for_io())

                    if track_gfile.has_prefix(gfile):
                        removed_tracks += [track]

            self.__library.collection.remove_tracks(removed_tracks)

            # Remove obsolete monitors
            removed_directories = [d for d in self.__monitors \
                if d == gfile or d.has_prefix(gfile)]

            for directory in removed_directories:
                self.__monitors[directory].cancel()
                del self.__monitors[directory]
                
                self.emit('location-removed', directory)

class Library(object):
    """
        Scans and watches a folder for tracks, and adds them to
        a Collection.

        Simple usage:

        >>> from xl.collection import *
        >>> c = Collection("TestCollection")
        >>> l = Library("./tests/data")
        >>> c.add_library(l)
        >>> l.rescan()
        True
        >>> print c.get_libraries()[0].location
        ./tests/data
        >>> print len(list(c.search('artist="TestArtist"')))
        5
        >>>
    """
    def __init__(self, location, monitored=False, scan_interval=0):
        """
            Sets up the Library

            :param location: the directory this library will scan
            :type location: string
            :param collection: the collection to associate with
            :type collection: :class:`Collection`
            :param monitored: whether the library should update its
                collection at changes within the library's path
            :type monitored: bool
            :param scan_interval: the interval for automatic rescanning
            :type scan_interval: int
        """
        self.location = location
        self.scan_interval = scan_interval
        self.scan_id = 0
        self.scanning = False
        self.monitor = LibraryMonitor(self)
        self.monitor.props.monitored = monitored

        self.collection = None
        self.set_rescan_interval(scan_interval)

    def set_location(self, location):
        """
            Changes the location of this Library

            :param location: the new location to use
            :type location: string
        """
        self.location = location

    def get_location(self):
        """
            Gets the current location associated with this Library

            :return: the current location
            :rtype: string
        """
        return self.location

    def set_collection(self, collection):

        self.collection = collection

    def get_monitored(self):
        """
            Whether the library should be monitored for changes
        """
        return self.monitor.props.monitored

    def set_monitored(self, monitored):
        """
            Enables or disables monitoring of the library
            
            :param monitored: Whether to monitor the library
            :type monitored: bool
        """
        self.monitor.props.monitored = monitored

    monitored = property(get_monitored, set_monitored)

    def get_rescan_interval(self):
        """
            :return: the scan interval in seconds
        """
        return self.scan_interval

    def set_rescan_interval(self, interval):
        """
            Sets the scan interval in seconds.  If the interval is 0 seconds,
            the scan interval is stopped

            :param interval: scan interval in seconds
            :type interval: int
        """
        if not interval:
            if self.scan_id:
                glib.source_remove(self.scan_id)
                self.scan_id = 0
        else:
            if self.scan_id:
                glib.source_remove(self.scan_id)

            self.scan_id = glib.timeout_add_seconds(interval, self.rescan)

        self.scan_interval = interval

    def _count_files(self):
        """
            Counts the number of files present in this directory
        """
        count = 0
        for file in common.walk(gio.File(self.location)):
            if self.collection:
                if self.collection._scan_stopped:
                    break
            count += 1

        return count

    def _check_compilation(self, ccheck, compilations, tr):
        """
            This is the hacky way to test to see if a particular track is a
            part of a compilation.

            Basically, if there is more than one track in a directory that has
            the same album but different artist, we assume that it's part of a
            compilation.

            :param ccheck: dictionary for internal use
            :param compilations: if a compilation is found, it'll be appended
                to this list
            :param tr: the track to check
        """
        # check for compilations
        if not settings.get_option('collection/file_based_compilations', True):
            return

        def joiner(value):
            if not value or type(value) in (str, unicode):
                return value
            else:
                try:
                    return u"\u0000".join(value)
                except TypeError:
                    return value

        try:
            basedir = joiner(tr.get_tag_raw('__basedir'))
            album = joiner(tr.get_tag_raw('album'))
            artist = joiner(tr.get_tag_raw('artist'))
        except UnicodeDecodeError: #TODO: figure out why this happens
            logger.warning("Encoding error, skipping compilation check")
            return
        if not basedir or not album or not artist: return
        album = album.lower()
        artist = artist.lower()
        try:
            if not basedir in ccheck:
                ccheck[basedir] = {}

            if not album in ccheck[basedir]:
                ccheck[basedir][album] = deque()
        except TypeError:
            common.log_exception(log=logger)
            return

        if ccheck[basedir][album] and not \
            artist in ccheck[basedir][album]:
            if not (basedir, album) in compilations:
                compilations.append((basedir, album))
                logger.info("Compilation %(album)s detected in %(dir)s" %
                        {'album':album, 'dir':basedir})

        ccheck[basedir][album].append(artist)

    def update_track(self, gloc):
        """
            Rescan the track at a given location

            :gloc: A gio.File representing the location

            returns: the Track object, None if it could not be updated
        """
        uri = gloc.get_uri()
        if not uri: # we get segfaults if this check is removed
            return None
        mtime = gloc.query_info("time::modified").get_modification_time()
        tr = self.collection.get_track_by_loc(uri)
        if tr:
            if tr.get_tag_raw('__modified') < mtime:
                tr.read_tags()
                tr.set_tag_raw('__modified', mtime)
        else:
            tr = trax.Track(uri)
            if tr._scan_valid == True:
                tr.set_tag_raw('__date_added', time.time())
                self.collection.add(tr)
                tr.set_tag_raw('__modified', mtime)

            # Track already existed. This fixes trax.get_tracks_from_uri
            # on windows, unknown why fix isnt needed on linux.
            elif not tr._init:
                self.collection.add(tr)
        return tr

    def rescan(self, notify_interval=None):
        """
            Rescan the associated folder and add the contained files
            to the Collection
        """
        # TODO: use gio's cancellable support

        if self.collection is None:
            return True

        if self.scanning:
            return

        logger.info("Scanning library: %s" % self.location)
        self.scanning = True
        db = self.collection
        libloc = gio.File(self.location)

        count = 0
        dirtracks = deque()
        compilations = deque()
        ccheck = {}
        for fil in common.walk(libloc):
            count += 1
            type = fil.query_info("standard::type").get_file_type()
            if type == gio.FILE_TYPE_DIRECTORY:
                if dirtracks:
                    for tr in dirtracks:
                        self._check_compilation(ccheck, compilations, tr)
                    for (basedir, album) in compilations:
                        base = basedir.replace('"', '\\"')
                        alb = album.replace('"', '\\"')
                        items = [ tr for tr in dirtracks if \
                                tr.get_tag_raw('__basedir') == base and \
                                # FIXME: this is ugly
                                alb in "".join(
                                    tr.get_tag_raw('album') or []).lower()
                                ]
                        for item in items:
                            item.set_tag_raw('__compilation', (basedir, album))
                dirtracks = deque()
                compilations = deque()
                ccheck = {}
            elif type == gio.FILE_TYPE_REGULAR:
                tr = self.update_track(fil)
                if not tr:
                    continue

                if dirtracks is not None:
                    dirtracks.append(tr)
                    # do this so that if we have, say, a 4000-song folder
                    # we dont get bogged down trying to keep track of them
                    # for compilation detection. Most albums have far fewer
                    # than 110 tracks anyway, so it is unlikely that this
                    # restriction will affect the heuristic's accuracy.
                    # 110 was chosen to accomodate "top 100"-style
                    # compilations.
                    if len(dirtracks) > 110:
                        logger.info("Too many files, skipping "
                                "compilation detection heuristic.")
                        dirtracks = None

            if self.collection and self.collection._scan_stopped:
                self.scanning = False
                return

            # progress update
            if notify_interval is not None and count % notify_interval == 0:
                event.log_event_sync('tracks_scanned', self, count)

        # final progress update
        if notify_interval is not None:
            event.log_event_sync('tracks_scanned', self, count)



        removals = deque()
        for tr in self.collection.tracks.itervalues():
            tr = tr._track
            loc = tr.get_loc_for_io()
            if not loc:
                continue
            gloc = gio.File(loc)
            try:
                if not gloc.has_prefix(libloc):
                    continue
            except UnicodeDecodeError:
                common.log_exception(log=logger)
                continue

            if not gloc.query_exists():
                removals.append(tr)

        for tr in removals:
            logger.debug(u"Removing %s"%unicode(tr))
            self.collection.remove(tr)
        self.scanning = False

    def add(self, loc, move=False):
        """
            Copies (or moves) a file into the library and adds it to the
            collection
        """
        oldgloc = gio.File(loc)

        newgloc = gio.File(self.location).resolve_relative_path(
                oldgloc.get_basename())

        if move:
            oldgloc.move(newgloc)
        else:
            oldgloc.copy(newgloc)
        tr = trax.Track(newgloc.get_uri())
        if tr._scan_valid:
            self.collection.add(tr)

    def delete(self, loc):
        """
            Deletes a file from the disk

            .. warning::
               This permanently deletes the file from the hard disk.
        """
        tr = self.collection.get_track_by_loc(loc)
        if tr:
            self.collection.remove(tr)
            loc = tr.get_loc_for_io()
            file = gio.File(loc)
            if not file.delete():
                logger.warning("Could not delete file %s." % loc)

    # the below are not essential for 0.3.0, should be implemented only
    # if time allows for it

    def set_layout(self, layout, default="Unknown"):
        pass

    def organize(self):
        pass

    def keep_organized(self, bool):
        pass

    def get_freespace(self):
        pass

    def get_totalspace(self):
        pass

    def get_usedspace(self):
        pass

    def get_usedspace_percent(self):
        pass


class TransferQueue(object):

    def __init__(self, library):
        self.library = library
        self.queue = []
        self.current_pos = -1
        self.transferring = False
        self._stop = False

    def enqueue(self, tracks):
        self.queue.extend(tracks)

    def dequeue(self, tracks):
        if self.transferring:
            # FIXME: use a proper exception, and make this only error on
            # tracks that have already been transferred
            raise Exception, "Cannot remove tracks while transferring"

        for t in tracks:
            try:
                self.queue.remove(t)
            except ValueError:
                pass

    def transfer(self):
        """
            Tranfer the queued tracks to the library.

            This is NOT asynchronous
        """
        self.transferring = True
        self.current_pos += 1
        try:
            while self.current_pos  < len(self.queue) and not self._stop:
                track = self.queue[self.current_pos]
                loc = track.get_loc_for_io()
                self.library.add(loc)

                # TODO: make this be based on filesize not count
                progress = self.current_pos * 100 / len(self.queue)
                event.log_event('track_transfer_progress', self, progress)

                self.current_pos += 1
        finally:
            self.queue = []
            self.transferring = False
            self.current_pos = -1
            self._stop = False
            event.log_event('track_transfer_progress', self, 100)

    def cancel(self):
        """
            Cancel the current transfer
        """
        # TODO: make this stop mid-file as well?
        self._stop = True


# vim: et sts=4 sw=4

