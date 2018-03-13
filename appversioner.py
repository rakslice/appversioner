"""
It's a software update checker.

Configuration in apps.json

You can get a suitable cacert.pem from https://curl.haxx.se/docs/caextract.html
"""

import argparse
import os
import struct
import urllib
import re

import bs4
import httplib2

from get_file_info import get_file_info
from util import read_json


USER_AGENT = """Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36"""

script_path = os.path.dirname(os.path.abspath(__file__))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-all", "-a",
                        default=False,
                        action="store_true",
                        help="Show versions for all software, not just those with updates")
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
                 use_user_agent=False, web_version_offset=None, dir_env=None):
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

        self.h = httplib2.Http(".httplib2cache", ca_certs=os.path.join(script_path, "cacert.pem"))

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

        if self.selector_finally is not None:
            tags = tags[0].select(self.selector_finally)

        if self.selector_options == "href":
            value_str = tags[0]["href"]
        else:
            if self.selector_options == "last":
                tags = tags[-1:]

            if len(tags) == 0:
                print soup

            value_str = "".join(tags[0].findAll(text=True))
        converter_func = self.get_converter_func()
        converter_kwargs = {}
        if self.web_version_offset is not None:
            converter_kwargs["web_version_offset"] = self.web_version_offset
        try:
            value = converter_func(value_str, **converter_kwargs)
        except IndexError:
            print "website", self.website_url
            print "value_str", repr(value_str)
            raise

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


def main():
    options = parse_args()

    apps = read_json(os.path.join(script_path, "apps.json"))

    apps = [App(**app) for app in apps]

    for app in apps:
        converter_func = CONVERTERS[app.converter]

        if app.dir_env is not None:
            program_filename = os.environ[app.dir_env] + "\\" + app.program_file
        else:
            program_filename = app.program_file

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
        try:
            installed_version_val = converter_func(installed_version)
        except IndexError:
            print "installed_version_str", installed_version
            raise

        if app.website_url is None:
            ver_repr = ver_str(installed_version_val)
        else:
            available_version_val = app.get_web_value()

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
