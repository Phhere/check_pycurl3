#!/usr/bin/env python3

# check_pycurl3 ; -*-Python-*-
# Copyright James Powell 2013-2021 / jamespo [at] gmail [dot] com
# This program is distributed under the terms of the GNU General Public License v3

import json
import pycurl
from io import BytesIO
from collections import ChainMap
import uuid
import sys
import os
import re
import yaml
from urllib.parse import urlencode
import copy
from optparse import OptionParser
import html 


class CheckPyCurlOptions(object):
    """class to contain check options for multi-mode"""

    def __init__(self):
        """set defaults if not present"""
        # correlate to CLI params for single-use mode
        self.test = "code:200"
        self.connecttimeout = 5
        self.timeout = 10
        self.location = False
        self.insecure = False
        self.proxy = None
        self.postdata = None
        self.tmpfile = None
        self.cookiejar = False
        self.url = None
        self.failaterror = True
        self.debug = False
        self.user_agent = "check_pycurl3"
        self.flags = []  # for other flags not explicitly in attr


class CheckPyCurlMulti(object):
    def __init__(self, runfile, debug=False):
        self.runfile = runfile
        self.checkoptobjs = []
        self.debug = debug

    @staticmethod
    def tmpfile():
        """return temporary filename"""
        return "%s%s" % ("/tmp/check_pycurl_", str(uuid.uuid4()))

    @staticmethod
    def rm_tmpfile():
        """remove cookiejar file if it exists"""
        if getattr(CheckPyCurlOptions, "tmpfile", False) and os.path.exists(
            CheckPyCurlOptions.tmpfile
        ):
            # print 'removing file'
            os.remove(CheckPyCurlOptions.tmpfile)

    def parse_runfile(self):
        """parse runfile & create check option objects"""
        with open(self.runfile) as f:
            runyaml = yaml.safe_load(f)
        global_options = CheckPyCurlOptions()
        # set global prefs
        for global_opt in runyaml:
            if global_opt == "cookiejar":
                if runyaml["cookiejar"] != "no":
                    CheckPyCurlOptions.tmpfile = self.tmpfile()
                    CheckPyCurlOptions.cookiejar = True
            elif global_opt == "urls":
                # loop round urls in object & create checkobjects
                # (this would be last section in runfile)
                for url in runyaml["urls"]:
                    local_options = copy.copy(global_options)
                    for opt in url:
                        setattr(local_options, opt, url[opt])
                    # set debug if required
                    setattr(local_options, "debug", self.debug)
                    self.checkoptobjs.append(local_options)
            elif global_opt == "flags":
                # if not an alias or "special" set in hash
                if self.debug:
                    print(
                        "DEBUG: Setting global_options.flags to %s" % runyaml["flags"]
                    )
                # convert list of dicts to single dict
                global_options.flags = dict(ChainMap(*runyaml["flags"]))
            else:
                # explicit attribute (eg insecure)
                setattr(global_options, global_opt, runyaml[global_opt])

    def check_runfile(self):
        """run check objects"""
        cpc = None
        search_results = {}
        total_req_time = 0
        for counter, checkobj in enumerate(self.checkoptobjs):
            cpc = CheckPyCurl(options=checkobj, prev_matches=search_results)
            rc = cpc.curl()
            cpc.results["stage"] = counter
            # store running total of reqtime
            total_req_time += cpc.results["totaltime"]
            cpc.results["totaltime"] = total_req_time
            if rc != 0 and checkobj.failaterror:
                self.rm_tmpfile()
                return cpc
            # store regex match results for later use if available
            if cpc.results.get("search_res", None) is not None:
                search_results[counter] = cpc.results["search_res"]
        self.rm_tmpfile()
        return cpc


