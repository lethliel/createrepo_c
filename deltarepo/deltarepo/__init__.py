"""
DeltaRepo package for Python.
This is the library for generation, application and handling of
DeltaRepositories.
The library is builded on the Createrepo_c library and its a part of it.

Copyright (C) 2013   Tomas Mlcoch

"""

import os
import shutil
import hashlib
import logging
import xml.dom.minidom
from lxml import etree
import createrepo_c as cr

__all__ = ['VERSION', 'VERBOSE_VERSION', 'DeltaRepoError',
           'DeltaRepoGenerator']

VERSION = "0.0.1"
VERBOSE_VERSION = "%s (createrepo_c: %s)" % (VERSION, cr.VERSION)

class DeltaRepoError(Exception):
    pass

class LoggingInterface(object):
    def __init__(self, logger=None):
        if logger is None:
            logger = logging.getLogger()
            logger.disabled = True
        self.logger = logger

    def _debug(self, msg):
        self.logger.debug(msg)

    def _info(self, msg):
        self.logger.info(msg)

    def _warning(self, msg):
        self.logger.warning(msg)

    def _error(self, msg):
        self.logger.error(msg)

    def _critical(self, msg):
        self.logger.critical(msg)

class DeltaModule(LoggingInterface):

    def __init__(self, id_type=None, logger=None):
        LoggingInterface.__init__(self, logger)

        if id_type is None:
            id_type = "sha256"
        self.id_type = id_type

    def _path(self, path, record):
        return os.path.join(path, record.location_href)

