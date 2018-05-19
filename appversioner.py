"""
It's a software update checker.

Configuration in apps.json
"""

import argparse
import os
import struct
import traceback
import urllib
import re
import sys

import bs4
import httplib2

from get_file_info import get_file_info
from util import read_json

import raven


# Report crashes to the maintainer with context
REPORT_CRASHES = True

PAUSE_BEFORE_CRASH_REPORT = True

raven_client = raven.Client('https://cd469360d77b439ba15d9dd1858ebc3a:601bb3882eff4ddaa5f1b44a69070222@sentry.io/1209952')


# TODO move this out; maybe there's something that can deliver a suitable UA for the platform
USER_AGENT = """Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36"""

script_path = os.path.dirname(os.path.abspath(__file__))


class WebValueException(Exception):
    pass


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-all", "-a",
                        default=False,
                        action="store_true",
                        help="Show versions for all software, not just those with updates")
    parser.add_argument("--dump-page-on-error", "-d",
                        default=False,
                        action="store_true",
                        help="Output the contents of the web page fetched to get the version from if there is an error")
    return parser.parse_args()


def extract_float(s):
    value_str = re.findall("\d+\.\d+", s)[0]
    return float(value_str)


def extract_multi_part(s, web_version_offset=None):
    return int_version_parts(re.findall("\d+\.\d+(?:\.\d+)+", s)[0], web_version_offset=web_version_offset)


def extract_three_part(s, web_version_offset=None):
    return int_version_parts(re.findall("\d+\.\d+\.\d+", s)[0], web_version_offset=web_version_offset)


def extract_three_part_implicit(s, web_version_offset=None):
    out = int_version_parts(re.findall("\d+\.\d+(?:\.\d+)?", s)[0], web_version_offset=web_version_offset)    
    if len(out) == 2:
        out = tuple(list(out) + [0])
    return out


def extract_two_part(s, web_version_offset=None):
    return int_version_parts(re.findall("\d+\.\d+", s)[0], web_version_offset=web_version_offset)


def int_version_parts(v, web_version_offset=None):
    num_parts = [int(x) for x in v.split(".")]
    if web_version_offset is not None:
        num_parts = [x - y for (x, y) in zip(num_parts, web_version_offset)]
    return tuple(num_parts)


def noop(s):
    return s


def die(msg):
    print >> sys.stderr, msg
    sys.exit(1)


CONVERTERS = {
    "float": extract_float,
    "multi": extract_multi_part,
    "three": extract_three_part,
    "three_implicit": extract_three_part_implicit,
    "two": extract_two_part,
    "none": noop,
}


class App(object):
    def __init__(self, program_file, website_url=None, version_attr="FileVersion", selector=None, converter="none",
                 selector_conditions=None, selector_finally=None, selector_options=None,
                 use_user_agent=False, web_version_offset=None, dir_env=None, dump_page_on_error=False):
        self.dir_env = dir_env
        self.program_file = program_file
        self.website_url = website_url
        self.version_attr = version_attr
        self.selector = selector
        self.selector_conditions = selector_conditions
        self.selector_finally = selector_finally
        self.selector_options = selector_options
        self.converter = converter
        self.use_user_agent = use_user_agent
        self.web_version_offset = web_version_offset
        self.dump_page_on_error = dump_page_on_error

        cacert_filename = os.path.join(script_path, "cacert.pem")
        if not os.path.isfile(cacert_filename):
            die("cacert.pem (root certificates file for HTTPS) not found. You can get a suitable cacert.pem from https://curl.haxx.se/docs/caextract.html")

        self.h = httplib2.Http(".httplib2cache", ca_certs=cacert_filename)

    def config(self):
        return {key: getattr(self, key) for key in ("dir_env", "program_file", "website_url", "version_attr", "selector", "converter",
                                                    "selector_conditions", "selector_finally", "selector_options", "use_user_agent",
                                                    "web_version_offset")}

    def get_converter_func(self):
        return CONVERTERS[self.converter]

    def get_web_value(self):
        assert self.website_url is not None
        # data = fetch_url(self.website_url)
        request_kwargs = {}
        if self.use_user_agent:
            request_kwargs["headers"] = {"User-Agent": USER_AGENT}
        _, data = self.h.request(self.website_url, **request_kwargs)
        soup = soup_data(data)
        if self.selector is None:
            print soup
        assert self.selector is not None
        tags = soup.select(self.selector)
        if self.selector_conditions is not None:
            conditions = self.selector_conditions
            if not isinstance(conditions, list):
                conditions = [conditions]
            for selector_condition in conditions:
                filtered_tags = []
                for tag in tags:
                    l = tag.select(selector_condition)
                    if len(l) != 0:
                        filtered_tags.append(tag)
                tags = filtered_tags

        if len(tags) == 0:
            if self.dump_page_on_error:
                print soup
            raise WebValueException("Selector '%s' didn't match anything on the page %s" % (self.selector, self.website_url))

        if self.selector_finally is not None:
            tags = tags[0].select(self.selector_finally)

        if self.selector_options == "href":
            value_str = tags[0]["href"]
        else:
            if self.selector_options == "last":
                tags = tags[-1:]

            value_str = "".join(tags[0].findAll(text=True))
        converter_func = self.get_converter_func()
        converter_kwargs = {}
        if self.web_version_offset is not None:
            converter_kwargs["web_version_offset"] = self.web_version_offset
        try:
            value = converter_func(value_str, **converter_kwargs)
        except IndexError:
            raise WebValueException("Can't find '%s' style version in selector '%s' text from page %s: %r" % (self.converter, self.selector, self.website_url, value_str))

        return value


