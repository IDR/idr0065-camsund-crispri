#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Generate companion files for experimentA of the idr0065 study. This script
# assumes the following layout for the original data:
#
#  <microscopic_slide>/        All data associated with a microscopic slide
#    pheno/                    Phenotypic acquisition
#      metadata.txt            Metadata for the phenotyping acquisition
#      Pos101/                 Position on a microscopyic slide
#        fluor/                Fluorescence timelapse images
#        phase/                Phase timelapse images
#    geno/                     Genotypic acqusition
#      Pos101/                 Position on the microscopyic slide
#        1_cy5_fluor/          Fluorescence acquisition (11 cycles)
#        2_cy3_fluor/          Fluorescence acquisition (11 cycles)
#        3_TxR_fluor/          Fluorescence acquisition (11 cycles)
#        4_fam_flour/          Fluorescence acquisition (11 cycles)
#        phase/                Phase acquisition (11 cycles)

import argparse
import logging

from ome_model.experimental import Image, create_companion
import os
from os.path import join, dirname
import subprocess

BASE_DIRECTORY = "/uod/idr/filesets/idr0065-camsund-crispri/"
TIMESTAMPS_FILE = join(BASE_DIRECTORY, "20190823-ftp", "acq_time.txt")
DATA_DIRECTORY = join(BASE_DIRECTORY, "20190930-ftp")
MAPPINGS_FILE = join(BASE_DIRECTORY, "20190823-ftp", "fluor_phase_link.txt")
EXPERIMENTA_DIRECTORY = "/uod/idr/metadata/idr0065-camsund-crispri/experimentA"
EXPERIMENTB_DIRECTORY = "/uod/idr/metadata/idr0065-camsund-crispri/experimentB"


def read_phenotypic_time_indexes():
    time_indexes = {}
    with open(MAPPINGS_FILE, 'r') as f:
        for line in f.readlines():
            a = line.split(' ')
            time_indexes[a[0]] = int(a[1].rstrip()[-8:-5])
    return time_indexes


def read_phenotypic_timestamps():
    timestamps = {}
    with open(TIMESTAMPS_FILE, 'r') as f:
        for line in f.readlines():
            a = line.split(' ')
            timestamps[a[0]] = float(a[1].rstrip())
    return timestamps


def parse_phenotypic_filenames(timestamps):
    """Parse filenames of timelapse phenotypic data"""

    files = {}
    slides = {}
    for filename in timestamps:
        slide = filename.split('/')[0]
        position = filename.split('/')[2]
        files.setdefault(slide, {})
        slides.setdefault(slide, set())
        files[slide].setdefault(position, [])
        files[slide][position].append(filename)
        slides[slide].add(position)

    # Validation
    for slide in files:
        assert len(files[slide]) == 90  # 90 positions per slide
        for x in range(101, 146):
            assert "Pos%s" % x in files[slide]
        for x in range(201, 246):
            assert "Pos%s" % x in files[slide]
        for p in files[slide]:
            for t in range(481):
                filename = get_phenotypic_filename(p, "phase", t, slide=slide)
                assert filename in files[slide][p]
            for t in range(241):
                filename = get_phenotypic_filename(p, "fluor", t, slide=slide)
                assert filename in files[slide][p]
    return slides


def get_phenotypic_filename(p, c, t, slide=None):
    name = "%s/%s/img_000000%03g.tiff" % (p, c, t)
    if slide is not None:
        return "%s/pheno/%s" % (slide, name)
    else:
        return name


def get_genotypic_filename(p, c, t):
    return "%s/%s/%02g.tiff" % (p, c, t)


