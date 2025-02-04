"""Command line script to generate meta data plots"""

import sys
import os
import time
import re
import traceback
import argparse

import numpy as np
import matplotlib.pyplot as plt

import hipercam as hcam
from hipercam import cline, utils
from hipercam.cline import Cline

__all__ = [
    "redplt",
]

##########################################################
#
# redplt -- generate standardised plots of reduce log data
#
##########################################################


def redplt(args=None):
    description = \
    """redplt

    This command is to be run in the "raw_data" directory containing
    night-by-night directories of data for |hipercam|, ULTRACAM or
    ULTRASPEC. It attempts to generate plots of any runs it finds with
    corresponding reduce logs files inside a sub-directory reduce and
    then stores these inside a sub-directory "meta". The purpose of
    these plots is so that they can be attached to the runs logs as a
    quick look on past runs.

    The code assumes that aperture 1 contains the target while
    aperture 2 has the best comparison. It produces plots in which the
    top panel shows the target divided by the comparison, and the
    bottom panel shows the comparison alone to give some sense of
    clouds.

    Runs with fewer than 20 points or lasting less than 10 minutes will
    not be plotted.

    """

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "-f",
        dest="full",
        action="store_true",
        help="carry out full re-computation of plots",
    )
    args = parser.parse_args()

    cwd = os.getcwd()
    if os.path.basename(cwd) != "raw_data":
        print("redplt must be run in a directory called 'raw_data'")
        print("redplt aborted", file=sys.stderr)
        return

    if cwd.find("ultracam") > -1:
        instrument = "ULTRACAM"
        itype = 'U'
        source = 'ul'
        cnams = ('1','2','3')
        cols = {'1' : "red", '2' : "green", '3' : "blue"}
    elif cwd.find("ultraspec") > -1:
        instrument = "ULTRASPEC"
        itype = 'U'
        source = 'ul'
        cnams = ('1',)
        cols = {'1' : "blue"}
    elif cwd.find("hipercam") > -1:
        instrument = "HiPERCAM"
        itype = 'H'
        source = 'hl'
        cnams = ('1','2','3','4','5')
        cols = {'1' : "blue", '2' : "green", '3' : "orange", '4' : "red", '5' : "mud"}
    else:
        print("cannot find either ultracam, ultraspec or hipercam in path")
        print("redplt aborted", file=sys.stderr)
        return

    linstrument = instrument.lower()

    # Now the actual work.  Next are regular expressions to match run
    # directories, nights, and run files
    nre = re.compile("^\d\d\d\d-\d\d-\d\d$")
    lre = re.compile("^run\d\d\d\\d?.log$")

    # Get list of night directories
    nnames = [
        nname
        for nname in os.listdir(".")
        if nre.match(nname)
        and os.path.isdir(nname)
        and os.path.exists(os.path.join(nname,'reduce'))
    ]
    nnames.sort()

    if len(nnames) == 0:
        print("no night directories found", file=sys.stderr)
        print("redplt aborted", file=sys.stderr)
        return

    for nname in nnames:

        print(f"Night {nname}")

        # reduce and meta directories
        rdir = os.path.join(nname,'reduce')
        mdir = os.path.join(nname,'meta')

        # load all the run names that can be found in reduce
        runs = [run[:-4] for run in os.listdir(rdir) if lre.match(run)]
        runs.sort()

        if len(runs) == 0:
            print(f' No run logs found in {rdir}; skipping')
            continue

        # ensure meta directory exists
        os.makedirs(mdir, exist_ok=True)

        # Minimum number of points / minutes to bother with
        NMIN, TMIN = 20, 10

        # Create plots, where possible.
        for run in runs:
            rlog = os.path.join(rdir, run + '.log')

            pname = os.path.join(mdir,run + '.png')
            if not args.full and os.path.exists(pname):
                print(f'  Plot {pname} exists and will not be re-computed')
                continue

            # OK attempt a plot
            try:

                hlog = hcam.hlog.Hlog.rascii(rlog)

                # Two panels, target / comparison and comparison
                fig,(ax1,ax2) = plt.subplots(2,1,sharex=True)

                cnams = sorted(list(hlog.keys()))
                apnames = hlog.apnames

                # use the next to work out optimal plot ranges
                tymin, tymax, cymin, cymax = 4*[None]
                for cnam in cnams:
                    if cnam in apnames:
                        apnams = apnames[cnam]
                        if '1' in apnams:
                            targ = hlog.tseries(cnam,'1')
                            if '2' in apnams:
                                comp = hlog.tseries(cnam,'2')

                                # run some checks
                                ts = targ.t[~targ.get_mask(hcam.BAD_TIME) & ~comp.get_mask(hcam.BAD_TIME)]
                                if len(ts) < NMIN:
                                    print(f'{run}, CCD={cnam} has too few points ({len(ts)} < {NMIN})')
                                    continue
                                tmins = 1440*(ts.max()-ts.min())
                                if tmins < TMIN:
                                    print(f'{run}, CCD={cnam} is too short ({tmins} < {TMIN} mins)')
                                    continue

                                targ /= comp

                                ndat = len(targ)
                                if ndat > 3000:
                                    # stop plotting too many points to keep
                                    # size down
                                    binsize = ndat // 1500
                                    targ.bin(binsize)
                                    comp.bin(binsize)

                                (_d,_d),(tylo,_d),(_d,tyhi) = targ.percentile([5,95],  bitmask=hcam.BAD_TIME)
                                (_d,_d),(cylo,_d),(_d,cyhi) = comp.percentile([5,95],  bitmask=hcam.BAD_TIME)
                                if tymax is not None:
                                    off = tymax - tylo
                                    targ += off
                                    tymax += tyhi-tylo
                                else:
                                    tymin, tymax = tylo, tyhi
                                if cymax is not None:
                                    off = cymax - cylo
                                    comp += off
                                    cymax += cyhi-cylo
                                else:
                                    cymin, cymax = cylo, cyhi

                                targ.mplot(ax1,utils.rgb(cols[cnam]),ecolor='0.5', bitmask=hcam.BAD_TIME)
                                comp.mplot(ax2,utils.rgb(cols[cnam]),ecolor='0.5',  bitmask=hcam.BAD_TIME)

                            else:
                                # run some checks
                                ts = targ.t[~targ.get_mask(hcam.BAD_TIME)]
                                if len(ts) < NMIN:
                                    print(f'{run}, CCD={cnam} has too few points ({len(ts)} < {NMIN})')
                                    continue
                                tmins = 1440*(ts.max()-ts.min())
                                if tmins < TMIN:
                                    print(f'{run}, CCD={cnam} is too short ({tmins} < {TMIN} mins)')
                                    continue

                                ndat = len(targ)
                                if ndat > 3000:
                                    # stop plotting too many points to keep
                                    # size down
                                    binsize = ndat // 1500
                                    targ.bin(binsize)

                                (_d,_d),(tylo,_d),(_d,tyhi) = targ.percentile([5,95],  bitmask=hcam.BAD_TIME)
                                if tymax is not None:
                                    off = tymax - tylo
                                    targ += off
                                    tymax += tyhi-tylo
                                else:
                                    tymin, tymax = tylo, tyhi
                                targ.mplot(ax1,utils.rgb(cols[cnam]),ecolor='0.5',  bitmask=hcam.BAD_TIME)

                if tymin is not None:
                    yrange = tymax-tymin
                    ax1.set_ylim(tymin-yrange/4, tymax+yrange/4)
                    if cymin is not None:
                        yrange = cymax-cymin
                        ax2.set_ylim(cymin-yrange/4, cymax+yrange/4)
                    ax1.set_ylabel('Target / Comparison')
                    ax1.set_title(f'{nname}, {run}')
                    ax2.set_ylabel('Comparison')
                    ax2.set_xlabel('Time [MJD]')
                    plt.savefig(pname)
                    print(f'Written {pname}')
                plt.close()

            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_tb(
                    exc_traceback, limit=1, file=sys.stderr
                )
                traceback.print_exc(file=sys.stderr)
                print("Problem reading log for run =", run)