class MainDeltaModule(DeltaModule):

    def apply(self, pri_old_fn, pri_delta_fn, pri_f, fil_old_fn,
              fil_delta_fn, fil_f, oth_old_fn, oth_delta_fn, oth_f, removed):

        removed_packages = set() # set of pkgIds (hashes)
        all_packages = {}        # dicst { 'pkgId': pkg }

        def old_pkgcb(pkg):
            if pkg.location_href in removed.packages:
                if removed.packages[pkg.location_href] == pkg.location_base:
                    # This package won't be in new metadata
                    return
            all_packages[pkg.pkgId] = pkg

        def delta_pkgcb(pkg):
            all_packages[pkg.pkgId] = pkg

        do_primary_files = 1
        if fil_f and fil_delta_fn and fil_old_fn:
            do_primary_files = 0

        cr.xml_parse_primary(pri_old_fn, pkgcb=old_pkgcb,
                             do_files=do_primary_files)
        cr.xml_parse_primary(pri_delta_fn, pkgcb=delta_pkgcb,
                             do_files=do_primary_files)

        # Sort packages
        def cmp_pkgs(x, y):
            # Compare only by filename
            ret = cmp(os.path.basename(x.location_href),
                      os.path.basename(y.location_href))
            if ret != 0:
                return ret

            # Compare by full location_href path
            return  cmp(x.location_href, y.location_href)

        all_packages_sorted = sorted(all_packages.values(), cmp=cmp_pkgs)

        def newpkgcb(pkgId, name, arch):
            return all_packages.get(pkgId, None)

        # Parse filelists
        if fil_f and fil_delta_fn and fil_old_fn:
            cr.xml_parse_filelists(fil_old_fn, newpkgcb=newpkgcb)
            cr.xml_parse_filelists(fil_delta_fn, newpkgcb=newpkgcb)

        # Parse other
        if oth_f and oth_delta_fn and oth_old_fn:
            cr.xml_parse_other(oth_old_fn, newpkgcb=newpkgcb)
            cr.xml_parse_other(oth_delta_fn, newpkgcb=newpkgcb)

        num_of_packages = len(all_packages_sorted)

        # Write out primary
        pri_f.set_num_of_pkgs(num_of_packages)
        for pkg in all_packages_sorted:
            pri_f.add_pkg(pkg)
        pri_f.close()

        # Write out filelists
        if fil_f:
            fil_f.set_num_of_pkgs(num_of_packages)
            for pkg in all_packages_sorted:
                fil_f.add_pkg(pkg)
            fil_f.close()

        # Write out other
        if oth_f:
            oth_f.set_num_of_pkgs(num_of_packages)
            for pkg in all_packages_sorted:
                oth_f.add_pkg(pkg)
            oth_f.close()

    def do(self, pri_old_fn, pri_new_fn, pri_f,
           fil_new_fn, fil_f, oth_new_fn, oth_f, removed):

        old_packages = set()
        added_packages = {}         # dict { 'pkgId': pkg }
        added_packages_ids = []     # list of package ids

        old_repoid_strings = []
        new_repoid_strings = []

        def old_pkgcb(pkg):
            pkg_id_tuple = (pkg.pkgId, pkg.location_href, pkg.location_base)
            old_packages.add(pkg_id_tuple)
            pkg_id_string = "%s%s%s" % (pkg.pkgId,
                                        pkg.location_href,
                                        pkg.location_base or '')
            old_repoid_strings.append(pkg_id_string)

        def new_pkgcb(pkg):
            pkg_id_tuple = (pkg.pkgId, pkg.location_href, pkg.location_base)
            pkg_id_string = "%s%s%s" % (pkg.pkgId,
                                        pkg.location_href,
                                        pkg.location_base or '')
            new_repoid_strings.append(pkg_id_string)
            if not pkg_id_tuple in old_packages:
                # This package is only in new repodata
                added_packages[pkg.pkgId] = pkg
                added_packages_ids.append(pkg.pkgId)
            else:
                # This package is also in the old repodata
                old_packages.remove(pkg_id_tuple)

        do_new_primary_files = 1
        if fil_f and fil_new_fn:
            # All files will be parsed from filelists
            do_new_primary_files = 0

        cr.xml_parse_primary(pri_old_fn, pkgcb=old_pkgcb, do_files=0)
        cr.xml_parse_primary(pri_new_fn, pkgcb=new_pkgcb,
                             do_files=do_new_primary_files)

        # Calculate RepoIds
        old_repo_id = ""
        new_repo_id = ""

        h = hashlib.new(self.id_type)
        old_repoid_strings.sort()
        for i in old_repoid_strings:
            h.update(i)
        old_repo_id = h.hexdigest()

        h = hashlib.new(self.id_type)
        new_repoid_strings.sort()
        for i in new_repoid_strings:
            h.update(i)
        new_repo_id = h.hexdigest()

        removed_pkgs = sorted(old_packages)
        for _, location_href, location_base in removed_pkgs:
            removed.add_pkg_locations(location_href, location_base)

        num_of_packages = len(added_packages)

        # Filelists and Other cb
        def newpkgcb(pkgId, name, arch):
            return added_packages.get(pkgId, None)

        # Write out filelists delta
        if fil_f and fil_new_fn:
            cr.xml_parse_filelists(fil_new_fn, newpkgcb=newpkgcb)
            fil_f.set_num_of_pkgs(num_of_packages)
            for pkgid in added_packages_ids:
                fil_f.add_pkg(added_packages[pkgid])
            fil_f.close()

        # Write out other delta
        if oth_f and oth_new_fn:
            cr.xml_parse_other(oth_new_fn, newpkgcb=newpkgcb)
            oth_f.set_num_of_pkgs(num_of_packages)
            for pkgid in added_packages_ids:
                oth_f.add_pkg(added_packages[pkgid])
            oth_f.close()

        # Write out primary delta
        # Note: Writing of primary delta has to be after parsing of filelists
        # Otherway cause missing files if do_new_primary_files was 0
        pri_f.set_num_of_pkgs(num_of_packages)
        for pkgid in added_packages_ids:
            pri_f.add_pkg(added_packages[pkgid])
        pri_f.close()

        return (old_repo_id, new_repo_id)

class RemovedXml(object):
    def __init__(self):
        self.packages = {}  # { location_href: location_base }
        self.files = {}     # { location_href: location_base or Null }

    def __str__(self):
        print self.packages
        print self.files

    def add_pkg(self, pkg):
        self.packages[pkg.location_href] = pkg.location_base

    def add_pkg_locations(self, location_href, location_base):
        self.packages[location_href] = location_base

    def add_record(self, rec):
        self.files[rec.location_href] = rec.location_base

    def xml_dump(self):
        xmltree = etree.Element("removed")
        packages = etree.SubElement(xmltree, "packages")
        for href, base in self.packages.iteritems():
            attrs = {}
            if href: attrs['href'] = href
            if base: attrs['base'] = base
            if not attrs: continue
            etree.SubElement(packages, "location", attrs)
        files = etree.SubElement(xmltree, "files")
        for href, base in self.files.iteritems():
            attrs = {}
            if href: attrs['href'] = href
            if base: attrs['base'] = base
            if not attrs: continue
            etree.SubElement(files, "location", attrs)
        return etree.tostring(xmltree,
                              pretty_print=True,
                              encoding="UTF-8",
                              xml_declaration=True)

    def xml_parse(self, path):
        dom = xml.dom.minidom.parse(path)

        packages = dom.getElementsByTagName("packages")
        if packages:
            for loc in packages[0].getElementsByTagName("location"):
                href = loc.getAttribute("href")
                base = loc.getAttribute("base")
                if not href:
                    continue
                if not base:
                    base = None
                self.packages[href] = base

        files = dom.getElementsByTagName("files")
        if files:
            for loc in files[0].getElementsByTagName("location"):
                href = loc.getAttribute("href")
                base = loc.getAttribute("base")
                if not href:
                    continue
                if not base:
                    base = None
                self.files[href] = base

