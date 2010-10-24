#!/usr/bin/env python
"""nike4all is a tool that allows you to upload your Nike+ from your ipod to the
    the Nike running website without using iTunes."""

__author__ = "gg"
__email__  = "giorgio@gilestro.tk"
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

import os, glob, shutil
import urllib, urllib2
import logging, logging.handlers
import subprocess, ConfigParser

import plistlib
import xml.etree.ElementTree as et


VERSION = '0.3.1' #09/09/09
URL = 'http://nike4all.gilestro.tk'

class iPodHandler():
    """
    This is the class handling the iPod
    It simply check whether the iPod is mounted and, if yes,
    where the mount point is
    """
    def __init__(self):
        pass

    def isMounted(self):
        """
        is an ipod with running data mounted?
        """
        return ( self.getMountPoint() != '' )
         

    def getMountPoint(self):
        """
        Search all mounted volumes for device which has NikePlus data
        Will return the path or an empty string
        """
        output = subprocess.Popen(['/bin/df','-P','-x','tmpfs'],stdout=subprocess.PIPE).communicate()[0]
        devices = output.split('\n')[1:]
        for line in devices:
            if line:
                # account for mountpoints with spaces in them
                mount = ' '.join(line.split()[5:])
                nike = os.path.join(mount, "iPod_Control", "Device", "Trainer", "Workouts", "Empeds")
                if os.path.exists(nike):
                    return mount

        return '' #will return False if the path is not found

        



