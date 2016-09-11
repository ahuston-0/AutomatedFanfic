from fanficfare import geturls
from os import listdir, remove, rename, utime, errno, devnull
from os.path import isfile, join
from subprocess import check_output, STDOUT, call,PIPE
import logging
from optparse import OptionParser
import re
from ConfigParser import ConfigParser
from tempfile import mkdtemp
from shutil import rmtree

logging.getLogger("fanficfare").setLevel(logging.ERROR)

def touch(fname, times=None):
    with open(fname, 'a'):
        utime(fname, times)


ffnet = re.compile('(fanfiction.net/s/\d*)/?.*')
neutral = re.compile('https?://(.*)')
story_name = re.compile('(.*)-.*')

equal_chapters = re.compile('.* already contains \d* chapters.')
chapter_difference = re.compile('.* contains \d* chapters, more than source: \d*.')
bad_chapters = re.compile(".* doesn't contain any recognizable chapters, probably from a different source.  Not updating.")
no_url = re.compile('No story URL found in epub to update.')
more_chapters = re.compile(".*File\(.*\.epub\) Updated\(.*\) more recently than Story\(.*\) - Skipping")


def parse_url(url):
    if ffnet.search(url):
        url = "www." + ffnet.search(url).group(1)
    elif neutral.search(url):
        url = neutral.search(url).group(1)
    return url
    
def get_files(mypath, filetype=None, fullpath=False):
    ans = []
    if filetype:
        ans = [f for f in listdir(mypath) if isfile(join(mypath, f)) and f.endswith(filetype)]
    else:
        ans = [f for f in listdir(mypath) if isfile(join(mypath, f))]
    if fullpath:
        return [join(mypath, f) for f in ans]
    else:
        return ans
        
def check_regexes(output):
    if equal_chapters.search(output):
        raise ValueError("Issue with story, site is broken. Story likely hasn't updated on site yet.")
    if bad_chapters.search(output):
        raise ValueError("Something is messed up with the site or the epub. No chapters found.")
    if no_url.search(output):
        raise ValueError("No URL in epub to update from. Fix the metadata.")

def main(user, password, server, label, inout_file, path ):
    if path:
        path = '--with-library "{}"'.format(path)
        try:
            with open(devnull, 'w') as nullout:
               call(['calibredb'], stdout=nullout, stderr=nullout)
        except OSError as e:
            if errno == ENOENT:
                print "Calibredb is not installed on this system. Cannot search the calibre library or update it."
                return
        
    touch(inout_file)

    with open(inout_file, "r") as fp:
        urls = set([x.replace("\n", "") for x in fp.readlines()])
        
    with open(inout_file, "w") as fp:
        fp.write("")
        urls |= geturls.get_urls_from_imap(server, user, password, label)
                
        urls = set(parse_url(x) for x in urls)
        
        if len(urls) != 0: print "URLs to parse: {}".format(", ".join(urls))

        loc = mkdtemp()


        
        for url in urls:
            print "Working with url {}".format(url)
            storyId = None
            try:
                if path:
                    try:
                        res = check_output('calibredb search "Identifiers:{}" {}'.format(url, path), shell=True,stderr=STDOUT,stdin=PIPE, ) 
                        storyId = res
                        print "\tStory is in calibre with id {}".format(storyId)
                        print "\tExporting file"
                        res = check_output('calibredb export {} --dont-save-cover --dont-write-opf --single-dir --to-dir "{}" {}'.format(storyId, loc, path), shell=True, stdin=PIPE, stderr=STDOUT)
                        cur = get_files(loc, ".epub", True)[0]
                        print '\tDownloading with fanficfare, updating file "{}"'.format(cur)
                        moving=""
                    except:
                        #story is not in calibre
                        cur = url
                        moving = 'cd "{}" && '.format(loc)
                    print '{}fanficfare -u "{}" --update-cover'.format(moving, cur)
                    res = check_output('{}fanficfare -u "{}" --update-cover'.format(moving, cur), shell=True,stderr=STDOUT,stdin=PIPE, )
                    check_regexes(res)
                    if chapter_difference.search(res) or more_chapters.search(res):
                        print "\tForcing download update\n"
                        res = check_output('{}fanficfare -u "{}" --force --update-cover'.format(moving, cur), shell=True,stderr=STDOUT,stdin=PIPE, )
                        check_regexes(res)
                    cur = get_files(loc, '.epub', True)[0]

                    
                    if storyId:    
                        print "\tRemoving {} from library".format(storyId)
                        res = check_output('calibredb remove {} {}'.format(storyId, path), shell=True,stderr=STDOUT,stdin=PIPE, )
                    
                    print "\tAdding {} to library".format(cur)
                    res = check_output('calibredb add "{}" -d {}'.format(cur, path), shell=True,stderr=STDOUT,stdin=PIPE, )
                    res = check_output('calibredb search "Identifiers:{}" {}'.format(url, path), shell=True, stderr=STDOUT,stdin=PIPE, )
                    print "\tAdded {} to library with id {}".format(cur, res)
                    remove(cur)
                else:
                    res = check_output('cd "{}" && fanficfare -u "{}" --update-cover'.format(loc, url), shell=True,stderr=STDOUT,stdin=PIPE, )
                    check_regexes(res)
                    cur = get_files(loc, '.epub', True)[0]
                    name = get_files(loc, '.epub', False)[0]
                    rename(cur, name)
                    print "Downloaded story {} to {}".format(story_name.search(name).group(1), name)
            except Exception as e:
                print "Exception: {}".format(e)
                rmtree(loc)
                loc = mkdtemp()
                fp.write("{}\n".format(url))
                continue
 
        rmtree(loc)