class CheckPyCurl(object):

    def __init__(self, options, prev_matches=None):
        if prev_matches is None:
            prev_matches = {}
        self.options = options
        self.results = dict()
        self.prev_matches = prev_matches
        self.successtest, self.successcheck = options.test.split(":")

    def create_curl_obj(self):
        """create pycurl object & set options"""
        c = pycurl.Curl()
        if 'PREV_MATCH_' in self.options.url:
            url = self.options.url
            check_postdata = re.match(r'.*PREV_MATCH_(\d+)_(\d+)$', url)
            if check_postdata is not None:
                (url_match_stage, url_match_num) = (int(check_postdata.group(1)),
                                                    int(check_postdata.group(2)))
                replacement = html.unescape(self.prev_matches[url_match_stage].group(url_match_num))
                url = url.replace('PREV_MATCH_'+str(url_match_stage)+'_'+str(url_match_num),replacement)
                self.options.url = url
        self._set_manual_options(c)
        if getattr(self.options, "cookiejar", False):
            c.setopt(pycurl.COOKIEJAR, self.options.tmpfile)
            c.setopt(pycurl.COOKIEFILE, self.options.tmpfile)
        if self.options.proxy is not None:
            c.setopt(c.PROXY, self.options.proxy)
        # set the flags
        for flag in self.options.flags:
            # "dynamic" curl option setting
            if self.options.debug:
                print("Flag: %s: %s" % (flag, self.options.flags[flag]))
            flag_attr = getattr(c, flag.upper())
            if flag == "resolve":
                # args have to be list
                c.setopt(flag_attr, self.options.flags[flag].split(","))
            elif flag == "ipresolve":
                # arg is pycurl const
                c.setopt(
                    flag_attr,
                    getattr(c, self.options.flags[flag].upper()),
                )
            else:
                c.setopt(flag_attr, self.options.flags[flag])
        # if a POST, set up options
        if getattr(self.options, "postdata", None) is not None:
            post_params = {}
            # split out post param & value and append to postitems
            for item in self.options.postdata:
                # post_params.append(tuple(item.split(':', 1)))
                (postname, postdata) = item.split(":", 1)
                # is data actually a lookup to previous match and if so substitute in
                check_postdata = re.match(r"PREV_MATCH_(\d+)_(\d+)$", postdata)
                if check_postdata is not None:
                    (url_match_stage, url_match_num) = (
                        int(check_postdata.group(1)),
                        int(check_postdata.group(2)),
                    )
                    postdata = self.prev_matches[url_match_stage].group(url_match_num)
                post_params[postname] = postdata
            if self.options.debug:
                print("POST fields: %s" % str(post_params))
            resp_data = urlencode(post_params)
            c.setopt(pycurl.POSTFIELDS, resp_data)
            c.setopt(pycurl.POST, 1)
        if getattr(self.options,'referer',None) is not None:
            #print("referer:"+ self.options.referer)
            c.setopt(pycurl.REFERER, self.options.referer)
        return c

    def _set_manual_options(self, c):
        """set manual options on curl object"""
        c.setopt(c.URL, self.options.url)
        c.setopt(c.CONNECTTIMEOUT, self.options.connecttimeout)
        c.setopt(c.TIMEOUT, self.options.timeout)
        c.setopt(c.FOLLOWLOCATION, 1)
        c.setopt(c.SSL_VERIFYPEER, not self.options.insecure)
        c.setopt(c.USERAGENT, self.options.user_agent)
        c.setopt(c.VERBOSE, self.options.debug)


    def curl(self):
        """make the request"""
        buf = BytesIO()
        # create object & set options
        c = self.create_curl_obj()
        c.setopt(c.WRITEFUNCTION, buf.write)
        # send the request
        try:
            c.perform()
            self.options.referer = c.getinfo(pycurl.EFFECTIVE_URL)
            self.content = buf.getvalue().decode("utf-8")
            self.results["rc"] = 0
            self.results["status"] = "%s returned HTTP %s" % (
                self.options.url,
                c.getinfo(pycurl.HTTP_CODE),
            )
            if self.options.debug:
                print(self.content)
                print(c.getinfo(pycurl.HTTP_CODE))
                print(c.getinfo(pycurl.EFFECTIVE_URL))
            # check results
            if self.successtest == "code":
                if int(self.successcheck) != int(c.getinfo(pycurl.HTTP_CODE)):
                    self.results["rc"] = 2
            elif self.successtest == "regex":
                search_res = re.search(self.successcheck, self.content, re.MULTILINE)
                if search_res is not None:
                    self.results["status"] = "%s found in %s" % (
                        self.successcheck,
                        self.options.url,
                    )
                    self.results["rc"] = 0
                    # store match result for possible later use
                    self.results["search_res"] = search_res
                else:
                    self.results["status"] = "%s not found in %s" % (
                        self.successcheck,
                        self.options.url,
                    )
                    self.results["rc"] = 2
            else:
                self.results["rc"] = 1
        except pycurl.error as excep:
            self.results["rc"] = 2
            self.results["status"] = excep.args[1]

        buf.close()

        self.results["totaltime"] = c.getinfo(pycurl.TOTAL_TIME)
        return self.results["rc"]


