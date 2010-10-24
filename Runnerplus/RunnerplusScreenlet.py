#!/usr/bin/env python
"""RunnerplusScreenlet is a Screenlet that allows you to upload your Nike+ from your ipod to the
    the several websites"""

__author__ = "gg"
__email__  = "giorgio@gilestro.tk"
__version__ = '0.6' # released 08/16/2009
__license__= """
Copyright (c) 2004-2009 gg <giorgio@gilestro.tk>

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License as
published by the Free Software Foundation; either version 2 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
USA
"""
"""
INFO:
- uploads data from Nike+ device to the following websites:
- http://www.runnerplus.com
- http://www.runometer.com
- http://nikerunning.nike.com

TODO:

KNOWN BUG:
- due to a screenlet bug in handling the keyring, user must have
  same account details for both sites
WHAT'S NEW
- v0.6
- added support to nike+ website
- reload credentials on Force Sync
- 
"""


import screenlets
import cairo, gobject, webbrowser, os, urllib2
from screenlets.options import StringOption,IntOption,AccountOption,BoolOption

from uploader import runnerPlusUpdater,runometerUpdater,iPodHandler
from nike4all import nikeUploader

try:
    import pygtk, pynotify
    pygtk.require('2.0')
    NOTIFICATION = True
    pynotify.init("Runner+ Widget")
except:
    print("Error importing pynotify")
    NOTIFICATION = False

class myAccountOption(AccountOption):
    
    def on_import (self, strvalue):
        """Import account info from a string (like 'username:auth_token'), 
        retrieve the password from the storage and return a tuple containing
        username and password."""
        # split string into username/auth_token
        (name, auth_token) = strvalue.split(':', 1)
        if name and auth_token:
            # read pass from storage
            try:
                if self.keyring == self.keyring_list[0]:
                    pw = gnomekeyring.item_get_info_sync('session', 
                        int(auth_token)).get_secret()
                else:
                    pw = gnomekeyring.item_get_info_sync(self.keyring, 
                        int(auth_token)).get_secret()
            except Exception, ex:
                print _("ERROR: Unable to read password from keyring: %s") % ex
                pw = ''
            # return
            return (name, pw)
        else:
            raise Exception(_('Illegal value in AccountOption.on_import.'))
    
    def on_export (self, value):
        """Export the given tuple/list containing a username and a password. The
        function stores the password in the gnomekeyring and returns a
        string in form 'username:auth_token'."""
        #The following line solves a bug that does not allow to use more than 1 account with same login
        # store password in storage
        attribs = dict(name=user + '_' + self.name)
        
        if self.keyring == self.keyring_list[0]:
            auth_token = gnomekeyring.item_create_sync('session', 
                gnomekeyring.ITEM_GENERIC_SECRET, value[0], attribs, value[1], True) 
        else:
            auth_token = gnomekeyring.item_create_sync(self.keyring, 
                gnomekeyring.ITEM_GENERIC_SECRET, value[0], attribs, value[1], True)
        # build value from username and auth_token
        return value[0] + ':' + str(auth_token)
        