def soup_data(data):
    return bs4.BeautifulSoup(data, "html.parser")


def fetch_url(url):
    handle = urllib.urlopen(url)
    try:
        return handle.read()
    finally:
        handle.close()


def ver_str(v):
    if isinstance(v, tuple):
        return ".".join(str(x) for x in v)
    else:
        return v


def pause():
    sys.stdin.readline()


def main():
    # noinspection PyBroadException
    try:
        inner_main()
    except:
        capture_exception()


def capture_exception():
    if REPORT_CRASHES:
        traceback.print_exc()
        if PAUSE_BEFORE_CRASH_REPORT:
            print "Press Enter to upload Exception with context to Sentry or Ctrl-Break/Ctrl-C to cancel"
            pause()
        raven_client.captureException()


def inner_main():
    options = parse_args()

    apps = read_json(os.path.join(script_path, "apps.json"))

    apps = [App(dump_page_on_error=options.dump_page_on_error, **app) for app in apps]

    for app in apps:
        with raven_client.context:
            raven_client.extra_context({"app_%s" % n: repr(val) for (n, val) in app.config().iteritems()})

            # raise Exception("hello, I am a test exception")

            converter_func = CONVERTERS[app.converter]

            if app.dir_env is not None:
                program_filename = os.environ[app.dir_env] + "\\" + app.program_file
            else:
                program_filename = app.program_file

            if not os.path.exists(program_filename):
                print "%s not found" % program_filename
                continue

            installed_version = get_file_info(program_filename.encode("utf-8"), app.version_attr)
            if app.version_attr == "ProductVersion":
                # print repr(installed_version)
                assert installed_version.startswith("\xbd\x04\xef\xfe")
                installed_version = ".".join(str(x) for x in reversed(struct.unpack("<HHHH", installed_version[12:12 + 8])))
            elif installed_version.endswith("\x00"):
                # it's a string
                installed_version = installed_version[:-1].replace(",", ".")
            else:
                print repr(installed_version)
                assert False, "%s unknown format" % program_filename

            got_installed_version_val = True
            ver_repr = None

            try:
                installed_version_val = converter_func(installed_version)
            except IndexError:
                got_installed_version_val = False
                ver_repr = "Can't get normalized version value '%s' from program file '%s' field '%s' using converter '%s'" % (installed_version, program_filename, app.version_attr, app.converter)
                capture_exception()

            if got_installed_version_val:
                pass
            elif app.website_url is None:
                ver_repr = ver_str(installed_version_val)
            else:
                # noinspection PyBroadException
                try:
                    available_version_val = app.get_web_value()
                except Exception, e:
                    if isinstance(e, WebValueException):
                        # This is a known exception where the exception string is ready for output
                        ver_repr = "Error getting version from web page: %s" % e
                    else:
                        ver_repr = "Exception while getting version from web page: %r" % e
                        capture_exception()
                else:
                    if available_version_val == installed_version_val:
                        if not options.show_all:
                            continue
                        ver_repr = ver_str(installed_version_val)
                    elif available_version_val < installed_version_val:
                        if not options.show_all:
                            continue
                        ver_repr = "%s [%s]" % (ver_str(installed_version_val), ver_str(available_version_val))
                    else:
                        ver_repr = "%s => %s %s" % (ver_str(installed_version_val), ver_str(available_version_val), app.website_url)

            filename_proper = os.path.basename(program_filename)

            print "%s, %s" % (filename_proper, ver_repr)


if __name__ == "__main__":
    main()