def checkargs(options):
    if options.url is None and options.runfile is None:
        # 3 is return code for unknown for NRPE plugin
        return (3, "No URL / runfile supplied")
    # TODO: check if runfile exists
    else:
        return (0, "")


def get_cli_options():
    """get command line options & return OptionParser"""
    parser = OptionParser()
    parser.add_option("-u", "--url", dest="url")
    parser.add_option("-f", "--runfile", dest="runfile")
    parser.add_option(
        "--test", dest="test", default="code:200", help="[code:HTTPCODE|regex:REGEX]"
    )
    parser.add_option("--connect-timeout", dest="connecttimeout", default=5)
    parser.add_option("--timeout", dest="timeout", default=10)
    parser.add_option("--postdata", dest="postdata", help="var1:value1,var2:value2")
    parser.add_option("--proxy", dest="proxy")
    parser.add_option(
        "--location",
        help="Follow redirects",
        dest="location",
        action="store_true",
        default=False,
    )
    parser.add_option(
        "--debug",
        help="turn on debug",
        dest="debug",
        action="store_true",
        default=False,
    )
    parser.add_option("--insecure", dest="insecure", action="store_true", default=False)
    parser.add_option("--useragent", dest="user_agent", default="check_pycurl3")
    parser.add_option("--flags", dest="flags", default="")
    options, _ = parser.parse_args()
    if options.flags == "":
        options.flags = {}
    else:
        options.flags = json.loads(options.flags)
    if options.postdata is not None:
        options.postdata = options.postdata.split(',')
    return options


def main():
    """get options, do checks, return results"""
    options = get_cli_options()
    (rc, rcstr) = checkargs(options)
    if rc != 3:
        if options.url is not None:
            cpc = CheckPyCurl(options)
            rc = cpc.curl()
            rcstr = "OK:" if rc == 0 else "CRITICAL:"
            rcstr = (
                rcstr
                + " "
                + cpc.results["status"]
                + " | request_time="
                + str(cpc.results["totaltime"])
            )
        else:
            # runfile
            a = CheckPyCurlMulti(options.runfile, options.debug)
            a.parse_runfile()
            cpc = a.check_runfile()
            rc = cpc.results["rc"]
            if rc == 0:
                rcstr = "OK: All stages passed (%s/%s)" % (
                    len(a.checkoptobjs),
                    len(a.checkoptobjs),
                )
            else:
                rcstr = "CRITICAL: Stage %s [%s] - %s (should be %s)" % (
                    cpc.results["stage"],
                    a.checkoptobjs[cpc.results["stage"]].url,
                    cpc.results["status"],
                    cpc.options.test,
                )
            rcstr += " | request_time=" + str(cpc.results["totaltime"])
    print(rcstr)
    sys.exit(rc)


if __name__ == "__main__":
    main()