class DeltaRepoGenerator(LoggingInterface):
    """Object for generating of DeltaRepositories."""

    def __init__(self, id_type=None, logger=None):
        LoggingInterface.__init__(self, logger)

        if id_type is None:
            id_type = "sha256"
        self.id_type = id_type

    def _fn_without_checksum(self, path):
        """Strip checksum from a record filename"""
        path = os.path.basename(path)
        return path.rsplit('-')[-1]

    def applydelta(self, old_path, delta_path, out_path=None):
        removedxml = RemovedXml()
        hash_in_the_name = False

        # Prepare variables with paths
        old_repodata_path = os.path.join(old_path, "repodata/")
        delta_repodata_path = os.path.join(delta_path, "repodata/")

        old_repomd_path = os.path.join(old_repodata_path, "repomd.xml")
        delta_repomd_path = os.path.join(delta_repodata_path, "repomd.xml")

        # Prepare Repomd objects
        old_repomd = cr.Repomd(old_repomd_path)
        delta_repomd = cr.Repomd(delta_repomd_path)
        new_repomd = cr.Repomd()

        # Prepare output path
        new_path = os.path.join(out_path, ".repodata/")
        new_repodata_path = os.path.join(new_path, "repodata/")
        os.mkdir(new_path)
        os.mkdir(new_repodata_path)

        # Apply repomd delta
        new_repomd.set_revision(delta_repomd.revision)
        for tag in delta_repomd.distro_tags:
            new_repomd.add_distro_tag(tag[1], tag[0])
        for tag in delta_repomd.repo_tags:
            new_repomd.add_repo_tag(tag)
        for tag in delta_repomd.content_tags:
            new_repomd.add_content_tag(tag)

        old_records = dict([(record.type, record) for record in old_repomd.records ])
        delta_records = dict([(record.type, record) for record in delta_repomd.records ])
        old_record_types = set(old_records.keys())
        delta_record_types = set(delta_records.keys())
        deleted_repomd_record_types = old_record_types - delta_record_types
        added_repomd_record_types = delta_record_types - old_record_types
        # TODO: Skip removed record

        # Prepare removedxml
        if "removed" in delta_records:
            removedxml_path = os.path.join(delta_path,
                                delta_records["removed"].location_href)
            removedxml.xml_parse(removedxml_path)
        else:
            self._warning("\"removed\" record is missing in repomd.xml "\
                          "of delta repo")

        # Apply delta on primary, filelists and other
        if not "primary" in old_records or not "primary" in delta_records:
            raise DeltaRepoError("Missing primary metadata")

        if delta_records["primary"].location_href.split("primary")[0] != "":
            hash_in_the_name = True

        pri_old_fn = os.path.join(old_path, old_records["primary"].location_href)
        pri_delta_fn = os.path.join(delta_path, delta_records["primary"].location_href)
        pri_out_fn = os.path.join(new_repodata_path, "primary.xml.gz")
        pri_out_f_stat = cr.ContentStat(cr.SHA256)
        pri_out_f = cr.PrimaryXmlFile(pri_out_fn, cr.GZ_COMPRESSION)

        fil_old_fn = None
        fil_delta_fn = None
        fil_out_fn = None
        fil_out_f_stat = None
        fil_out_f = None
        if ("filelists" in delta_records):
            fil_old_fn = os.path.join(old_path, old_records["filelists"].location_href)
            fil_delta_fn = os.path.join(delta_path, delta_records["filelists"].location_href)
            fil_out_fn = os.path.join(new_repodata_path, "filelists.xml.gz")
            fil_out_f_stat = cr.ContentStat(cr.SHA256)
            fil_out_f = cr.FilelistsXmlFile(fil_out_fn, cr.GZ_COMPRESSION)

        oth_old_fn = None
        oth_delta_fn = None
        out_out_fn = None
        oth_out_f_stat = None
        oth_out_f = None
        if ("other" in delta_records):
            oth_old_fn = os.path.join(old_path, old_records["other"].location_href)
            oth_delta_fn = os.path.join(delta_path, delta_records["other"].location_href)
            oth_out_fn = os.path.join(new_repodata_path, "other.xml.gz")
            oth_out_f_stat = cr.ContentStat(cr.SHA256)
            oth_out_f = cr.OtherXmlFile(oth_out_fn, cr.GZ_COMPRESSION)

        deltamodule = MainDeltaModule(id_type=self.id_type, logger=self.logger)
        deltamodule.apply(pri_old_fn, pri_delta_fn, pri_out_f, fil_old_fn,
                          fil_delta_fn, fil_out_f, oth_old_fn, oth_delta_fn,
                          oth_out_f, removedxml)

        # Prepare repomd.xml records
        pri_rec = cr.RepomdRecord("primary", pri_out_fn)
        pri_rec.load_contentstat(pri_out_f_stat)
        pri_rec.fill(cr.SHA256)
        if hash_in_the_name:
            pri_rec.rename_file()
        new_repomd.set_record(pri_rec)

        if fil_out_fn:
            fil_rec = cr.RepomdRecord("filelists", fil_out_fn)
            fil_rec.load_contentstat(fil_out_f_stat)
            fil_rec.fill(cr.SHA256)
            if hash_in_the_name:
                fil_rec.rename_file()
            new_repomd.set_record(fil_rec)

        if oth_out_fn:
            oth_rec = cr.RepomdRecord("other", oth_out_fn)
            oth_rec.load_contentstat(oth_out_f_stat)
            oth_rec.fill(cr.SHA256)
            if hash_in_the_name:
                oth_rec.rename_file()
            new_repomd.set_record(oth_rec)

        # Write out repomd.xml
        deltarepoid = "TODO"  # TODO
        new_repomd.set_repoid(deltarepoid, self.id_type)
        new_repomd_path = os.path.join(new_repodata_path, "repomd.xml")
        new_repomd_xml = new_repomd.xml_dump()
        self._debug("Writing repomd.xml")
        open(new_repomd_path, "w").write(new_repomd_xml)

        # Final move
        final_destination = os.path.join(out_path, "repodata/")
        if os.path.exists(final_destination):
            self._warning("Destination dir already exists! Removing %s" % \
                          final_destination)
            shutil.rmtree(final_destination)
        self._info("Moving %s -> %s" % (new_path, final_destination))
        os.rename(new_path, final_destination)

    def gendelta(self, old_path, new_path, out_path=None,
                 do_only=None, skip=None):
        removedxml = RemovedXml()
        hash_in_the_name = False

        # Prepare variables with paths
        new_repodata_path = os.path.join(new_path, "repodata/")
        old_repodata_path = os.path.join(old_path, "repodata/")

        old_repomd_path = os.path.join(old_repodata_path, "repomd.xml")
        new_repomd_path = os.path.join(new_repodata_path, "repomd.xml")

        # Prepare Repomd objects
        old_repomd = cr.Repomd(old_repomd_path)
        new_repomd = cr.Repomd(new_repomd_path)
        delta_repomd = cr.Repomd()

        # Prepare output path
        delta_path = os.path.join(out_path, ".deltarepo/")
        delta_repodata_path = os.path.join(delta_path, "repodata/")
        os.mkdir(delta_path)
        os.mkdir(delta_repodata_path)

        # Do repomd delta
        delta_repomd.set_revision(new_repomd.revision)
        for tag in new_repomd.distro_tags:
            delta_repomd.add_distro_tag(tag[1], tag[0])
        for tag in new_repomd.repo_tags:
            delta_repomd.add_repo_tag(tag)
        for tag in new_repomd.content_tags:
            delta_repomd.add_content_tag(tag)

        old_records = dict([(record.type, record) for record in old_repomd.records ])
        new_records = dict([(record.type, record) for record in new_repomd.records ])
        old_record_types = set(old_records.keys())
        new_record_types = set(new_records.keys())
        deleted_repomd_record_types = old_record_types - new_record_types
        added_repomd_record_types = new_record_types - old_record_types

        # Do deltas for the "primary", "filelists" and "other"
        if not "primary" in old_records or not "primary" in new_records:
            raise DeltaRepoError("Missing primary metadata")

        if new_records["primary"].location_href.split("primary")[0] != "":
            hash_in_the_name = True

        pri_old_fn = os.path.join(old_path, old_records["primary"].location_href)
        pri_new_fn = os.path.join(new_path, new_records["primary"].location_href)
        pri_out_fn = os.path.join(delta_repodata_path, "primary.xml.gz")
        pri_out_f_stat = cr.ContentStat(cr.SHA256)
        pri_out_f = cr.PrimaryXmlFile(pri_out_fn, cr.GZ_COMPRESSION)

        fil_new_fn = None
        fil_out_fn = None
        fil_out_f_stat = None
        fil_out_f = None
        if ("filelists" in new_records):
            fil_new_fn = os.path.join(new_path, new_records["filelists"].location_href)
            fil_out_fn = os.path.join(delta_repodata_path, "filelists.xml.gz")
            fil_out_f_stat = cr.ContentStat(cr.SHA256)
            fil_out_f = cr.FilelistsXmlFile(fil_out_fn, cr.GZ_COMPRESSION)

        oth_new_fn = None
        out_out_fn = None
        oth_out_f_stat = None
        oth_out_f = None
        if ("other" in new_records):
            oth_new_fn = os.path.join(new_path, new_records["other"].location_href)
            oth_out_fn = os.path.join(delta_repodata_path, "other.xml.gz")
            oth_out_f_stat = cr.ContentStat(cr.SHA256)
            oth_out_f = cr.OtherXmlFile(oth_out_fn, cr.GZ_COMPRESSION)

        deltamodule = MainDeltaModule()
        ids = deltamodule.do(pri_old_fn, pri_new_fn, pri_out_f, fil_new_fn,
                             fil_out_f, oth_new_fn, oth_out_f, removedxml)

        # Prepare repomd.xml records
        pri_rec = cr.RepomdRecord("primary", pri_out_fn)
        pri_rec.load_contentstat(pri_out_f_stat)
        pri_rec.fill(cr.SHA256)
        if hash_in_the_name:
            pri_rec.rename_file()
        delta_repomd.set_record(pri_rec)

        if fil_out_fn:
            fil_rec = cr.RepomdRecord("filelists", fil_out_fn)
            fil_rec.load_contentstat(fil_out_f_stat)
            fil_rec.fill(cr.SHA256)
            if hash_in_the_name:
                fil_rec.rename_file()
            delta_repomd.set_record(fil_rec)

        if oth_out_fn:
            oth_rec = cr.RepomdRecord("other", oth_out_fn)
            oth_rec.load_contentstat(oth_out_f_stat)
            oth_rec.fill(cr.SHA256)
            if hash_in_the_name:
                oth_rec.rename_file()
            delta_repomd.set_record(oth_rec)

        # Write out removed.xml
        # TODO: Compression via compression wrapper
        removedxml_path = os.path.join(delta_repodata_path, "removed.xml")
        #removedxml_path_gz = os.path.join(delta_repodata_path, "removed.xml.gz")
        removedxml_xml = removedxml.xml_dump()
        self._debug("Writing removed.xml")
        open(removedxml_path, "w").write(removedxml_xml)
        stat = cr.ContentStat(cr.SHA256)
        #cr.compress_file(removedxml_path, removedxml_path_gz, cr.GZ, stat)
        #os.remove(removedxml_path)
        #removedxml_rec = cr.RepomdRecord("removed", removedxml_path_gz)
        removedxml_rec = cr.RepomdRecord("removed", removedxml_path)
        removedxml_rec.load_contentstat(stat)
        removedxml_rec.fill(cr.SHA256)
        if hash_in_the_name:
            removedxml_rec.rename_file()
        delta_repomd.set_record(removedxml_rec)

        # Write out repomd.xml
        deltarepoid = "%s-%s" % ids
        delta_repomd.set_repoid(deltarepoid, self.id_type)
        delta_repomd_path = os.path.join(delta_repodata_path, "repomd.xml")
        delta_repomd_xml = delta_repomd.xml_dump()
        self._debug("Writing repomd.xml")
        open(delta_repomd_path, "w").write(delta_repomd_xml)

        # Final move
        final_destination = os.path.join(out_path, "%s-%s" % ids)
        if os.path.exists(final_destination):
            self._warning("Destination dir already exists! Removing %s" % \
                          final_destination)
            shutil.rmtree(final_destination)
        self._info("Moving %s -> %s" % (delta_path, final_destination))
        os.rename(delta_path, final_destination)
