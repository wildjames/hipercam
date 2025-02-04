import sys
import os
import time

import numpy as np
from astropy.time import Time

from trm.pgplot import *
import hipercam as hcam
from hipercam import cline, utils, spooler, defect
from hipercam.cline import Cline
import requests
import socket

__all__ = [
    "rtplot",
]

######################################
#
# rtplot -- display of multiple images
#
######################################


def rtplot(args=None):
    """``rtplot [source device width height] (run first [twait tmax] |
    flist) trim ([ncol nrow]) (ccd (nx)) [pause plotall] bias
    [lowlevel highlevel] flat defect setup [drurl] msub iset (ilo ihi
    | plo phi) xlo xhi ylo yhi (profit [fdevice fwidth fheight method
    beta fwhm fwhm_min shbox smooth splot fhbox hmin read gain
    thresh])``

    Plots a sequence of images as a movie in near 'real time', hence
    'rt'. Designed to be used to look at images coming in while at the
    telescope, 'rtplot' comes with many options, a large number of
    which are hidden by default, and many of which are only prompted
    if other arguments are set correctly. If you want to see them all,
    invoke as 'rtplot prompt'.  This is worth doing once to know
    rtplot's capabilities.

    rtplot can source data from both the ULTRACAM and HiPERCAM
    servers, from local 'raw' ULTRACAM and HiPERCAM files (i.e. .xml +
    .dat for ULTRACAM, 3D FITS files for HiPERCAM) and from lists of
    HiPERCAM '.hcm' files.

    rtplot optionally allows the selection of targets to be fitted
    with gaussian or moffat profiles, and, if successful, will plot
    circles of 2x the measured FWHM in green over the selected
    targets. This option only works if a single CCD is being plotted.

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

        device : str [hidden]
          Plot device. PGPLOT is used so this should be a PGPLOT-style name,
          e.g. '/xs', '1/xs' etc. At the moment only ones ending /xs are
          supported.

        width : float [hidden]
           plot width (inches). Set = 0 to let the program choose.

        height : float [hidden]
           plot height (inches). Set = 0 to let the program choose. BOTH width
           AND height must be non-zero to have any effect

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
           CCD(s) to plot, '0' for all, '1 3' to plot '1' and '3' only, etc.

        nx : int [if more than 1 CCD]
           number of panels across to display.

        pause : float [hidden]
           seconds to pause between frames (defaults to 0)

        plotall : bool [hidden]
           plot all frames regardless of status (i.e. including blank frames
           when nskips are enabled (defaults to False). The profile fitting
           will still be disabled for bad frames.

        bias : str
           Name of bias frame to subtract, 'none' to ignore.

        lowlevel : float [hidden]
           Level below which a warning about low bias levels is warned. Set=0
           to ignore. Applied to first window of first CCD. 2000 about
           right for ULTRACAM.

        highlevel : float [hidden]
           Level above which a warning about high bias levels is warned. Set=0
           to ignore. Applied to first window of first CCD. 3500 about
           right for ULTRACAM.

        flat : str
           Name of flat field to divide by, 'none' to ignore. Should normally
           only be used in conjunction with a bias, although it does allow you
           to specify a flat even if you haven't specified a bias.

        defect : str
           Name of defect file, 'none' to ignore.

        setup : bool
           True/yes to access the current windows from hdriver. Useful
           during observing when seeting up windows, but not normally
           otherwise. Next argument (hidden) is the URL to get to
           hdriver. Once setup, you should probably turn this off to
           avoid overloading hdriver, especially if in drift mode as
           it makes a request for the windows for every frame.

        drurl : str [if setup; hidden]
           URL needed to access window setting from the camera
           driver (ultracam, ultraspec, hipercam). The internal server 
           in the camera driver must be switched on which can be done
           from the GUI.

        msub : bool
           subtract the median from each window before scaling for the
           image display or not. This happens after any bias subtraction.

        iset : str [single character]
           determines how the intensities are determined. There are three
           options: 'a' for automatic simply scales from the minimum to the
           maximum value found on a per CCD basis. 'd' for direct just takes
           two numbers from the user. 'p' for percentile dtermines levels
           based upon percentiles determined from the entire CCD on a per CCD
           basis.

        ilo : float [if iset='d']
           lower intensity level

        ihi : float [if iset='d']
           upper intensity level

        plo : float [if iset='p']
           lower percentile level

        phi : float [if iset='p']
           upper percentile level

        xlo : float
           left-hand X-limit for plot

        xhi : float
           right-hand X-limit for plot (can actually be < xlo)

        ylo : float
           lower Y-limit for plot

        yhi : float
           upper Y-limit for plot (can be < ylo)

        profit : bool [if plotting a single CCD only]
           carry out profile fits or not. If you say yes, then on the first
           plot, you will have the option to pick objects with a cursor. The
           program will then attempt to track these from frame to frame, and
           fit their profile. You may need to adjust 'first' to see anything.
           The parameters used for profile fits are hidden and you may want to
           invoke the command with 'prompt' the first time you try profile
           fitting.

        fdevice : str [if profit; hidden]
           plot device for profile fits, PGPLOT-style name.
           e.g. '/xs', '2/xs' etc.

        fwidth : float [if profit; hidden]
           fit plot width (inches). Set = 0 to let the program choose.

        fheight : float [if profit; hidden]
           fit plot height (inches). Set = 0 to let the program choose.
           BOTH fwidth AND fheight must be non-zero to have any effect

        method : str [if profit; hidden]
           this defines the profile fitting method, either a gaussian or a
           moffat profile. The latter is usually best.

        beta : float [if profit and method == 'm'; hidden]
           default Moffat exponent

        fwhm : float [if profit; hidden]
           default FWHM, unbinned pixels.

        fwhm_min : float [if profit; hidden]
           minimum FWHM to allow, unbinned pixels.

        shbox : float [if profit; hidden]
           half width of box for searching for a star, unbinned pixels. The
           brightest target in a region +/- shbox around an intial position
           will be found. 'shbox' should be large enough to allow for likely
           changes in position from frame to frame, but try to keep it as
           small as you can to avoid jumping to different targets and to
           reduce the chances of interference by cosmic rays.

        smooth : float [if profit; hidden]
           FWHM for gaussian smoothing, binned pixels. The initial position
           for fitting is determined by finding the maximum flux in a smoothed
           version of the image in a box of width +/- shbox around the starter
           position. Typically should be comparable to the stellar width. Its
           main purpose is to combat cosmi rays which tend only to occupy a
           single pixel.

        splot : bool [if profit; hidden]
           Controls whether an outline of the search box and a target number
           is plotted (in red) or not.

        fhbox : float [if profit; hidden]
           half width of box for profile fit, unbinned pixels. The fit box is
           centred on the position located by the initial search. It should
           normally be > ~2x the expected FWHM.

        hmin : float [if profit; hidden]
           height threshold to accept a fit. If the height is below this
           value, the position will not be updated. This is to help in cloudy
           conditions.

        read : float [if profit; hidden]
           readout noise, RMS ADU, for assigning uncertainties

        gain : float [if profit; hidden]
           gain, ADU/count, for assigning uncertainties

        thresh : float [if profit; hidden]
           sigma rejection threshold for fits

    """

    command, args = utils.script_args(args)

    # get the inputs
    with Cline("HIPERCAM_ENV", ".hipercam", command, args) as cl:

        # register parameters
        cl.register("source", Cline.GLOBAL, Cline.HIDE)
        cl.register("device", Cline.LOCAL, Cline.HIDE)
        cl.register("width", Cline.LOCAL, Cline.HIDE)
        cl.register("height", Cline.LOCAL, Cline.HIDE)
        cl.register("run", Cline.GLOBAL, Cline.PROMPT)
        cl.register("first", Cline.LOCAL, Cline.PROMPT)
        cl.register("trim", Cline.GLOBAL, Cline.PROMPT)
        cl.register("ncol", Cline.GLOBAL, Cline.HIDE)
        cl.register("nrow", Cline.GLOBAL, Cline.HIDE)
        cl.register("twait", Cline.LOCAL, Cline.HIDE)
        cl.register("tmax", Cline.LOCAL, Cline.HIDE)
        cl.register("flist", Cline.LOCAL, Cline.PROMPT)
        cl.register("ccd", Cline.LOCAL, Cline.PROMPT)
        cl.register("nx", Cline.LOCAL, Cline.PROMPT)
        cl.register("pause", Cline.LOCAL, Cline.HIDE)
        cl.register("plotall", Cline.LOCAL, Cline.HIDE)
        cl.register("bias", Cline.GLOBAL, Cline.PROMPT)
        cl.register("lowlevel", Cline.GLOBAL, Cline.HIDE)
        cl.register("highlevel", Cline.GLOBAL, Cline.HIDE)
        cl.register("flat", Cline.GLOBAL, Cline.PROMPT)
        cl.register("defect", Cline.GLOBAL, Cline.PROMPT)
        cl.register("setup", Cline.GLOBAL, Cline.PROMPT)
        cl.register("drurl", Cline.GLOBAL, Cline.HIDE)
        cl.register("msub", Cline.GLOBAL, Cline.PROMPT)
        cl.register("iset", Cline.GLOBAL, Cline.PROMPT)
        cl.register("ilo", Cline.GLOBAL, Cline.PROMPT)
        cl.register("ihi", Cline.GLOBAL, Cline.PROMPT)
        cl.register("plo", Cline.GLOBAL, Cline.PROMPT)
        cl.register("phi", Cline.LOCAL, Cline.PROMPT)
        cl.register("xlo", Cline.GLOBAL, Cline.PROMPT)
        cl.register("xhi", Cline.GLOBAL, Cline.PROMPT)
        cl.register("ylo", Cline.GLOBAL, Cline.PROMPT)
        cl.register("yhi", Cline.GLOBAL, Cline.PROMPT)
        cl.register("profit", Cline.LOCAL, Cline.PROMPT)
        cl.register("fdevice", Cline.LOCAL, Cline.HIDE)
        cl.register("fwidth", Cline.LOCAL, Cline.HIDE)
        cl.register("fheight", Cline.LOCAL, Cline.HIDE)
        cl.register("method", Cline.LOCAL, Cline.HIDE)
        cl.register("beta", Cline.LOCAL, Cline.HIDE)
        cl.register("fwhm", Cline.LOCAL, Cline.HIDE)
        cl.register("fwhm_min", Cline.LOCAL, Cline.HIDE)
        cl.register("shbox", Cline.LOCAL, Cline.HIDE)
        cl.register("smooth", Cline.LOCAL, Cline.HIDE)
        cl.register("splot", Cline.LOCAL, Cline.HIDE)
        cl.register("fhbox", Cline.LOCAL, Cline.HIDE)
        cl.register("hmin", Cline.LOCAL, Cline.HIDE)
        cl.register("read", Cline.LOCAL, Cline.HIDE)
        cl.register("gain", Cline.LOCAL, Cline.HIDE)
        cl.register("thresh", Cline.LOCAL, Cline.HIDE)

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

        # plot device stuff
        device = cl.get_value("device", "plot device", "1/xs")
        width = cl.get_value("width", "plot width (inches)", 0.0)
        height = cl.get_value("height", "plot height (inches)", 0.0)

        if server_or_local:
            resource = cl.get_value("run", "run name", "run005")
            if source == "hs":
                first = cl.get_value("first", "first frame to plot", 1)
            else:
                first = cl.get_value("first", "first frame to plot", 1, 0)

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

        # define the panel grid. first get the labels and maximum dimensions
        ccdinf = spooler.get_ccd_pars(source, resource)

        nxdef = cl.get_default("nx", 3)

        if len(ccdinf) > 1:
            ccd = cl.get_value("ccd", "CCD(s) to plot [0 for all]", "0")
            if ccd == "0":
                ccds = list(ccdinf.keys())
            else:
                ccds = ccd.split()
                check = set(ccdinf.keys())
                if not set(ccds) <= check:
                    raise hcam.HipercamError("At least one invalid CCD label supplied")

            if len(ccds) > 1:
                nxdef = min(len(ccds), nxdef)
                cl.set_default("nx", nxdef)
                nx = cl.get_value("nx", "number of panels in X", 3, 1)
            else:
                nx = 1
        else:
            nx = 1
            ccds = list(ccdinf.keys())

        cl.set_default("pause", 0.0)
        pause = cl.get_value(
            "pause", "time delay to add between" " frame plots [secs]", 0.0, 0.0
        )

        cl.set_default("plotall", False)
        plotall = cl.get_value(
            "plotall", "plot all frames," " regardless of status?", False
        )

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

        lowlevel = cl.get_value(
            "lowlevel", "bias level lower limit for warnings", 2000.0
        )

        highlevel = cl.get_value(
            "highlevel", "bias level upper limit for warnings", 3500.0
        )

        # flat (if any)
        flat = cl.get_value(
            "flat", fprompt, cline.Fname("flat", hcam.HCAM), ignore="none"
        )
        if flat is not None:
            # read the flat frame
            flat = hcam.MCCD.read(flat)

        # defect file (if any)
        dfct = cl.get_value(
            "defect",
            "defect file ['none' to ignore]",
            cline.Fname("defect", hcam.DFCT),
            ignore="none",
        )
        if dfct is not None:
            # read the defect frame
            dfct = defect.MccdDefect.read(dfct)

        # Get windows from hdriver
        setup = cl.get_value("setup", "display current hdriver window settings", False)

        if setup:
            drurl = cl.get_value(
                "drurl", "URL for driver windows", "http://192.168.1.2:5100"
            )

        # define the display intensities
        msub = cl.get_value("msub", "subtract median from each window?", True)

        iset = cl.get_value(
            "iset",
            "set intensity a(utomatically)," " d(irectly) or with p(ercentiles)?",
            "a",
            lvals=["a", "d", "p"],
        )
        iset = iset.lower()

        plo, phi = 5, 95
        ilo, ihi = 0, 1000
        if iset == "d":
            ilo = cl.get_value("ilo", "lower intensity limit", 0.0)
            ihi = cl.get_value("ihi", "upper intensity limit", 1000.0)
        elif iset == "p":
            plo = cl.get_value(
                "plo", "lower intensity limit percentile", 5.0, 0.0, 100.0
            )
            phi = cl.get_value(
                "phi", "upper intensity limit percentile", 95.0, 0.0, 100.0
            )

        # region to plot
        for i, cnam in enumerate(ccds):
            nxtot, nytot, nxpad, nypad = ccdinf[cnam]
            if i == 0:
                xmin, xmax = float(-nxpad), float(nxtot + nxpad + 1)
                ymin, ymax = float(-nypad), float(nytot + nypad + 1)
            else:
                xmin = min(xmin, float(-nxpad))
                xmax = max(xmax, float(nxtot + nxpad + 1))
                ymin = min(ymin, float(-nypad))
                ymax = max(ymax, float(nytot + nypad + 1))

        xlo = cl.get_value("xlo", "left-hand X value", xmin, xmin, xmax, enforce=False)
        xhi = cl.get_value("xhi", "right-hand X value", xmax, xmin, xmax, enforce=False)
        ylo = cl.get_value("ylo", "lower Y value", ymin, ymin, ymax, enforce=False)
        yhi = cl.get_value("yhi", "upper Y value", ymax, ymin, ymax, enforce=False)

        # profile fitting if just one CCD chosen
        if len(ccds) == 1:
            # many parameters for profile fits, although most are not plotted
            # by default
            profit = cl.get_value("profit", "do you want profile fits?", False)

            if profit:
                fdevice = cl.get_value("fdevice", "plot device for fits", "2/xs")
                fwidth = cl.get_value("fwidth", "fit plot width (inches)", 0.0)
                fheight = cl.get_value("fheight", "fit plot height (inches)", 0.0)
                method = cl.get_value(
                    "method", "fit method g(aussian) or m(offat)", "m", lvals=["g", "m"]
                )
                if method == "m":
                    beta = cl.get_value(
                        "beta", "initial exponent for Moffat fits", 5.0, 0.5, 20.
                    )
                else:
                    beta = 0.0
                fwhm_min = cl.get_value(
                    "fwhm_min", "minimum FWHM to allow [unbinned pixels]", 1.5, 0.01
                )
                fwhm = cl.get_value(
                    "fwhm",
                    "initial FWHM [unbinned pixels] for profile fits",
                    6.0,
                    fwhm_min,
                )
                shbox = cl.get_value(
                    "shbox",
                    "half width of box for initial location"
                    " of target [unbinned pixels]",
                    11.0,
                    2.0,
                )
                smooth = cl.get_value(
                    "smooth",
                    "FWHM for smoothing for initial object"
                    " detection [binned pixels]",
                    6.0,
                )
                splot = cl.get_value("splot", "plot outline of search box?", True)
                fhbox = cl.get_value(
                    "fhbox",
                    "half width of box for profile fit" " [unbinned pixels]",
                    21.0,
                    3.0,
                )
                hmin = cl.get_value(
                    "hmin", "minimum peak height to accept the fit", 50.0
                )
                read = cl.get_value("read", "readout noise, RMS ADU", 3.0)
                gain = cl.get_value("gain", "gain, ADU/e-", 1.0)
                thresh = cl.get_value("thresh", "number of RMS to reject at", 4.0)

        else:
            profit = False

    ################################################################
    #
    # all the inputs have now been obtained. Get on with doing stuff

    # open image plot device
    imdev = hcam.pgp.Device(device)
    if width > 0 and height > 0:
        pgpap(width, height / width)

    # set up panels and axes
    nccd = len(ccds)
    ny = nccd // nx if nccd % nx == 0 else nccd // nx + 1

    # slice up viewport
    pgsubp(nx, ny)

    # plot axes, labels, titles. Happens once only
    for cnam in ccds:
        pgsci(hcam.pgp.Params["axis.ci"])
        pgsch(hcam.pgp.Params["axis.number.ch"])
        pgenv(xlo, xhi, ylo, yhi, 1, 0)
        pglab("X", "Y", "CCD {:s}".format(cnam))

    # initialisations. 'last_ok' is used to store the last OK frames of each
    # CCD for retrieval when coping with skipped data.

    total_time = 0  # time waiting for new frame
    fpos = []  # list of target positions to fit
    fframe = True  # waiting for first valid frame with profit

    # plot images
    with spooler.data_source(source, resource, first, full=False) as spool:

        # 'spool' is an iterable source of MCCDs
        nframe = 0
        for mccd in spool:

            if server_or_local:
                # Handle the waiting game ...
                give_up, try_again, total_time = spooler.hang_about(
                    mccd, twait, tmax, total_time
                )

                if give_up:
                    print("rtplot stopped")
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
            #            try:
            tstamp = Time(mccd.head["TIMSTAMP"], format="isot", precision=3)
            print(
                "{:d}, utc= {:s} ({:s}), ".format(
                    mccd.head.get("NFRAME",nframe+1),
                    tstamp.iso,
                    "ok" if mccd.head.get("GOODTIME", True) else "nok",
                ),
                end="",
            )
            #            except:
            #   # sometimes times are junk.
            #   print(
            #      '{:d}, utc = {:s}, '.format(
            #           mccd.head['NFRAME'], '2000-01-01 00:00:00.000'), end=''
            #   )

            # accumulate errors
            emessages = []

            # bias level checks
            if lowlevel != 0.0:
                median = mccd.get_num(0).get_num(0).median()
                if median < lowlevel:
                    emessages.append(
                        "** low bias level, median vs limit: {:.1f} vs {:.1f}".format(
                            median, lowlevel
                        )
                    )

            if highlevel != 0.0:
                try:
                    median = mccd.get_num(0).get_num(1).median()
                except:
                    median = mccd.get_num(0).get_num(0).median()

                if median > highlevel:
                    emessages.append(
                        "** high bias level, median vs limit: {:.1f} vs {:.1f}".format(
                            median, lowlevel
                        )
                    )

            if nframe == 0:
                if bias is not None:
                    # crop the bias on the first frame only
                    bias = bias.crop(mccd)

                if flat is not None:
                    # crop the flat on the first frame only
                    flat = flat.crop(mccd)

            if setup:
                # Get windows from driver. Fair bit of error checking
                # needed. 'got_windows' indicates if anything useful
                # found, 'hwindows' is a list of (llx,lly,nx,ny) tuples
                # if somthing is found.
                try:
                    r = requests.get(drurl, timeout=0.2)

                    if r.text.strip() == "No valid data available":
                        emessages.append(
                            "** bad return from hdriver = {:s}".format(r.text.strip())
                        )
                        got_windows = False

                    elif r.text.strip() == "fullframe":
                        # to help Stu out a bit, effectively just
                        # ignore this one
                        got_windows = False

                    else:
                        # OK, got something
                        got_windows = True
                        lines = r.text.split("\r\n")
                        xbinh, ybinh, nwinh = lines[0].split()
                        xbinh, ybinh, nwinh = int(xbinh), int(ybinh), int(nwinh)
                        hwindows = []
                        for line in lines[1 : nwinh + 1]:
                            llxh, llyh, nxh, nyh = line.split()
                            hwindows.append((int(llxh), int(llyh), int(nxh), int(nyh)))

                        if nwinh != len(hwindows):
                            emessages.append(
                                (
                                    "** expected {:d} windows from"
                                    " hdriver but got {:d}"
                                ).format(nwinh, len(hwindows))
                            )
                            got_windows = False

                except (
                    requests.exceptions.ConnectionError,
                    socket.timeout,
                    requests.exceptions.Timeout,
                ) as err:
                    emessages.append(" ** hdriver error: {!r}".format(err))
                    got_windows = False

            else:
                got_windows = False

            # display the CCDs chosen
            message = ""
            pgbbuf()
            for nc, cnam in enumerate(ccds):
                ccd = mccd[cnam]

                if plotall or ccd.is_data():
                    # this should be data as opposed to a blank frame
                    # between data frames that occur with nskip > 0

                    # subtract the bias
                    if bias is not None:
                        ccd -= bias[cnam]

                    # divide out the flat
                    if flat is not None:
                        ccd /= flat[cnam]

                    if msub:
                        # subtract median from each window
                        for wind in ccd.values():
                            wind -= wind.median()

                    # set to the correct panel and then plot CCD
                    ix = (nc % nx) + 1
                    iy = nc // nx + 1
                    pgpanl(ix, iy)
                    vmin, vmax = hcam.pgp.pCcd(
                        ccd,
                        iset,
                        plo,
                        phi,
                        ilo,
                        ihi,
                        xlo=xlo,
                        xhi=xhi,
                        ylo=ylo,
                        yhi=yhi,
                    )

                    if got_windows:
                        # plot the current hdriver windows
                        pgsci(hcam.CNAMS["green"])
                        pgsls(2)
                        for llxh, llyh, nxh, nyh in hwindows:
                            pgrect(
                                llxh - 0.5,
                                llxh + nxh - 0.5,
                                llyh - 0.5,
                                llyh + nyh - 0.5,
                            )

                    if dfct is not None and cnam in dfct:
                        # plot defects
                        hcam.pgp.pCcdDefect(dfct[cnam])

                    # accumulate string of image scalings
                    if nc:
                        message += ", ccd {:s}: {:.1f}, {:.1f}, exp: {:.4f}".format(
                            cnam, vmin, vmax, mccd.head["EXPTIME"]
                        )
                    else:
                        message += "ccd {:s}: {:.1f}, {:.1f}, exp: {:.4f}".format(
                            cnam, vmin, vmax, mccd.head["EXPTIME"]
                        )

            pgebuf()
            # end of CCD display loop
            print(message)
            for emessage in emessages:
                print(emessage)

            if ccd.is_data() and profit and fframe:
                fframe = False

                # cursor selection of targets after first plot, if profit
                # accumulate list of starter positions

                print(
                    "Please select targets for profile fitting. You can select as many as you like."
                )
                x, y, reply = (xlo + xhi) / 2, (ylo + yhi) / 2, ""
                ntarg = 0
                pgsci(2)
                pgslw(2)
                while reply != "Q":
                    print(
                        "Place cursor on fit target. Any key to register, 'q' to quit"
                    )
                    x, y, reply = pgcurs(x, y)
                    if reply == "q":
                        break
                    else:
                        # check that the position is inside a window
                        wnam = ccd.inside(x, y, 2)

                        if wnam is not None:
                            # store the position, Window label, target number,
                            # box size fwhm, beta
                            ntarg += 1
                            fpos.append(Fpar(x, y, wnam, ntarg, shbox, fwhm, beta))

                            # report information, overplot search box
                            print(
                                (
                                    "Target {:d} selected at {:.1f},"
                                    "{:.1f} in window {:s}"
                                ).format(ntarg, x, y, wnam)
                            )
                            if splot:
                                fpos[-1].plot()

                if len(fpos):
                    print(len(fpos), "targets selected")
                    # if some targets were selected, open the fit plot device
                    fdev = hcam.pgp.Device(fdevice)
                    if fwidth > 0 and fheight > 0:
                        pgpap(fwidth, fheight / fwidth)

            if ccd.is_data():

                # carry out fits. Nothing happens if fpos is empty
                for fpar in fpos:
                    # switch to the image plot
                    imdev.select()

                    # plot search box
                    if splot:
                        fpar.plot()

                    try:
                        # extract search box from the CCD. 'fpar' is updated later
                        # if the fit is successful to reflect the new position
                        swind = fpar.swind(ccd)

                        # carry out initial search
                        x, y, peak = swind.search(smooth, fpar.x, fpar.y, hmin, False)

                        # now for a more refined fit. First extract fit Window
                        fwind = ccd[fpar.wnam].window(
                            x - fhbox, x + fhbox, y - fhbox, y + fhbox
                        )

                        # crude estimate of sky background
                        sky = np.percentile(fwind.data, 50)

                        # uncertainties
                        sigma = np.sqrt(read**2 + np.maximum(0,fwind.data)/gain)

                        # refine the Aperture position by fitting the profile
                        (
                            (sky, height, x, y, fwhm, beta),
                            epars,
                            (wfit, X, Y, chisq, nok, nrej, npar, nfev, message),
                        ) = hcam.fitting.combFit(
                            fwind, sigma,
                            method,
                            sky,
                            peak - sky,
                            x,
                            y,
                            fpar.fwhm,
                            fwhm_min,
                            False,
                            fpar.beta,
                            20.,
                            False,
                            thresh,
                        )

                        print("Targ {:d}: {:s}".format(fpar.ntarg, message))

                        if peak > hmin and ccd[fpar.wnam].distance(x, y) > 1:
                            # update some initial parameters for next time
                            if method == "g":
                                fpar.x, fpar.y, fpar.fwhm = x, y, fwhm
                            elif method == "m":
                                fpar.x, fpar.y, fpar.fwhm, fpar.beta = x, y, fwhm, beta

                            # plot values versus radial distance
                            ok = sigma > 0
                            R = np.sqrt((X - x) ** 2 + (Y - y) ** 2)
                            fdev.select()
                            vmin = min(sky, sky + height, fwind.min())
                            vmax = max(sky, sky + height, fwind.max())
                            extent = vmax - vmin
                            pgeras()
                            pgvstd()
                            pgswin(
                                0, R.max(), vmin - 0.05 * extent, vmax + 0.05 * extent
                            )
                            pgsci(4)
                            pgbox("bcnst", 0, 0, "bcnst", 0, 0)
                            pgsci(2)
                            pglab("Radial distance [unbinned pixels]", "Counts", "")
                            pgsci(1)
                            pgpt(R[ok].flat, fwind.data[ok].flat, 1)
                            if nrej:
                                pgsci(2)
                                pgpt(R[~ok].flat, fwind.data[~ok].flat, 5)

                            # line fit
                            pgsci(3)
                            r = np.linspace(0, R.max(), 400)
                            if method == "g":
                                alpha = 4 * np.log(2.0) / fwhm ** 2
                                f = sky + height * np.exp(-alpha * r ** 2)
                            elif method == "m":
                                alpha = 4 * (2 ** (1 / beta) - 1) / fwhm ** 2
                                f = sky + height / (1 + alpha * r ** 2) ** beta
                            pgline(r, f)

                            # back to the image to plot a circle of radius FWHM
                            imdev.select()
                            pgsci(3)
                            pgcirc(x, y, fwhm)

                        else:
                            print(
                                "  *** below detection threshold; position & FWHM will not updated"
                            )
                            pgsci(2)

                        # plot location on image as a cross
                        pgpt1(x, y, 5)

                    except hcam.HipercamError as err:
                        print(
                            " >> Targ {:d}: fit failed ***: {!s}".format(
                                fpar.ntarg, err
                            )
                        )
                        pgsci(2)

            if pause > 0.0:
                # pause between frames
                time.sleep(pause)

            # update the frame number
            nframe += 1


# From here is support code not visible outside


class Fpar:
    """Class for profile fits. Able to plot the search box around an x,y
    position and come up with a Window representing that region."""

    def __init__(self, x, y, wnam, ntarg, shbox, fwhm, beta):
        self.x = x
        self.y = y
        self.wnam = wnam
        self.ntarg = ntarg
        self.shbox = shbox
        self.fwhm = fwhm
        self.beta = beta

    def region(self):
        return (
            self.x - self.shbox,
            self.x + self.shbox,
            self.y - self.shbox,
            self.y + self.shbox,
        )

    def plot(self):
        """Plots search region"""
        pgsci(2)
        xlo, xhi, ylo, yhi = self.region()
        pgrect(xlo, xhi, ylo, yhi)
        pgptxt(xlo, ylo, 0, 1.3, str(self.ntarg))

    def swind(self, ccd):
        """Returns with search Window"""
        xlo, xhi, ylo, yhi = self.region()
        return ccd[self.wnam].window(xlo, xhi, ylo, yhi)
