#! /usr/bin/env python

import os, glob
import subprocess, ConfigParser
import shutil, string

import logging, logging.handlers

import urllib, urllib2

#Multipart is provided
#courtesy of http://stacyprowell.com/blog/2009/05/29/handling-multipartform-data-in-python/
from multipart import Multipart

import ClientCookie

#require ClientCookie 
#http://wwwsearch.sourceforge.net/ClientCookie/
#sudo apt-get install python-clientcookie


def setupLogger(log_dir, appname):
    '''
    '''
    log_filename = os.path.join(log_dir, 'logfile.txt')
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                        datefmt='%m-%d %H:%M',
                        filename=log_filename,
                        filemode='w')

    # define a Handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    # set a format which is simpler for console use
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    # tell the handler to use this format
    console.setFormatter(formatter)
    # add the handler to the root logger
    logging.getLogger('').addHandler(console)
    
    return logging.getLogger('%s' % appname)  

        

class iPodHandler():
    '''
    '''
    
    def __init__(self):
        pass

    def isMounted(self):
        '''
        is an ipod with running data mounted?
        '''
        return ( self.getMountPoint() != '' )
         

    def getMountPoint(self):
        '''
        Search all mounted volumes for device which has NikePlus data
        Will return the path or an empty string
        '''
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

        

class runometerUpdater():

    def __init__(self, account=None, debug=False, testing=False):
        
        self.url = "http://www.runometer.com"
        self.__version__ = 0.1
        self.sync_successful = False
        self.config_filename = os.path.join(os.path.expanduser("~"), ".runometerrc")

        self.doDebug = debug
        self.testing = testing
        self.__logger = None

        self.account = account
        self.ipod = iPodHandler()
        self.isLoggedIn = False
        
        if self.doDebug:
            backupdir = os.path.split(self.getConfigDataFromFile()[2])[0]
            self.logger = setupLogger(backupdir, 'runometer')
        
      
    def getConfigDataFromFile(self):
        '''
        get the configuration data from the rc file
        this is used when the program is run from the commandline
        '''
        if self.account:
            #data coming from the __init__ function
            email, password, backupdir = self.account
            #self.logger.info("Receiving credentials from the outside")
            
        else:
            #if the GUI didn't provide data, we need to fetch them from the config file
            config = ConfigParser.SafeConfigParser({'dirname': '.runometer'})
            config_found = config.read(self.config_filename)

            if not config_found: print "Config File not found. See README file for instructions on creating a config file.\nCould not continue."

            email = config.get('Login','email')
            password = config.get('Login','password')
            backupdir = config.get('Backup', 'dirname')

            #self.logger.info("Receiving credentials from a configuration file")

        if backupdir[0:2] == '~/':
            backupdir = os.path.join(os.path.expanduser("~"), backupdir[2:])
        backupdir = os.path.join(backupdir, 'runometer')

        return email, password, backupdir

    def push_data(self):
        '''
        '''
        self.sync_successful = None

        email, password, backupdir = self.getConfigDataFromFile()

        if not self.isLoggedIn:
            self.isLoggedIn = self.webLogin(email, password)
            if not self.isLoggedIn: 
                self.logger.info("authentication failed")
                return False

        # create the backup directory, if not present
        if not os.path.exists(backupdir):
            self.logger.info("backup dir not found, so creating it: %s" % backupdir)
            os.makedirs(backupdir)
        
        mount_point = self.ipod.getMountPoint()
        if not mount_point: self.logger.info("failed to find iPod-NikePlus file system in any filesystem")
        else: self.logger.info("iPod found at %s" % mount_point)
        
        path = os.path.join(mount_point, "iPod_Control", "Device", "Trainer", "Workouts", "Empeds")
        if os.path.isdir(path):
            stats = os.statvfs(path)
            total_space = (stats[2] * stats[0]) / (1024 * 1024)
            avail_space = (stats[4] * stats[0]) / (1024 * 1024)
            self.logger.info("iPod mounted at %s has a capacity of %d MB and has %d MB available" % \
                (mount_point, total_space, avail_space) )

            filelist = glob.glob(os.path.join(path, '*', '*', '*-*.xml'))
            self.sync_successful = self.uploadRun(email, password, filelist)
        
        return self.sync_successful

    def isNewFile(self, fname):
        '''
        '''
        backupdir = self.getConfigDataFromFile()[2]
        log_file = os.path.join(backupdir, 'uploaded_files.log')
        if not os.path.exists(log_file): self.logFileUploaded('[Runometer - Files Uploaded]')
        
        lf = open(log_file, 'r')
        uploaded_files = lf.read()
        lf.close()
        
        return not (fname in uploaded_files)
        
    def logFileUploaded(self, fname):
        '''
        '''
        backupdir = self.getConfigDataFromFile()[2]
        log_file = os.path.join(backupdir, 'uploaded_files.log')
        lf = open(log_file, 'a')
        lf.write('%s\n' % fname)
        lf.close()
    
    def uploadRun(self, email, password, files):
        '''
        '''
        def file2text(fn):
            fh=open(fn)
            fc = fh.read()
            fh.close()
            return fc
            
        upload_url = self.url + '/add_run.php'
        success = True
        backupdir = self.getConfigDataFromFile()[2]

        if not self.isLoggedIn: self.isLoggedIn = self.webLogin(email, password)
                
        if self.isLoggedIn:
            
            for full_path in files:
                self.logger.info("uploading file %s" % full_path)
                path, fname = os.path.split(full_path)

                if self.isNewFile(fname):

                    m = Multipart()
                    m.field('public_run','checked')
                    m.field('MAX_FILE_SIZE','14000000')
                    m.file('runfile',fname ,file2text(full_path),{'Content-Type':'application/x-www-form-urlencoded'})
                    ct,body = m.get()
                   
                    request = urllib2.Request(upload_url, headers={'Content-Type':ct}, data=body)
                    reply = ClientCookie.urlopen(request)
                    file_uploaded = 'Runometer: Show Run' in reply.read()
                    
                    if file_uploaded:
                        self.logFileUploaded(fname)
                        shutil.copy(full_path, backupdir)

                    success = success * file_uploaded
                    
                else:
                    self.logger.info("File %s already uploaded in some previous session" % fname)

        return success

    def webLogin(self, email, password):
        '''
        '''
        good_login_text = 'Welcome Back to Runometer'
        login_url = self.url + '/login.php'

        post_data = {'username' : email, 'passwd' : password, 'rememberme' : True }
        headers = {'Content-type': 'application/x-www-form-urlencoded'} 
        return_value = None

        if not self.testing:

            request = urllib2.Request(login_url, headers=headers, data=urllib.urlencode(post_data))
            reply = ClientCookie.urlopen(request)
            return_value = good_login_text in reply.read()
           
        return return_value

     

