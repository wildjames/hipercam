import sys
import os
import time
from signal import signal, SIGINT
import requests
import socket
from numba import jit

import numpy as np

import matplotlib.pylab as plt
from matplotlib.patches import Circle

from astropy.time import Time

import hipercam as hcam
from hipercam import cline, utils, spooler, defect, fringe, mpl
from hipercam.cline import Cline
from hipercam.mpl import Params

# colour for setup windows. works for me at least
# but may need input from Stu
COL_SETUP = (0.8, 0., 0.)

__all__ = [
    "ncal",
]

######################################
#
# ncal -- noise calibration
#
######################################

def ncal(args=None):
    """``ncal [source] (run first last [twait tmax] | flist) trim ([ncol
    nrow]) (ccd) bias dark flat xybox read gain grain``

    Calibrates noise characteristics of CCDs by plotting estimator
    of RMS vs signal level from a series of frames. The estimate
    is the mean of the absolute difference between each pixel
    and the mean of its 8 near-neighbours. This is very local and
    fairly robust. Assuming gaussian noise, the RMS is sqrt(4*Pi/9)
    times this value, and this is what is plotted as the RMS by this
    routine. `ncal` is best to applied to a series of frames with
    a large dynamic range, ideally starting from bias-like frames
    to well exposed sky flats. A long flat-field run going to low
    levels, or a run into twilight at the end of the night could be
    good places to start.

    Parameters:

        source : str [hidden]
           Data source, five options:

             |  'hs' : HiPERCAM server
             |  'hl' : local HiPERCAM FITS file
             |  'us' : ULTRACAM server
             |  'ul' : local ULTRACAM .xml/.dat files
             |  'hf' : list of HiPERCAM hcm FITS-format files

           'hf' is used to look at sets of frames generated by 'grab'
           or converted from foreign data formats. The standard
           start-off default for ``source`` can be set using the
           environment variable HIPERCAM_DEFAULT_SOURCE. e.g. in bash
           :code:`export HIPERCAM_DEFAULT_SOURCE="us"` would ensure it
           always started with the ULTRACAM server by default. If
           unspecified, it defaults to 'hl'.

        run : str [if source ends 's' or 'l']
           run number to access, e.g. 'run034'

        flist : str [if source ends 'f']
           name of file list

        first : int [if source ends 's' or 'l']
           exposure number to start from. 1 = first frame; set = 0 to always
           try to get the most recent frame (if it has changed).  For data
           from the |hiper| server, a negative number tries to get a frame not
           quite at the end.  i.e. -10 will try to get 10 from the last
           frame. This is mainly to sidestep a difficult bug with the
           acquisition system.

        last : int [if source ends 's' or 'l']
           Last frame to access, 0 for the lot

        twait : float [if source ends 's' or 'l'; hidden]
           time to wait between attempts to find a new exposure, seconds.

        tmax : float [if source ends 's' or 'l'; hidden]
           maximum time to wait between attempts to find a new exposure,
           seconds.

        trim : bool [if source starts with 'u']
           True to trim columns and/or rows off the edges of windows nearest
           the readout which can sometimes contain bad data.

        ncol : int [if trim, hidden]
           Number of columns to remove (on left of left-hand window, and right
           of right-hand windows)

        nrow : int [if trim, hidden]
           Number of rows to remove (bottom of windows)

        ccd : str
           The CCD to analyse.

        bias : str
           Name of bias frame to subtract, 'none' to ignore.

        dark : str
           Name of dark frame to subtract, 'none' to ignore

        flat : str
           Name of flat field to divide by, 'none' to ignore. Should normally
           only be used in conjunction with a bias, although it does allow you
           to specify a flat even if you haven't specified a bias.

        xybox : int
           the stats will be taken over boxes of xybox-squared pixels
           to keep the number of points and scatter under control.

        read : float
           readout noise, RMS ADU, for overplotting a model

        gain : float
           gain, e-/count, for overploting a model

        grain : float
           fractional RMS variation due to flat-field variations,
           if you didn't include a flat field.

    """

    command, args = utils.script_args(args)

    # get the inputs
    with Cline("HIPERCAM_ENV", ".hipercam", command, args) as cl:

        # register parameters
        cl.register("source", Cline.GLOBAL, Cline.HIDE)
        cl.register("run", Cline.GLOBAL, Cline.PROMPT)
        cl.register("first", Cline.LOCAL, Cline.PROMPT)
        cl.register("last", Cline.LOCAL, Cline.PROMPT)
        cl.register("trim", Cline.GLOBAL, Cline.PROMPT)
        cl.register("ncol", Cline.GLOBAL, Cline.HIDE)
        cl.register("nrow", Cline.GLOBAL, Cline.HIDE)
        cl.register("twait", Cline.LOCAL, Cline.HIDE)
        cl.register("tmax", Cline.LOCAL, Cline.HIDE)
        cl.register("flist", Cline.LOCAL, Cline.PROMPT)
        cl.register("ccd", Cline.LOCAL, Cline.PROMPT)
        cl.register("bias", Cline.GLOBAL, Cline.PROMPT)
        cl.register("dark", Cline.GLOBAL, Cline.PROMPT)
        cl.register("flat", Cline.GLOBAL, Cline.PROMPT)
        cl.register("xybox", Cline.LOCAL, Cline.PROMPT)
        cl.register("read", Cline.LOCAL, Cline.PROMPT)
        cl.register("gain", Cline.LOCAL, Cline.PROMPT)
        cl.register("grain", Cline.LOCAL, Cline.PROMPT)

        # get inputs
        default_source = os.environ.get('HIPERCAM_DEFAULT_SOURCE','hl')
        source = cl.get_value(
            "source",
            "data source [hs, hl, us, ul, hf]",
            default_source,
            lvals=("hs", "hl", "us", "ul", "hf"),
        )

        # set some flags
        server_or_local = source.endswith("s") or source.endswith("l")

        if server_or_local:
            resource = cl.get_value("run", "run name", "run005")
            if source == "hs":
                first = cl.get_value("first", "first frame to plot", 1)
            else:
                first = cl.get_value("first", "first frame to plot", 1, 0)
            last = cl.get_value("last", "last frame to grab", 0)
            if last < first and last != 0:
                sys.stderr.write("last must be >= first or 0")
                sys.exit(1)

            twait = cl.get_value(
                "twait", "time to wait for a new frame [secs]", 1.0, 0.0
            )
            tmax = cl.get_value(
                "tmax", "maximum time to wait for a new frame [secs]", 10.0, 0.0
            )

        else:
            resource = cl.get_value(
                "flist", "file list", cline.Fname("files.lis", hcam.LIST)
            )
            first = 1

        trim = cl.get_value("trim", "do you want to trim edges of windows?", True)
        if trim:
            ncol = cl.get_value("ncol", "number of columns to trim from windows", 0)
            nrow = cl.get_value("nrow", "number of rows to trim from windows", 0)
        else:
            ncol, nrow = None, None

        # define the panel grid. first get the labels and maximum dimensions
        ccdinf = spooler.get_ccd_pars(source, resource)

        if len(ccdinf) > 1:
            cnam = cl.get_value(
                "ccd", "CCD to analyse", "1", lvals=list(ccdinf.keys())
            )
        else:
            cnam = ccdinf.keys()[0]

        # bias frame (if any)
        bias = cl.get_value(
            "bias",
            "bias frame ['none' to ignore]",
            cline.Fname("bias", hcam.HCAM),
            ignore="none",
        )
        if bias is not None:
            # read the bias frame
            bias = hcam.MCCD.read(bias)
            fprompt = "flat frame ['none' to ignore]"
        else:
            fprompt = "flat frame ['none' is normal choice with no bias]"

        # dark (if any)
        dark = cl.get_value(
            "dark", "dark frame to subtract ['none' to ignore]",
            cline.Fname("dark", hcam.HCAM), ignore="none"
        )
        if dark is not None:
            # read the dark frame
            dark = hcam.MCCD.read(dark)

        # flat (if any)
        flat = cl.get_value(
            "flat", fprompt, cline.Fname("flat", hcam.HCAM), ignore="none"
        )
        if flat is not None:
            # read the flat frame
            flat = hcam.MCCD.read(flat)

        xybox = cl.get_value(
            "xybox",
            "box size for averaging results [binned pixels]", 11, 1
        )
        read = cl.get_value("read", "readout noise, RMS ADU", 4.0, 0.0)
        gain = cl.get_value("gain", "gain, ADU/e-", 1.0, 0.001)
        grain = cl.get_value("grain", "flat field graininess", 0.01, 0.)

    ######################################

    # Phew. We finally have all the inputs

    # Now on with the analysis
    total_time, nframe = 0, 0
    with spooler.data_source(source, resource, first, full=False) as spool:

        for mccd in spool:

            if server_or_local:
                # Handle the waiting game ... some awkward stuff
                # involving updating on a cycle faster than twait to
                # make the plots more responsive, if twait is long.
                give_up, try_again, total_time = spooler.hang_about(
                    mccd, twait, tmax, total_time
                )

                if give_up:
                    print("ncal stopped")
                    break
                elif try_again:
                    continue

            # Trim the frames: ULTRACAM windowed data has bad columns
            # and rows on the sides of windows closest to the readout
            # which can badly affect reduction. This option strips
            # them.
            if trim:
                hcam.ccd.trim_ultracam(mccd, ncol, nrow)

            # indicate progress
            tstamp = Time(mccd.head["TIMSTAMP"], format="isot", precision=3)
            nfrm = mccd.head.get("NFRAME",nframe+1)
            print(
                f'{nfrm}, utc= {tstamp.iso} ({"ok" if mccd.head.get("GOODTIME", True) else "nok"}), '
            )

            if nframe == 0:

                # get the bias, dark, flat
                # into shape first time through

                if bias is not None:
                    # crop the bias on the first frame only
                    bias = bias.crop(mccd)
                    bexpose = bias.head.get("EXPTIME", 0.0)
                else:
                    bexpose = 0.

                if dark is not None:
                    # crop the dark on the first frame only
                    dark = dark.crop(mccd)

                if flat is not None:
                    # crop the flat on the first frame only
                    flat = flat.crop(mccd)

            # extract the CCD of interest
            ccd = mccd[cnam]

            if ccd.is_data():
                # "is_data" indicates genuine data as opposed to junk
                # that results from nskip > 0.

                # subtract the bias
                if bias is not None:
                    ccd -= bias[cnam]

                # subtract the dark
                if dark is not None:
                    dexpose = dark.head["EXPTIME"]
                    cexpose = ccd.head["EXPTIME"]
                    scale = (cexpose - bexpose) / dexpose
                    ccd -= scale * dark[cnam]

                # divide out the flat
                if flat is not None:
                    ccd /= flat[cnam]

                # at this point we have the data in the right state to
                # start processing.

                for wind in ccd.values():
                    data = wind.data
                    ny,nx = data.shape
                    if nx-2 >= xybox and ny-2 >= xybox:
                        means, stds = procdata(wind.data, xybox)
                        plt.loglog(means, stds, ',b')

            # update the frame number
            nframe += 1
            if server_or_local and last and nframe > last:
                break

    count = 10**np.linspace(0,5,200)
    sigma = np.sqrt(read**2 + count / gain + (grain*count)**2 )
    plt.plot(count,sigma,'r',lw=2)

    plt.xlim(1,100000)
    plt.ylim(1,1000)
    plt.xlabel('Mean count level')
    plt.ylabel('RMS [counts]')
    plt.title(f'RMS vs level, CCD {cnam}')
    plt.show()