class RunnerplusScreenlet (screenlets.Screenlet):
    """
    http://www.gilestro.tk/2009/nike-ipod-uploader-for-linux/
    """

    # default meta-info for Screenlets
    __name__ = 'RunnerplusScreenlet'
    __version__ = '0.6'
    __author__ = 'giorgio gilestro'
    __desc__ = __doc__

    updateOnClick = True
    show_unplugged = True
    backup_folder = '~/nike+backup'
    notify = True
    dolog = True
    auto_update = True
    url = ''
    
    ipod = None
    isMounted = False
    
    run_plus=None
    use_runnerplus = False
    runnerplus_account = ('username', 'password')

    runometer=None
    use_runometer = False
    runometer_account = ('username', 'password')
    
    nike=None
    use_nike = False
    nike_pin = ''
    
    def __init__ (self, **keyword_args):
        """
        Set or Check options
        Initialize everything
        """
        screenlets.Screenlet.__init__(self, uses_theme=True, **keyword_args)

        self.theme_name = "default"
        if self.theme:
            sizes = (self.theme.width, self.theme.height)
        else:
            sizes = (100, 150)

        #Adding general options
        self.add_options_group('General', 'Change general options here')
        self.add_option(BoolOption('General', 'show_unplugged', self.show_unplugged, 'Show Widget always', 'Do you want to show the Widget also when the iPod is not connected?'))
        self.add_option(StringOption('General', 'backup_folder', self.backup_folder,'backup folder', 'Where do you want to store backuped data from your ipop?'))
        self.add_option(BoolOption('General', 'notify', self.notify, 'Enable Notifications', 'Do you want to be receive visual notifications? (requires pynotify)'))
        self.add_option(BoolOption('General', 'log', self.dolog, 'Enable Log', 'Activity will be logged in the file nike_plus.log in your home folder'))
        self.add_option(BoolOption('General', 'auto_update', self.auto_update, 'Automatic update', 'Checks for newer version of the widget and dowload them automatically'))
        self.add_option(StringOption('General', 'url', self.url,'Open URL on click', 'Open the specified URL when the icon is clicked; if left empty nothing happens'))

        #Adding options for Runner+ and Runometer
        self.add_options_group('Runometer', 'Change Runometer account details here')
        self.add_option(BoolOption('Runometer', 'use_runometer', self.use_runometer, 'Upload files to Runometer', 'Do you want to upload files to Runometer?'))
        self.add_option(AccountOption('Runometer', 'runometer_account', self.runometer_account,'Username/Password', 'Your Login information')) 

        self.add_options_group('Runner+', 'Change Runner+ account details here')
        self.add_option(BoolOption('Runner+', 'use_runnerplus', self.use_runnerplus, 'Upload files to Runner+', 'Do you want to upload files to Runner+? '))
        self.add_option(AccountOption('Runner+', 'runnerplus_account', self.runnerplus_account,'Username/Password', 'Your Login information')) 

        #Adding options for Nike+
        self.add_options_group('Nike+', 'Change Runner+ account details here')
        self.add_option(BoolOption('Nike+', 'use_nike', self.use_nike, 'Upload files to the Nike website', 'Do you want to upload files to Nike+? '))
        self.add_option(StringOption('Nike+', 'nike_pin', self.nike_pin, 'Nike PIN', 'Enter here the Nike PIN associated to your user account'))

        self.__timeout = gobject.timeout_add(5000, self.update)        # update everything once every 5 seconds

        v = self.updateAvailable(autoUpdate=self.auto_update)
        new = v > self.__version__
        
        if new and self.auto_update: self.notifyUser('New version found (%s).\nDownloaded to your home folder' % v)
        if new and not self.auto_update: self.notifyUser('New version was found (%s) but automatic update was not selected' % v)
        if v == 0:  self.notifyUser('New version found but error downloading to your home folder')  
        if v == -1:  self.notifyUser('Could not connect to the update website.')  

        self.window.resize(sizes[0], sizes[1])
        self.width	= sizes[0]
        self.height	= sizes[1]
        
        self.update_shape()
        self.window.show()

    def on_init (self):
        print "Screenlet has been initialized."
        # add default menuitems
        self.add_default_menuitems()
        self.add_menuitem('force_sync', 'Force Sync')
        self.add_menuitem('force_update', 'Check for Updates')

    def on_menuitem_select (self, id):
        '''
        '''
        if id == 'force_sync':
            self.nike = None
            self.runometer = None
            self.run_plus = None
            self.update()
            self.deviceStatusChanged()
            
        if id == 'force_update':
            v = self.updateAvailable(self.auto_update)
            new = v > self.__version__
            if new and self.auto_update: self.notifyUser('New version found (%s).\nDownloaded to your home folder' % v)
            if new and not self.auto_update: self.notifyUser('New version was found (%s) but automatic update was not selected' % v)
            if v == 0:  self.notifyUser('New version found but error downloading to your home folder')  
            if v == -1:  self.notifyUser('Could not connect to the update website.')
            if not new: self.notifyUser('You are already running the latest version.')



    def on_draw (self, ctx):
        '''
        Called everytime the icon is redrawn
        '''

        ctx.set_operator(cairo.OPERATOR_OVER)
        ctx.scale(self.scale, self.scale)
        #self.update()

        if self.theme:
            if self.isMounted:
                self.theme.render(ctx, 'runnerplus-active')
            else:
                self.theme.render(ctx, 'runnerplus-inactive')
         
            if not self.show_unplugged and not self.isMounted: self.window.hide()
            else: self.window.show()

       

    def on_draw_shape (self,ctx):
        # simply call drawing handler and pass shape-context
        self.on_draw(ctx)
        
    def button_press (self, widget, event):
        '''
        Load specified website on click
        '''
     
        if event.button == 1 and self.url:
            webbrowser.open_new_tab(self.url)
            self.notifyUser("Loading specified website")
        else:
            screenlets.Screenlet.button_press(self, widget, event)


    def set_update_interval (self, interval):
        '''
        Set the update-time in milliseconds.
        '''
        if self.__timeout:
            gobject.source_remove(self.__timeout)
        self.__timeout = gobject.timeout_add(interval, self.update)



    def updateAvailable(self, autoUpdate=False):
        '''
        Check online for newer versions of the widget
        returns:
        0: new version found and downloaded
        -1: new version found but error downloading
        -2: no internet
        ver_num: new version found (no automatic downloaded selected)
        '''
        url = "http://www.gilestro.tk/various/software/runner_widget"
        
        try:
            sock = urllib2.urlopen('%s/version' % url, timeout=5)
            version = sock.read().replace('\n','')
            sock.close()
        except:
            version = -1
    
        if autoUpdate and version > self.__version__:
            try:
                file_name = 'RunnerplusScreenlet-%s.tar.gz' % version
                webFile = urllib.urlopen('%s/file_name' % url)
                localFile = open(os.path.join(os.path.expanduser('~'), file_name), 'wb')
                localFile.write(webFile.read())
                webFile.close()
                localFile.close()
            except:
                version = 0

        return version 

    def deviceStatusChanged(self):
        '''
        called whenever the iPod was plugged or unplugged
        '''
        self.isMounted = not self.isMounted

        if self.isMounted: 
            self.notifyUser("iPod connected")
            
            if self.use_runnerplus:
                sync_successful = self.run_plus.push_data()
                if sync_successful: self.notifyUser("Succesfully syncronized with Runner+ website.")
                else: self.notifyUser("Error sending data to Runner+ website.\nNo connection or bad credentials?")
           
            if self.use_runometer:
                sync_successful = self.runometer.push_data()
                if sync_successful: self.notifyUser("Succesfully syncronized with Runometer website.")
                else: self.notifyUser("Error sending data to Runometer website.\nNo connection or bad credentials?")
                
            if self.use_nike:
                if self.nike.validatePin():
                    sync_successful = self.nike.sync()
                    if sync_successful >= 0:
                        self.nike.closeSync()
                        self.notifyUser('Synced %s files with Nike+ website.' % sync_successful)
                    else:
                        self.notifyUser('Error sending data to Nikerunning.\nIs the ipod mounted?')
                else:
                    self.notifyUser('Error sending data to Nikerunning.\nNo connection or bad PIN?')
                    
                    
        self.redraw_canvas()


    def update(self):
        '''
        called periodically to check for changes
        '''

        if not self.ipod: #called only on first launch
            self.ipod = iPodHandler()

        if self.use_runnerplus and not self.run_plus:
            self.run_plus = runnerPlusUpdater(account=self.runnerplus_account+(self.backup_folder,), debug=self.dolog, testing=False)
        if self.use_runometer and not self.runometer:
            self.runometer = runometerUpdater(account=self.runometer_account+(self.backup_folder,), debug=self.dolog, testing=False)
        if self.use_nike and not self.nike and self.nike_pin:
            backupdir = os.path.join(self.backup_folder, 'nike+')
            self.nike = nikeUploader(self.nike_pin, backupdir)
        
        isMounted = self.ipod.isMounted()
        
        if self.isMounted != isMounted:
            self.deviceStatusChanged()

        return True # keep running this event   
        
    def notifyUser(self, text):
        '''
        Send a notification message
        '''
        #uri = "file://" + os.path.abspath(os.path.curdir) + "/themes/runner/runnerplus_active.svg"
        if self.notify:
            try:
                n = pynotify.Notification("Runner+ Widget", str(text))#, uri)
                n.show()
            except:
                pass



# If the program is run directly or passed as an argument to the python
# interpreter then create a Screenlet instance and show it
if __name__ == "__main__":
    # create new session
    import screenlets.session
    screenlets.session.create_session(RunnerplusScreenlet)

