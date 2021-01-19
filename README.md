# check_pycurl3

A nagios / icinga / shinken / icinga2 plugin to check webservers via HTTP requests.

Written in python. Licensed under GPL v3.


**DEPENDENCIES**

python 3.x with modules:
- pycurl  (with TLS support)
- pyyaml

*Python 2 version which is now unmaintained available @ https://github.com/jamespo/check_pycurl*

## INSTALLATION

Just install the dependencies, copy the script to your standard path for nagios plugins (eg /usr/local/nagios/plugins) and configure in your monitoring tool (see SERVER CONFIGURATION).


## USAGE

    Usage: check_pycurl [options]

    Options:
      -h, --help            show this help message and exit
      -u URL, --url=URL
      -f RUNFILE, --runfile=RUNFILE
      --test=TEST           [code:HTTPCODE|regex:REGEX]
      --connect-timeout=CONNECTTIMEOUT
      --timeout=TIMEOUT
      --proxy=PROXY
      --location            Follow redirects
      --insecure

check_pycurl can run in one of two ways, a simple one-off http check (specify the url with -u) or with a runfile which is written in yaml and can be used to specify multi-stage url checks (eg logging in then checking for success).

By default check_pycurl will test for HTTP 200 code (--test code:200)

An alternate test is for presence of regex in the output (--test regex:t.st)


**EXAMPLE RUNFILE**

    ---
    cookiejar: no

    urls:
      - url: http://jamespo.org.uk
        test: code:200
      - url: http://yahoo.com
        test: code:301


## SERVER CONFIGURATION

**Nagios / Icinga 1**

    # simple configuration just for HTTP 200 check 
    define command {
      command_name	check_pycurl
      command_line	/usr/local/nagios/plugins/check_pycurl --url $ARG1$
    }

    # configuration to use runfiles
    define command {
      command_name	check_pycurl_rf
      command_line	/usr/local/nagios/plugins/check_pycurl -f $ARG1$
    }

    # host check
    define service {
            use                             generic-service
            host_name                       local2
            service_description             BBC web check
            check_command                   check_pycurl!http://www.bbc.co.uk
    }

    # runfile check
    define service {
            use                             generic-service
            host_name                       local2
            service_description             Roundcube Login Check
            check_command                   check_pycurl_rf!/opt/nagios/pyc_rf/rc.yml
    }

**Icinga 2**

    const LocalPluginDir = "/usr/local/nagios/plugins"

    object CheckCommand "pycurl" {
          command = [ LocalPluginDir + "/check_pycurl3" ]
          arguments = {
                    "--url" = {
                          value = "$url$"
                          description = "URL to check"
                    }
                    "--test" = {
                            value = "$urltest$"
                            description = "code:HTTPCODE|regex:REGEX"
                    }
            }
            vars.urltest = "code:200"
    }

    apply Service for (url in host.vars.urls) {
      import "generic-service"
      
      check_command = "pycurl"
      vars.url = url
      
      check_interval = 10m
      retry_interval = 1m
      
      assign where host.vars.urls
    }

    object Host "cloud" {
      import "generic-host"
      address = "127.1.1.1"
      vars.os = "Cloud"

      vars.urls = ["https://webscalability.com", "https://www.amazon.co.uk"]
    }
