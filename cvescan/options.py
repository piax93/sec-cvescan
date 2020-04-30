import configparser
import cvescan.constants as const
from cvescan.errors import ArgumentError
import logging
import os
import re
import sys

FMT_CVE_OPTION = "-c|--cve"
FMT_EXPERIMENTAL_OPTION = "-x|--experimental"
FMT_FILE_OPTION = "-f|--file"
FMT_MANIFEST_OPTION = "-m|--manifest"
FMT_NAGIOS_OPTION = "-n|--nagios"
FMT_PRIORITY_OPTION = "-p|priority"
FMT_REUSE_OPTION = "-r|--reuse"
FMT_SILENT_OPTION = "-s|--silent"
FMT_TEST_OPTION = "-t|--test"
FMT_UPDATES_OPTION = "-u|--updates"

MANIFEST_URL_TEMPLATE = "https://cloud-images.ubuntu.com/%s/current/%s-server-cloudimg-amd64.manifest"

class Options:
    def __init__(self, args, logger):
        self.logger = logger

        raise_on_invalid_args(args)
        self.distrib_codename = get_ubuntu_codename(args)

        self._set_mode(args)
        self._set_oval_file_options(args)
        self._set_manifest_file_options(args)
        self._set_remove_cached_files_options(args)
        self._set_output_verbosity(args)

        self.cve = args.cve
        self.priority = args.priority
        self.all_cve = not args.updates
        self.scriptdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        # TODO: Find a better way to locate this file than relying on it being in the
        #       same directory as this script
        self.xslt_file = str("%s/text.xsl" % self.scriptdir)
        # TODO: Find a better solution than this
        self.extra_sed = "" if args.list else "-e s@^@http://people.canonical.com/~ubuntu-security/cve/@"

    def _set_mode(self, args):
        self.manifest_mode = True if args.manifest else False
        self.experimental_mode = args.experimental
        self.test_mode = args.test
        self.nagios = args.nagios

    def _set_oval_file_options(self, args):
        self.oval_base_url = "https://people.canonical.com/~ubuntu-security/oval"
        self.oval_file = "com.ubuntu.%s.cve.oval.xml" % self.distrib_codename

        if self.manifest_mode:
            self.oval_file = "oci.%s" % self.oval_file

        if self.experimental_mode:
            self.oval_base_url = "%s/alpha" % self.oval_base_url
            self.oval_file = "alpha.%s" % oval_file

        self.oval_zip = "%s.bz2" % self.oval_file

    def _set_manifest_file_options(self, args):
        self.manifest_file = os.path.abspath(args.file) if args.file else None
        self.manifest_url = MANIFEST_URL_TEMPLATE % (self.distrib_codename, self.distrib_codename)

    def _set_remove_cached_files_options(self, args):
        self.remove = not args.reuse or args.manifest

    def _set_output_verbosity(self, args):
        self.verbose_oscap_options = ""

        if args.verbose:
            self.logger.setLevel(logging.DEBUG)
            self.verbose_oscap_options = "--verbose WARNING --verbose-log-file %s" % const.DEBUG_LOG
        elif args.silent:
            self.logger = get_null_logger()


def raise_on_invalid_args(args):
    raise_on_invalid_cve(args)
    raise_on_invalid_combinations(args)
    raise_on_invalid_manifest_file(args)

def raise_on_invalid_cve(args):
    cve_regex = r"^CVE-[0-9]{4}-[0-9]{4,}$"
    if (args.cve is not None) and (not re.match(cve_regex, args.cve)):
        raise ValueError("Invalid CVE ID (%s)" % args.cve)

def raise_on_invalid_combinations(args):
    raise_on_invalid_manifest_options(args)
    raise_on_invalid_nagios_options(args)
    raise_on_invalid_test_options(args)
    raise_on_invalid_silent_options(args)