class runnerPlusUpdater():
    '''
    This code is a modification of the uploader originally posted by vkurup
    http://www.runnerplus.com/forum/topicpage-10-448-manual_upload_of_xml_files-0#13375
    
    '''

    def __init__(self, account=None, debug=False, testing=False):

        self.url = "http://www.runnerplus.com/"
        self.__version__ = 0.1
        self.sync_successful = False
        self.config_filename = os.path.join(os.path.expanduser("~"), ".runnerplusrc")

        self.doDebug = debug
        self.__logger = None
        self.testing = testing
        
        self.account = account
        self.ipod = iPodHandler()
        
        if self.doDebug:
            backupdir = os.path.split(self.getConfigDataFromFile()[2])[0]
            self.logger = setupLogger(backupdir, 'runnerplus')


    def isNewFile(self, fname):
        '''
        '''
        backupdir = self.getConfigDataFromFile()[2]
        log_file = os.path.join(backupdir, 'uploaded_files.log')
        if not os.path.exists(log_file): self.logFileUploaded('[Runner+ - Files Uploaded]')
        
        lf = open(log_file, 'r')
        uploaded_files = lf.read()
        lf.close()
        
        return not (fname in uploaded_files)
        
    def logFileUploaded(self, fname):
        '''
        '''
        backupdir = self.getConfigDataFromFile()[2]
        log_file = os.path.join(backupdir, 'uploaded_files.log')
        lf = open(log_file, 'a')
        lf.write('%s\n' % fname)
        lf.close()

    

    def getConfigDataFromFile(self):
        '''
        get the configuration data from the rc file
        this is used when the program is run from the commandline
        '''
        if self.account:
            #data coming from the __init__ function
            email, password, backupdir = self.account
            #self.logger.info("Receiving credentials from the outside")
            
        else:
            #if the GUI didn't provide data, we need to fetch them from the config file
            config = ConfigParser.SafeConfigParser({'dirname': '.runnerplus'})
            config_found = config.read(self.config_filename)

            if not config_found: print "Config File not found. See README file for instructions on creating a config file.\nCould not continue."

            email = config.get('Login','email')
            password = config.get('Login','password')
            backupdir = config.get('Backup', 'dirname')

            #self.logger.info("Receiving credentials from a configuration file")

        if backupdir[0:2] == '~/':
            backupdir = os.path.join(os.path.expanduser("~"), backupdir[2:])

        backupdir = os.path.join(backupdir, 'runnerplus')

        return email, password, backupdir

    def push_data(self):
        xmlfile = None

        email, password, backupdir = self.getConfigDataFromFile()

        uid = self.validate_user(email, password)
        self.logger.info("uid == %s." % uid)
        
        if uid == "0":
                self.logger.info("authentication failed")
                return False
                
        # create the backup directory, if not present
        if not os.path.exists(backupdir):
            self.logger.info("backup dir not found, so creating it: %s" % backupdir)
            os.makedirs(backupdir)
        
        mount_point = self.ipod.getMountPoint()
        if not mount_point: self.logger.info("failed to find iPod-NikePlus file system in any filesystem")
        else: self.logger.info("iPod found at %s" % mount_point)
        
        path = os.path.join(mount_point, "iPod_Control", "Device", "Trainer", "Workouts", "Empeds")
        if os.path.isdir(path):
            stats = os.statvfs(path)
            total_space = (stats[2] * stats[0]) / (1024 * 1024)
            avail_space = (stats[4] * stats[0]) / (1024 * 1024)
            self.logger.info("iPod mounted at %s has a capacity of %d MB and has %d MB available" % \
                (mount_point, total_space, avail_space) )

            filelist = glob.glob(os.path.join(path, '*', '*', '*-*.xml'))
            for xmlfile in filelist:
                self.logger.info("debug found: %s" % xmlfile)
                self.post_to_runnerplus(uid, xmlfile, backupdir)
            self.sync_successful = True
            return self.sync_successful

    def post_to_runnerplus(self, uid, fullpath, backupdir):
        basename = os.path.basename(fullpath)
        
        if not self.isNewFile(basename):
            self.logger.info("File has been previously synced: %s" % basename)
        else:
            self.logger.info("Syncing file: " + basename )
            f = open(fullpath)
            data = f.read()
            f.close()

            v = "Python uploader %s (Linux)" % self.__version__
            post_data = urllib.urlencode({'uid' : uid, 'v' : v, 'data' : data })
            post_url = self.url + "profile/api_postdata.asp"
            if not self.testing: 
                try:
                    contents = urllib.urlopen(post_url, post_data).read()
                    # move to backup folder
                    self.logger.info( "Sync successful. Back up file: %s" % basename)
                    shutil.copy(fullpath, backupdir)
                    self.logFileUploaded(basename)
                except:
                    contents = os.sys.exc_info()[0]
                    self.logger.info(contents)
            else:
                contents = "Testing"
                
            self.logger.info(contents)
        


    def validate_user(self, email, password):
        self.logger.info("validating user %s ..." % email)
        user_url = self.url + "profile/api_validateuser.asp"
        post_data = urllib.urlencode({'n' : email, 'p' : password })
        if not self.testing:
            contents = urllib.urlopen(user_url, post_data)
            uid = contents.read()
        else:
            uid = "999"
        return uid



if __name__ == "__main__":
    
    try:
        use = os.sys.argv[1]
    except:
        use = ''
    
    if use == 'runometer':
        runometer = runometerUpdater(debug=False, testing=False)
        runometer.push_data()

    elif use == 'runnerplus':
        runner = runnerPlusUpdater(debug=False, testing=False)
        runner.push_data()
        
    else:
        print "Usage:\n%s [runometer|runnerplus]\n" % os.sys.argv[0]
    
    