class AutomaticHTTPRedirectHandler(urllib2.HTTPRedirectHandler):

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Return a Request or None in response to a redirect.
        
        The default response in redirect_request claims not to 
        follow directives in RFC 2616 but in fact it does
        This class does not and makes handling 302 with POST
        possible
        """
        m = req.get_method()
        if (code in (301, 302, 303, 307) and m in ("GET", "HEAD")
            or code in (301, 302, 303) and m == "POST"):
            newurl = newurl.replace(' ', '%20')
            return urllib2.Request(newurl,
                           data=req.get_data(),
                           headers=req.headers,
                           origin_req_host=req.get_origin_req_host(),
                           unverifiable=True)
        else:
            raise urllib2.HTTPError(req.get_full_url(), code, msg, headers, fp)

class userData():
    """
    Just a class for packing the data of the Nike+ user
    """
    def __init__(self, validation_text):
        """
        """
        root = et.fromstring(validation_text)
        self.pinStatus = root.findall('pinStatus')[0].text
        self.isAssociated = self.pinStatus == 'confirmed'

        if self.pinStatus == 'replace':
            self.newpin = root.findall('pin')[0].text
        else:
            self.newpin = None
        
        if self.isAssociated:
            self.email = root.findall('email')[0].text
            self.screenName = root.findall('screenName')[0].text
            self.gender = root.findall('gender')[0].text
            self.dateOfBirth = root.findall('dateOfBirth')[0].text
            self.dateFormat = root.findall('dateFormat')[0].text
            
        else:
            self.email = None
            self.screenName = None
            self.dateOfBirth = None
            self.dateFormat = None
      


class nikeUploader():
    """
    The class that handles the comunication with the Nike+ website
    """
    __version__ = VERSION
    pin = None
    backupdir = None
    
    def __init__(self, pin=None, backupdir=None):
                
        pinConf, bdirConf = self.loadConfigFile()
        self.pin = pin or pinConf
        self.backupdir = backupdir or bdirConf
        
        if self.backupdir[0:2] == '~/': self.backupdir = os.path.join(os.path.expanduser("~"), self.backupdir[2:])
        
        self.url = 'http://phobos.apple.com'
        self.agent = 'iTunes/8.2.1 (Windows; N)'

        try:
            self.bag = self.getNikeBag()
        except:
            raise Exception ('Could not get the nikeBag. Are you connected to the internet?')
            
        self.ipod = iPodHandler()

    def __file2text__(self, fn):
        """
        open a file and return its content in plain text
        """
        fh=open(fn)
        fc = fh.read()
        fh.close()
        return fc

    def saveConfigFile(self, pin=None, bdir=None):
        """
        """
        if not pin: pin = self.pin
        if not bdir: bdir = self.backupdir
        try:
            fname = os.path.join(os.path.expanduser("~"), ".nike+rc")
            cf = open(fname, 'w')

            config = ConfigParser.ConfigParser()

            bdir = bdir or '~/.nike+' 

            config.add_section('Nike+')
            config.set('Nike+', 'pin', pin)
            config.set('Nike+', 'backupdir', bdir)

            config.write(cf)
            cf.close()
            return True
        except:
            return False
        
        

    def loadConfigFile(self):
        """
        get the configuration data from the rc file
        this is used when the program is run from the commandline
        """
        fname = os.path.join(os.path.expanduser("~"), ".nike+rc")
        config = ConfigParser.SafeConfigParser({'pin': '', 'backupdir': '~/.nike+'})
        config_found = config.read(fname)

        if not config_found:
            self.saveConfigFile()
            return self.loadConfigFile()

        pin = config.get('Nike+','pin')
        backupdir = config.get('Nike+','backupdir')
        
        if backupdir[0:2] == '~/':
            backupdir = os.path.join(os.path.expanduser("~"), backupdir[2:])


        return pin, backupdir

    def isNewFile(self, fname):
        '''
        '''
        log_file = os.path.join(self.backupdir, 'uploaded_files.log')
        if not os.path.exists(log_file): self.logFileUploaded('[Nike+ - Files Uploaded]')
        
        lf = open(log_file, 'r')
        uploaded_files = lf.read()
        lf.close()
        
        print fname
        print uploaded_files
        return not (fname in uploaded_files)
        
    def logFileUploaded(self, fname):
        '''
        '''
    
        log_file = os.path.join(self.backupdir, 'uploaded_files.log')
        lf = open(log_file, 'a')
        lf.write('%s\n' % fname)
        lf.close()
        
    def sync(self):
        """
        sync iPod contents online
        return
        0 files found but not synced
        -1 no files found
        n files found 
        """
        success = 0
        
        # create the backup directory, if not present
        if not os.path.exists(self.backupdir):
            #self.logger.info("backup dir not found, so creating it: %s" % self.backupdir)
            os.makedirs(self.backupdir)
        
        mount_point = self.ipod.getMountPoint()
        #if not mount_point: return False

        path = os.path.join(mount_point, "iPod_Control", "Device", "Trainer", "Workouts", "Empeds")
        if os.path.isdir(path):
            filelist = glob.glob(os.path.join(path, '*', '*', '*-*.xml'))
            for file in filelist:
                fname = os.path.split(file)[1]
                if self.isNewFile(fname):
                    self.postFile(file)
                    p = self.postFile(file)
                    success = success + int(p)
                    if p: shutil.copy(file, self.backupdir)

        else:
            return -1
        
        return success

    
    def getNikeBag(self):
        """
        The nikeBag is a xml file containing the address to all the Nike+ services
        """
        bag_url = self.url + '/nikeBag.xml.gz'
        headers = {'host': 'phobos.apple.com', 'connection': 'close', 'user-agent': self.agent}
        
        request = urllib2.Request(bag_url)
        opener = urllib2.build_opener(AutomaticHTTPRedirectHandler)
        response = opener.open(request)
        bag = response.read()
        return plistlib.readPlistFromString(bag)        

    def createAccount(self):
        """
        Sync a new account with the ipod
        """
        #this is a temporary PIN
        self.pin = self.generatePin()
        validate = self.validatePin()
        
        if not validate.isAssociated:
            token = self.generateToken()
            account_url = self.bag['accessAccountV2'] + token + '&v=2'
            return self.pin, account_url

        else:
            return self.createAccount()


    def getFinalPin(self):
        """
        called after the creation of a temporary Pin and the activation
        online
        """
        validate = self.validatePin()
        
        if validate.pinStatus == 'replace':
            self.pin = validate.newpin
            user = self.validatePin()
            return user
        else:
            return None

    def openAccountWebPage(self, url):
        """
        """

        headers = {'connection': 'close', 'content-length': '0', 'user-agent': self.agent, 'cache-control' : 'no-cache'}

        request = urllib2.Request(url, headers=headers)
        opener = urllib2.build_opener(AutomaticHTTPRedirectHandler)
        response = opener.open(request)
        page = response.headers
        print page

    def generatePin(self):
        """
        example of pin_response
        <?xml version="1.0" encoding="UTF-8"?><plusService><status>success</status><pin>xxxxxxxx-xxxx-xxxx-xxxx-xxxxx16D2309</pin></plusService>
        """
        generatePin_url = self.bag['generatePINV2']
        
        params = urllib.urlencode({'pin' : self.pin})
        headers = {'connection': 'close', 'content-length': '0', 'user-agent': self.agent, 'cache-control' : 'no-cache'}

        request = urllib2.Request(generatePin_url, headers=headers)
        opener = urllib2.build_opener(AutomaticHTTPRedirectHandler)
        response = opener.open(request)
        pin_response = response.read()

        #pin_response = '<?xml version="1.0" encoding="UTF-8"?><plusService><status>success</status><pin>721856F0-CBD8-0D2C-1BCF-B56E916D2309</pin></plusService>'

        root = et.fromstring(pin_response)
        if root.findall('status')[0].text == 'success':
            return root.findall('pin')[0].text
        else:
            return None
       
       
    def generateToken(self):
        """
        example of a token_reponse
        #<?xml version="1.0" encoding="UTF-8"?><plusService><status>success</status><token>xxxxxxxx-xxxx-xxxx-xxxx-E7A74548090B</token></plusService>
        """
        generate_token_url = self.bag['generateTokenV2']
        params = urllib.urlencode({'pin' : self.pin})
        l = str(len(params))
        headers = {'content-length': l, 'user-agent': self.agent, 'connection': 'close', 'cache-control' : 'no-cache', 'content-type': 'application/x-www-form-urlencoded'}

        request = urllib2.Request(generate_token_url, params, headers)
        opener = urllib2.build_opener(AutomaticHTTPRedirectHandler)
        response = opener.open(request)
        token_response = response.read()
        
        root = et.fromstring(token_response)
        if root.findall('status')[0].text == 'success':
            return root.findall('token')[0].text
        else:
            return None


    def validatePin(self):
        """
        example of pin responses:
        #
        #<?xml version="1.0" encoding="UTF-8"?><plusService><status>success</status><pinStatus>unconfirmed</pinStatus></plusService>
        #<?xml version="1.0" encoding="UTF-8"?><plusService><status>success</status><pinStatus>confirmed</pinStatus><email><![CDATA[email@domain.tld]]></email><screenName><![CDATA[username]]></screenName><gender><![CDATA[M]]></gender><dateOfBirth><![CDATA[01/01/1970]]></dateOfBirth><dateFormat><![CDATA[MM/DD/YY]]></dateFormat></plusService>

        """
        validatePin_url = self.bag['getPINStatusV2']
        params = urllib.urlencode({'pin' : self.pin})
        l = str(len(params))
        headers = {'content-length': l, 'user-agent': self.agent, 'connection': 'close', 'cache-control' : 'no-cache', 'content-type': 'application/x-www-form-urlencoded'}

        request = urllib2.Request(validatePin_url, params, headers)
        opener = urllib2.build_opener(AutomaticHTTPRedirectHandler)
        response = opener.open(request)
        nikeUser = userData(response.read())

        return nikeUser

        
    def postFile(self, path_to_file):
        """
        upload the specified file online
        """
        
        post_url = self.bag['dataSyncV2']
        params = self.__file2text__(path_to_file)
        l = str(len(params))
        headers = {'content-length': l, 'pin' : self.pin, 'connection': 'close', 'user-agent': self.agent, 'cache-control' : 'no-cache', 'content-type': 'text/xml'}

        request = urllib2.Request(post_url, params, headers)
        opener = urllib2.build_opener(AutomaticHTTPRedirectHandler)
        response = opener.open(request)
        
        root = et.fromstring(response.read())
        if root.findall('status')[0].text == 'success':
            fname = os.path.split(path_to_file)[1]
            self.logFileUploaded(fname)
            return True
        else:
            return False

       
    def closeSync(self):
        """
        terminates the connection
        """
        end_url = self.bag['dataSyncCompleteV2']
        params = urllib.urlencode({'pin' : self.pin})
        l = str(len(params))
        headers = {'content-length': l, 'connection': 'close',  'user-agent': self.agent, 'cache-control' : 'no-cache', 'content-type': 'application/x-www-form-urlencoded'}

        request = urllib2.Request(end_url, params, headers)
        opener = urllib2.build_opener(AutomaticHTTPRedirectHandler)
        response = opener.open(request)
        
        root = et.fromstring(response.read())
        if root.findall('status')[0].text == 'success':
            return True
        else:
            return False

    def updateAvailable(self):
        """
        Check online for newer versions of the program
        """
        url = "http://www.gilestro.tk/various/software/nike4all"
        
        sock = urllib2.urlopen('%s/version' % url, timeout=5)
        version = sock.read().replace('\n','')
        sock.close()
    
        return version > self.__version__
       
        
        
if __name__ == "__main__":
    
        
    args = os.sys.argv
    prog_name = os.path.split(args[0])[1]
    
 
    if '-checkUpdate' in args:
        nike = nikeUploader()
        if nike.updateAvailable():
            print 'A new version of the program is available'
            print 'Get at %s' % URL
        else:
            print 'You are already running the last available version'
    
    elif '-getNikeBag' in args:
        nike = nikeUploader()
        print nike.getNikeBag()
        os.sys.exit(1)
        
    elif '-sync' in args:
        nike = nikeUploader()
        nike.validatePin()
        n = nike.sync()
        if n < 0:
            print 'No Files found. Is the ipod mounted?'
        else:
            print 'Synced %s files' % n

            if n > 0 and nike.closeSync():
                print 'Connection closed.'

        os.sys.exit(1)        
            
    
    elif '-validatePin' in args:
        ix = args.index('-validatePin')
        
        try:
            pin = args[ix+1]
        except:
            pin = None
            
        nike = nikeUploader(pin)
        user = nike.validatePin()
        if user:
            print 'Pin Status: %s' % user.pinStatus
            print 'Associated to user: %s' % user.screenName
        else:
            print 'Error'

        os.sys.exit(1)

    elif '-uploadFile' in args:
        ix = args.index('-uploadFile')
        file = args[ix+1]
        
        try:
            pin = args[ix+2]
        except:
            pin = None
            
        nike = nikeUploader(pin)
        user = nike.validatePin()
        print 'uploading file %s for user %s' % (file, user.screenName)
        if nike.postFile(file):
            print 'Upload Succesful!'
        else:
            print 'Error Uploading the file.'
        if nike.closeSync():
            print 'Connection Closed'
        else:
            print 'Error closing connection'
        os.sys.exit(1)
        
    elif '-createAccount' in args:
        nike = nikeUploader()
        pin, url = nike.createAccount()
        print 'Go to this URL and login whit username and password of the account you just created'
        print 'Url to visit: %s' % url
        raw_input ('Press enter to continue only AFTER you login')
        nike.pin = pin
        user = nike.getFinalPin()
        
        if user:
            print 'Congratulation, your status is now confirmed!'
            print 'The user %s is now associated to the pin %s' % (user.screenName, nike.pin)
            
            if nike.saveConfigFile():
                print 'Your pin was successfully saved in the configuration file'
                print 'To update new files connect the iPod and use the following command:'
                print '%s -sync\n' % prog_name
            else:
                print 'Error! Could not save your pin in the configuration file!'
                print 'To update new files connect the iPod and use the following command:'
                print '%s -sync %s\n' % (prog_name, pin)
            os.sys.exit(1)
        else:
            print 'Problem getting new pin. Did you login after creating the account?'
            print 'Your temporary pin was %s' % pin 
            os.sys.exit(1)        
        
        
    elif '-getFinalPin' in args:
        ix = args.index('-getFinalPin')
        pin = args[ix+1]
        nike = nikeUploader(pin)
        user = nike.getFinalPin()
        if user:
            print 'Congratulation, your status is now confirmed'
            print 'The user %s is now associated to the pin %s' % (user.screenName, nike.pin)
            
            if nike.saveConfigFile():
                print 'Your pin was succesfully saved in the configuration file'
                print 'To update new files connect the iPod and use the following command:'
                print '%s -sync\n' % prog_name
            else:
                print 'Error! Could not save your pin in the configuration file!'
                print 'To update new files connect the iPod and use the following command:'
                print '%s -sync %s\n' % (prog_name, pin)
            os.sys.exit(1)
        else:
            print 'Problem getting new pin. Did you login after creating the account?' 
            print 'Your temporary pin was %s' % pin 
            os.sys.exit(1)   
    
    elif '-test' in args:
        nike = nikeUploader()
        nike.loadConfigFile()
        print nike.validatePin().screenName
        print nike.backupdir
        
    else:
        print '%s by giorgio@gilestro.tk' % prog_name
        print 'Version %s' % VERSION
        print 'Usage: %s options\n' % prog_name
        print 'Options:'
        print '-createAccount\t\t\tSync your ipod with an already existing Nike+ account.'
        print '-sync\t\t\t\tSync the data file for user PIN. If PIN is not provided will use configuration file'
        print '-uploadFile path_to_file [PIN]\tUpload the data file for user PIN'
        print '-validatePin [PIN]\t\tReturn the user PIN data'
        print '-checkUpdate\t\t\tCheck for an update of the program online.'
        print '-h --help\t\t\tPrint this help message.'
        os.sys.exit(1)        
        
    
    