def raise_on_invalid_manifest_options(args):
    if args.manifest and args.reuse:
        raise_incompatible_arguments_error(FMT_MANIFEST_OPTION, FMT_REUSE_OPTION)

    if args.manifest and args.test:
        raise_incompatible_arguments_error(FMT_MANIFEST_OPTION, FMT_TEST_OPTION)

    if args.file and not args.manifest:
        raise ArgumentError("Cannot specify -f|--file argument without -m|--manifest.")

def raise_on_invalid_nagios_options(args):
    if not args.nagios:
        return

    if args.cve:
        raise_incompatible_arguments_error(FMT_NAGIOS_OPTION, FMT_CVE_OPTION)

    if args.silent:
        raise_incompatible_arguments_error(FMT_NAGIOS_OPTION, FMT_SILENT_OPTION)

    if args.updates:
        raise_incompatible_arguments_error(FMT_NAGIOS_OPTION, FMT_UPDATES_OPTION)

def raise_on_invalid_test_options(args):
    if not args.test:
        return

    if args.cve:
        raise_incompatible_arguments_error(FMT_TEST_OPTION, FMT_CVE_OPTION)

    if args.experimental:
        raise_incompatible_arguments_error(FMT_TEST_OPTION, FMT_EXPERIMENTAL_OPTION)

    if args.file:
        raise_incompatible_arguments_error(FMT_TEST_OPTION, FMT_FILE_OPTION)

    if args.manifest:
        raise_incompatible_arguments_error(FMT_TEST_OPTION, FMT_MANIFEST_OPTION)

    if args.nagios:
        raise_incompatible_arguments_error(FMT_TEST_OPTION, FMT_NAGIOS_OPTION)

    if args.reuse:
        raise_incompatible_arguments_error(FMT_TEST_OPTION, FMT_REUSE_OPTION)

    if args.silent:
        raise_incompatible_arguments_error(FMT_TEST_OPTION, FMT_SILENT_OPTION)

    if args.updates:
        raise_incompatible_arguments_error(FMT_TEST_OPTION, FMT_UPDATES_OPTION)

def raise_on_invalid_silent_options(args):
    if not args.silent:
        return

    if not args.cve:
        raise ArgumentError("Cannot specify %s argument without %s." % (FMT_SILENT_OPTION, FMT_CVE_OPTION))

    if args.verbose:
        raise_incompatible_arguments_error(FMT_SILENT_OPTION, FMT_VERBOSE_OPTION)

def raise_incompatible_arguments_error(arg1, arg2):
    raise ArgumentError("The %s and %s options are incompatible and may not " \
            "be specified together." % (arg1, arg2))

def raise_on_invalid_manifest_file(args):
    if not args.file:
        return

    file_abs_path = os.path.abspath(args.file)
    if not os.path.isfile(file_abs_path):
        # TODO: mention snap confinement in error message
        raise ArgumentError("Cannot find manifest file \"%s\". Current "
                "working directory is \"%s\"." % (file_abs_path, os.getcwd()))

def get_lsb_release_info():
    with open("/etc/lsb-release", "rt") as lsb_file:
        lsb_file_contents = lsb_file.read()

    # ConfigParser needs section headers, so adding a header.
    lsb_file_contents = "[lsb]\n" + lsb_file_contents

    lsb_config = configparser.ConfigParser()
    lsb_config.read_string(lsb_file_contents)

    return lsb_config

# TODO: This probably shouldn't be determined in Options
def get_ubuntu_codename(args):
    if args.manifest:
        return args.manifest

    lsb_config = get_lsb_release_info()
    distrib_id = lsb_config.get("lsb","DISTRIB_ID")

    # NOTE: I don't care about DISTRIB_ID if cvescan was run with --manifest
    # Compare /etc/lsb-release to acceptable environment.
    if distrib_id != "Ubuntu":
        raise DistribIDError("DISTRIB_ID in /etc/lsb-release must be Ubuntu (DISTRIB_ID=%s)" % distrib_id)

    return lsb_config.get("lsb","DISTRIB_CODENAME")

def get_null_logger():
    logger = logging.getLogger("cvescan.null")
    logger.addHandler(logging.NullHandler())

    return logger