if __name__ == "__main__":
    option_parser = OptionParser(usage="usage: %prog [flags]")
    
    option_parser.add_option('-u', '--user', action='store', dest='user', help='Email Account Username. Required.')
    
    option_parser.add_option('-p', '--password', action='store', dest='password', help='Email Account Password. Required.')
    
    option_parser.add_option('-s', '--server', action='store', dest='server', default="imap.gmail.com", help='Email IMAP Server. Default is "imap.gmail.com".')
    
    option_parser.add_option('-m', '--mailbox', action='store', dest='mailbox', default='INBOX', help='Email Label. Default is "INBOX".')
    
    option_parser.add_option('-l', '--library', action='store', dest='library', help="calibre library db location. If none is passed, then this merely scrapes the email and error file for new stories and downloads them into the current directory.")
    
    option_parser.add_option('-i', '--input', action='store', dest='input', default="./fanfiction.txt", help="Error file. Any urls that fail will be output here, and file will be read to find any urls that failed previously. If file does not exist will create. File is overwitten every time the program is run.")
    
    option_parser.add_option('-c', '--config', action='store', dest='config', help='Config file for inputs. Blank config file is provided. No default. If an option is present in whatever config file is passed it, the option will overwrite whatever is passed in through command line arguments unless the option is blank. Do not put any quotation marks in the options.')
    
    (options, args) = option_parser.parse_args()
    
    if options.config:
        touch(options.config)
        config = ConfigParser(allow_no_value=True)
        config.read(options.config)
        
        updater = lambda option, newval : newval if newval != "" else option
        try: options.user = updater(options.user, config.get('login', 'user').strip())
        except: pass
        
        try: options.password = updater(options.password, config.get('login', 'password').strip())
        except: pass
        
        try: options.server = updater(options.server, config.get('login', 'server').strip())
        except: pass
        
        try: options.mailbox = updater(options.mailbox, config.get('login', 'mailbox').strip())
        except: pass
        
        try: options.library = updater(options.library, config.get('locations', 'library').strip())
        except: pass
        
        try: options.input = updater(options.input, config.get('locations', 'input').strip())
        except: pass
        
    if not (options.user or options.password):
        raise ValueError("User or Password not given")
    
    main(options.user, options.password, options.server, options.mailbox, options.input, options.library)
            
            
    

        
