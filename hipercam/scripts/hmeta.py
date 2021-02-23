"""Command line script to generate meta data"""

import sys
import os
import time
import tempfile
import getpass

import numpy as np

import hipercam as hcam
from hipercam import cline, utils, spooler
from hipercam.cline import Cline

__all__ = [
    "hmeta",
]

#############################
#
# hmeta -- generate meta data
#
#############################


def mstats(args=None):
    """hmeta

    This command is to be run in the "raw_data" directory containg
    night-by-night directories of data. It attempts to generate
    statistical data on any run data it can find and write this
    to a file in a sub-directory called meta. These data can be picked
    up by logging scripts.

    """

    cwd = os.getcwd()
    if os.path.basename(cwd) != "raw_data":
        print("** hmeta must be run in a directory called 'raw_data'")
        print("hmeta aborted", file=sys.stderr)
        return

    if cwd.find("ultracam") > -1:
        instrument = "ULTRACAM"
        itype = 'U'
        source = 'ul'
    elif cwd.find("ultraspec") > -1:
        instrument = "ULTRASPEC"
        itype = 'U'
        source = 'ul'
    elif cwd.find("hipercam") > -1:
        instrument = "HiPERCAM"
        itype = 'H'
        source = 'hl'
    else:
        print("** hmeta: cannot find either ultracam, ultraspec or hipercam in path")
        print("hmeta aborted", file=sys.stderr)
        return

    linstrument = instrument.lower()

    # Now the actual work.  Next are regular expressions to match run
    # directories, nights, and run files
    nre = re.compile("^\d\d\d\d-\d\d-\d\d$")
    ure = re.compile("^run\d\d\d\.xml$")
    hre = re.compile("^run\d\d\d\d\.fits$")

    # Get list of night directories
    nnames = [
        nname
        for nname in os.listdir(".")
        if nre.match(rname)
        and os.path.isdir(nname)
    ]
    nnames.sort()

    if len(nnames) == 0:
        print(
            "no night directories found"
            file=sys.stderr,
        )
        print("hmeta aborted", file=sys.stderr)
        return


    for nname in nnames:

        print(f"  night {nname}")

        # create directory for any meta info such as the times
        meta = os.path.join(nname, 'meta')
        os.makedirs(meta, exist_ok=True)

        # name of stats file
        stats = os.path.join(meta, 'statistcs')
        if os.path.exists(stats):
            # if file already present, don't attempt to re-compute
            continue

        with open(stats, "w") as fstats:

            # load all the run names
            if itype == 'U':
                runs = [run[:-4] for run in os.listdir(night) if ure.match(run)]
            else:
                runs = [run[:-5] for run in os.listdir(night) if hre.match(run)]
            runs.sort()

            for run in runs:
                dfile = os.path.join(night, run)

                with spooler.data_source(source, dfile, first) as spool:

            stats.write(
                """#
# This file was generated by mstats running on file {run}
#
# The columns are:
#
# nframe ccd window minimum maximum mean median rms
#
# where ccd and window are string labels, nframe is the frame
# number an an integer, while the rest are floats.
#
""".format(
                    run=resource
                )
            )

            for mccd in spool:

                # Handle the waiting game ...
                give_up, try_again, total_time = spooler.hang_about(
                    mccd, twait, tmax, total_time
                )

                if give_up:
                    print("mstats stopped")
                    break
                elif try_again:
                    continue

                if bias is not None:
                    # read bias after first frame so we can
                    # chop the format
                    if bframe is None:

                        # read the bias frame
                        bframe = hcam.MCCD.read(bias)

                        # reformat
                        bframe = bframe.crop(mccd)

                    mccd -= bframe

                for cnam, ccd in mccd.items():
                    for wnam, wind in ccd.items():
                        stats.write(
                            (
                                "{1:5d}   {2:5s} {3:5s} {4:{0:s}} {5:{0:s}}"
                                " {6:{0:s}} {7:{0:s}} {8:{0:s}}\n"
                            ).format(
                                form,
                                nframe,
                                cnam,
                                wnam,
                                wind.min(),
                                wind.max(),
                                wind.mean(),
                                wind.median(),
                                wind.std(),
                            )
                        )

                # flush the output
                stats.flush()

                # progress info
                print("Written stats of frame {:d} to {:s}".format(nframe, outfile))

                # update the frame number
                nframe += 1
                if last and nframe > last:
                    break