def write_companion(images, file_path):
    # Generate companion OME-XML file
    if not os.path.exists(dirname(file_path)):
        os.makedirs(dirname(file_path))
        logging.info("Created %s" % dirname(file_path))
    create_companion(images=images, out=file_path)

    # Indent XML for readability
    proc = subprocess.Popen(
        ['xmllint', '--format', '-o', file_path, file_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE)
    (output, error_output) = proc.communicate()
    logging.info("Created %s" % file_path)


def create_phenotypic_companions():
    """Phenotypic metadata files"""

    logging.info("Generating phenotypic metadata files")
    time_indexes = read_phenotypic_time_indexes()
    timestamps = read_phenotypic_timestamps()
    slides = parse_phenotypic_filenames(timestamps)
    filePaths = []

    for slide in slides:
        images = []
        logging.debug("Processing phenotypic %s" % slide)
        # Genotypic metadata generation
        for position in sorted(slides[slide]):
            logging.debug("  Creating image for %s" % position)
            image = Image(
                position, 2048, 879, 1, 2, 481, order="XYZCT", type="uint16")
            image.add_channel("Phase", -1)
            image.add_channel("Fluorescence", 16711935)

            # Phase images
            for t in range(481):
                relative_path = get_phenotypic_filename(position, "phase", t)
                full_path = get_phenotypic_filename(position, "phase", t,
                                                    slide=slide)
                image.add_tiff(relative_path, c=0, z=0, t=t, planeCount=1)
                plane_options = {
                    "DeltaT": timestamps[full_path],
                    "DeltaTUnit": "s",
                    "ExposureTime": "20",
                    "ExposureTimeUnit": "ms",
                }
                image.add_plane(c=0, z=0, t=t, options=plane_options)

            # Fluorescence images
            for i in range(241):
                relative_path = get_phenotypic_filename(position, "fluor", i)
                full_path = get_phenotypic_filename(position, "fluor", i,
                                                    slide=slide)
                t = time_indexes[full_path]
                plane_options = {
                    "DeltaT": timestamps[full_path],
                    "DeltaTUnit": "s",
                    "ExposureTime": "300",
                    "ExposureTimeUnit": "ms",
                }
                if t == 2 * i:
                    image.add_tiff(relative_path, c=1, z=0, t=t, planeCount=1)
                    if i != 240:
                        image.add_tiff(None, c=1, z=0, t=(2 * i) + 1)
                elif t == (2 * i) + 1:
                    image.add_tiff(None, c=1, z=0, t=2 * i)
                    if t != 481:
                        image.add_tiff(relative_path, c=1, z=0, t=t,
                                       planeCount=1)
                else:
                    raise Exception("Invalid mapping")
                image.add_plane(c=1, z=0, t=t, options=plane_options)
            images.append(image)

            position_dir = join(EXPERIMENTA_DIRECTORY, 'companions', slide,
                                "pheno", position)
            if not os.path.lexists(position_dir):
                os.symlink(join(DATA_DIRECTORY, slide, "pheno", position),
                           position_dir)

        companion_file = join(
            EXPERIMENTA_DIRECTORY, 'companions', slide, "pheno",
            slide + '.companion.ome')
        write_companion(images, companion_file)

        filePaths.append(
            "Project:name:idr0065-camsund-crispri/experimentA/"
            "Dataset:name:%s\t"
            "%s\t%s\n" % (slide, companion_file, slide))

    tsv = join(EXPERIMENTA_DIRECTORY, 'idr0065-experimentA-filePaths.tsv')
    with open(tsv, 'w') as f:
        for p in filePaths:
            f.write(p)
    return slides


def create_genotypic_companions(slides):
    GENO_CYCLES = 11

    logging.info("Generating genotypic metadata files")
    filePaths = []
    for slide in slides:
        for i in range(GENO_CYCLES):
            images = []
            index = i + 1
            logging.debug("Processing %s" % slide)
            # Genotypic metadata generation
            for position in sorted(slides[slide]):
                logging.debug("  Creating image for %s" % position)
                image = Image(
                    position, 2048, 879, 1, 5, 1,
                    order="XYZCT", type="uint16")

                image.add_channel("Cy5", -16776961)
                image.add_channel("Cy3", 16711935)
                image.add_channel("TxR", 65535)
                image.add_channel("Fam", -65281)
                image.add_channel("Phase", -1)

                image.add_tiff(
                    get_genotypic_filename(position, "1_cy5_fluor", index),
                    c=0, z=0, t=0)
                image.add_tiff(
                    get_genotypic_filename(position, "2_cy3_fluor", index),
                    c=1, z=0, t=0)
                image.add_tiff(
                    get_genotypic_filename(position, "3_TxR_fluor", index),
                    c=2, z=0, t=0)
                image.add_tiff(
                    get_genotypic_filename(position, "4_fam_flour", index),
                    c=3, z=0, t=0)
                image.add_tiff(
                    get_genotypic_filename(position, "phase", index),
                    c=4, z=0, t=0)
                images.append(image)

                position_dir = join(EXPERIMENTB_DIRECTORY, 'companions', slide,
                                    'geno', position)
                if not os.path.lexists(position_dir):
                    os.symlink(join(DATA_DIRECTORY, slide, "geno", position),
                               position_dir)

            companion_file = join(
                EXPERIMENTB_DIRECTORY, 'companions', slide, "geno",
                '%s_round-%02g.companion.ome' % (slide, index))
            write_companion(images, companion_file)

            filePaths.append(
                "Project:name:idr0065-camsund-crispri/experimentB/"
                "Dataset:name:%s_round-%02g\t"
                "%s\t%s\n" % (slide, index, companion_file, slide))

    tsv = join(EXPERIMENTB_DIRECTORY, 'idr0065-experimentB-filePaths.tsv')
    with open(tsv, 'w') as f:
        for p in filePaths:
            f.write(p)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='count', default=0)
    args = parser.parse_args()

    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(len(levels)-1, args.verbose)]
    logger = logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)s %(message)s")

    slides = create_phenotypic_companions()
    create_genotypic_companions(slides)