@jit(nopython=True, cache=True)
def procdata(data, xybox):
    """Given a numpy array and a box size returns two arrays of mean vs
    standard deviation for all the boxes. The standard deviation is
    estimated using a robust technique involving the absolute
    difference of each pixel from the 8 surrounding pixels.  Only
    pixels more than 1 in from the edge are processed as a result.

    Very loopy this routine, hence the "numba" directive
    """

    ny,nx = data.shape
    xlo,xhi = 1,nx-1
    ylo,yhi = 1,ny-1

    nxbox = (xhi-xlo) // xybox
    nybox = (yhi-ylo) // xybox

    nbox = nxbox*nybox
    means = np.empty((nbox))
    stds = np.empty((nbox))
    ibox = 0
    for iybox in range(nybox):
        for ixbox in range(nxbox):
            # next two lines loop over all pixels in the box
            sumv, sumd = 0., 0.
            for iy in range(ylo+xybox*iybox,ylo+xybox*(iybox+1)):
                for ix in range(xlo+xybox*ixbox,xlo+xybox*(ixbox+1)):
                    # need mean of surrounding 8 pixels
                    mean8 = (data[iy-1:iy+2,ix-1:ix+2].sum() - data[iy,ix])/8
                    sumv += data[iy,ix]
                    sumd += abs(data[iy,ix]-mean8)
            means[ibox] = sumv/xybox**2
            stds[ibox] = sumd/xybox**2
            ibox += 1
    stds *= np.sqrt(4*np.pi/9.)
    return (means, stds)
