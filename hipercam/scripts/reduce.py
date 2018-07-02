import sys
import multiprocessing

import hipercam as hcam
from hipercam import cline, utils, spooler
from hipercam.cline import Cline
from hipercam.reduction import (Rfile, initial_checks, extractFlux, moveApers, update_plots,
                                process_ccds, setup_plots, setup_plot_buffers, LogWriter)

# get hipercam version to write into the reduce log file
from pkg_resources import get_distribution, DistributionNotFound
try:
    hipercam_version = get_distribution('hipercam').version
except DistributionNotFound:
    hipercam_version = 'not found'

__all__ = ['reduce', ]


################################################
#
# reduce -- reduces multi-CCD imaging photometry
#
################################################
def reduce(args=None):
    """``reduce [source] rfile (run first twait tmax | flist) log lplot implot
    (ccd nx msub xlo xhi ylo yhi iset (ilo ihi | plo phi))``

    Reduces a sequence of multi-CCD images, plotting lightcurves as images
    come in. It can extract with either simple aperture photometry or Tim
    Naylor's optimal photometry, on specific targets defined in an aperture
    file using |setaper|.

    reduce can source data from both the ULTRACAM and HiPERCAM servers, from
    local 'raw' ULTRACAM and HiPERCAM files (i.e. .xml + .dat for ULTRACAM, 3D
    FITS files for HiPERCAM) and from lists of HiPERCAM '.hcm' files. If you
    have data from a different instrument you should convert into the
    FITS-based hcm format.

    reduce is primarily configured from a file with extension ".red". This
    contains a series of directives, e.g. to say how to re-position and
    re-size the apertures. An initial reduce file is best generated with
    the script |genred| after you have created an aperture file. This contains
    lots of help on what to do.

    A reduce run can be terminated at any point with ctrl-C without doing
    any harm. You may often want to do this at the start in order to adjust
    parameters of the reduce file.

    Parameters:

        source : string [hidden]
           Data source, five options:

             |  'hs': HiPERCAM server
             |  'hl': local HiPERCAM FITS file
             |  'us': ULTRACAM server
             |  'ul': local ULTRACAM .xml/.dat files
             |  'hf': list of HiPERCAM hcm FITS-format files

           'hf' is used to look at sets of frames generated by 'grab' or
           converted from foreign data formats.

        rfile : string
           the "reduce" file, i.e. ASCII text file suitable for reading by
           ConfigParser. Best seen by example as it has many parts.

        run : string [if source ends 's' or 'l']
           run number to access, e.g. 'run034'

        first : int [if source ends 's' or 'l']
           exposure number to start from. 1 = first frame; set = 0 to
           always try to get the most recent frame (if it has changed)

        twait : float [if source ends 's'; hidden]
           time to wait between attempts to find a new exposure, seconds.

        tmax : float [if source ends 's'; hidden]
           maximum time to wait between attempts to find a new exposure,
           seconds.

        flist : string [if source ends 'f']
           name of file list

        log : string
           log file for the results

        tkeep : float
           maximum number of minutes of data to store in internal buffers, 0
           for the lot. When large numbers of frames are stored, performance
           can be slowed (although I am not entirely clear why) in which case
           it makes sense to lose the earlier points (without affecting the
           saving to disk). This parameter also gives operation similar to that
           of "max_xrange" parameter in the ULTRACAM pipeline whereby just
           the last few minutes are shown.

        lplot : bool
           flag to indicate you want to plot the light curve. Saves time not
           to especially in high-speed runs.

        implot : bool
           flag to indicate you want to plot images.

        ccd : string [if implot]
           CCD(s) to plot, '0' for all, '1 3' to plot '1' and '3' only, etc.

        nx : int [if implot]
           number of panels across to display.

        msub : bool [if implot]
           subtract the median from each window before scaling for the
           image display or not. This happens after any bias subtraction.

        xlo : float [if implot]
           left-hand X-limit for plot

        xhi : float [if implot]
           right-hand X-limit for plot (can actually be < xlo)

        ylo : float [if implot]
           lower Y-limit for plot

        yhi : float [if implot]
           upper Y-limit for plot (can be < ylo)

        iset : string [if implot]
           determines how the intensities are determined. There are three
           options: 'a' for automatic simply scales from the minimum to the
           maximum value found on a per CCD basis. 'd' for direct just takes
           two numbers from the user. 'p' for percentile dtermines levels
           based upon percentiles determined from the entire CCD on a per CCD
           basis.

        ilo : float [if implot and iset='d']
           lower intensity level

        ihi : float [if implot and iset='d']
           upper intensity level

        plo : float [if implot and iset='p']
           lower percentile level

        phi : float [if implot and iset='p']
           upper percentile level

    .. Warning::

       The transmission plot generated with reduce is not reliable in the
       case of optimal photometry since it is highly correlated with the
       seeing. If you are worried about the transmission during observing,
       you should always use normal aperture photometry.
    """

    command, args = utils.script_args(args)

    with Cline('HIPERCAM_ENV', '.hipercam', command, args) as cl:

        # register parameters
        cl.register('source', Cline.GLOBAL, Cline.HIDE)
        cl.register('rfile', Cline.GLOBAL, Cline.PROMPT)
        cl.register('run', Cline.GLOBAL, Cline.PROMPT)
        cl.register('first', Cline.LOCAL, Cline.PROMPT)
        cl.register('twait', Cline.LOCAL, Cline.HIDE)
        cl.register('tmax', Cline.LOCAL, Cline.HIDE)
        cl.register('flist', Cline.LOCAL, Cline.PROMPT)
        cl.register('log', Cline.GLOBAL, Cline.PROMPT)
        cl.register('tkeep', Cline.GLOBAL, Cline.PROMPT)
        cl.register('lplot', Cline.LOCAL, Cline.PROMPT)
        cl.register('implot', Cline.LOCAL, Cline.PROMPT)
        cl.register('ccd', Cline.LOCAL, Cline.PROMPT)
        cl.register('nx', Cline.LOCAL, Cline.PROMPT)
        cl.register('msub', Cline.GLOBAL, Cline.PROMPT)
        cl.register('iset', Cline.GLOBAL, Cline.PROMPT)
        cl.register('ilo', Cline.GLOBAL, Cline.PROMPT)
        cl.register('ihi', Cline.GLOBAL, Cline.PROMPT)
        cl.register('plo', Cline.GLOBAL, Cline.PROMPT)
        cl.register('phi', Cline.LOCAL, Cline.PROMPT)
        cl.register('xlo', Cline.GLOBAL, Cline.PROMPT)
        cl.register('xhi', Cline.GLOBAL, Cline.PROMPT)
        cl.register('ylo', Cline.GLOBAL, Cline.PROMPT)
        cl.register('yhi', Cline.GLOBAL, Cline.PROMPT)

        # get inputs
        source = cl.get_value(
            'source', 'data source [hs, hl, us, ul, hf]',
            'hl', lvals=('hs', 'hl', 'us', 'ul', 'hf')
        )

        # set some flags
        server_or_local = source.endswith('s') or source.endswith('l')

        # the reduce file
        rfilen = cl.get_value(
            'rfile', 'reduce file', cline.Fname('reduce.red', hcam.RED))
        try:
            rfile = Rfile.read(rfilen)
        except hcam.HipercamError as err:
            # abort on failure to read as there are many ways to get reduce
            # files wrong
            print(err, file=sys.stderr)
            exit(1)

        if server_or_local:
            resource = cl.get_value('run', 'run name', 'run005')
            first = cl.get_value('first', 'first frame to reduce', 1, 0)
            twait = cl.get_value(
                'twait', 'time to wait for a new frame [secs]', 1., 0.)
            tmx = cl.get_value(
                'tmax', 'maximum time to wait for a new frame [secs]',
                10., 0.)

        else:
            resource = cl.get_value(
                'flist', 'file list', cline.Fname('files.lis', hcam.LIST)
            )
            first = 1

        log = cl.get_value(
            'log', 'name of log file to store results',
            cline.Fname('reduce.log', hcam.LOG, cline.Fname.NEW)
        )

        tkeep = cl.get_value(
            'tkeep', 'number of minute of data to'
            ' keep in internal buffers (0 for all)',
            0., 0.
        )

        lplot = cl.get_value(
            'lplot', 'do you want to plot light curves?', True
        )

        implot = cl.get_value(
            'implot', 'do you want to plot images?', True
        )

        if implot:

            # define the panel grid. first get the labels and maximum
            # dimensions
            ccdinf = spooler.get_ccd_pars(source, resource)

            try:
                nxdef = cl.get_default('nx')
            except KeyError:
                nxdef = 3

            if len(ccdinf) > 1:
                ccd = cl.get_value('ccd', 'CCD(s) to plot [0 for all]', '0')
                if ccd == '0':
                    ccds = list(ccdinf.keys())
                else:
                    ccds = ccd.split()

                if len(ccds) > 1:
                    nxdef = min(len(ccds), nxdef)
                    cl.set_default('nx', nxdef)
                    nx = cl.get_value('nx', 'number of panels in X', 3, 1)
                else:
                    nx = 1
            else:
                nx = 1
                ccds = list(ccdinf.keys())

            # define the display intensities
            msub = cl.get_value(
                'msub', 'subtract median from each window?', True)

            iset = cl.get_value(
                'iset', 'set intensity a(utomatically),'
                ' d(irectly) or with p(ercentiles)?',
                'a', lvals=['a', 'd', 'p']
            )

            plo, phi = 5, 95
            ilo, ihi = 0, 1000
            if iset == 'd':
                ilo = cl.get_value('ilo', 'lower intensity limit', 0.)
                ihi = cl.get_value('ihi', 'upper intensity limit', 1000.)
            elif iset == 'p':
                plo = cl.get_value(
                    'plo', 'lower intensity limit percentile',
                    5., 0., 100.)
                phi = cl.get_value(
                    'phi', 'upper intensity limit percentile',
                    95., 0., 100.)

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

            xlo = cl.get_value('xlo', 'left-hand X value', xmin, xmin, xmax)
            xhi = cl.get_value('xhi', 'right-hand X value', xmax, xmin, xmax)
            ylo = cl.get_value('ylo', 'lower Y value', ymin, ymin, ymax)
            yhi = cl.get_value('yhi', 'upper Y value', ymax, ymin, ymax)

        # save list of parameter values for writing to the reduction file
        plist = cl.list()

    ################################################################
    #
    # all the inputs have now been obtained. Get on with doing stuff
    plot_lims = (xlo, xhi, ylo, yhi)
    imdev, lcdev, spanel, tpanel, xpanel, ypanel, lpanel = setup_plots(rfile, ccds, nx, plot_lims, implot, lplot)

    # a couple of initialisations
    total_time = 0   # time waiting for new frame

    # dictionary of dictionaries for looking up the window associated with a
    # given aperture, i.e.  mccdwins[cnam][apnam] give the name of the Window.
    mccdwins = {}
    if lplot:
        lbuffer, xbuffer, ybuffer, tbuffer, sbuffer = setup_plot_buffers(rfile)

    ############################################
    #
    # open the log file and write headers
    #
    with LogWriter(log, rfile, hipercam_version, plist) as logfile:

        # for storage / retrieval of fit values from one frame to the next
        store = {}

        ncpu = rfile['general']['ncpu']
        if ncpu > 1:
            pool = multiprocessing.Pool(processes=ncpu)
        else:
            pool = None

        ##############################################
        #
        # Finally, start winding through the frames
        #
        tzset = False

        with spooler.data_source(source, resource, first) as spool:

            # 'spool' is an iterable source of MCCDs
            for nf, mccd in enumerate(spool):

                if server_or_local:

                    # Handle the waiting game ...
                    give_up, try_again, total_time = spooler.hang_about(
                        mccd, twait, tmx, total_time
                    )

                    if give_up:
                        print('reduce stopped')
                        break
                    elif try_again:
                        continue

                # indicate progress
                if 'NFRAME' in mccd.head:
                    nframe = mccd.head['NFRAME']
                else:
                    nframe = nf + 1

                print(
                    'Frame {:d}: {:s} [{:s}]'.format(
                        nframe, mccd.head['TIMSTAMP'],
                        'OK' if mccd.head.get('GOODTIME', True) else 'NOK'),
                    end='' if implot else '\n'
                )

                if not tzset:
                    tzero, read, gain, ok = initial_checks(mccd, rfile)
                    # set flag to show we are set
                    if not ok:
                        break
                    tzset = True

                # De-bias the data. Retain a copy of the raw data as 'mccd'
                # in order to judge saturation. Processed data called 'pccd'
                if rfile.bias is not None:
                    # subtract bias
                    pccd = mccd - rfile.bias
                else:
                    # no bias subtraction
                    pccd = mccd.copy()

                if rfile.flat is not None:
                    # apply flat field to processed frame
                    pccd /= rfile.flat

                results = process_ccds(pccd, mccd, pool, ccdproc, rfile,
                                       mccdwins, store, read, gain)

                # write out results to the log file
                alerts = logfile.write_results(nframe, results, pccd, store)
                # print out any accumulated alert messages
                if len(alerts):
                    print('\n'.join(alerts))

                update_plots(results, store, rfile, implot, lplot, imdev, lcdev,
                             pccd, ccds, msub, nx, iset, plo, phi, ilo, ihi, tzero,
                             lpanel, xpanel, ypanel, tpanel, spanel,
                             tkeep, lbuffer, xbuffer, ybuffer, tbuffer, sbuffer)

# END OF MAIN SECTION


# Stuff below here are helper routines that are not exported
def ccdproc(cnam, ccd, flat, rflat, rccd, ccdaper, ccdwins, rfile, store):
    """
    Processing steps for one CCD. This is designed for parallelising the
    processing across CCDs using multiprocessing. To be called *after*
    checking that any processing is needed.

    Arguments::

       cnam     : string
          name of CCD

       ccd      : CCD
          the CCD under processing which should have been debiassed, flat
          fielded and multiplied by the gain to get into electrons.

       flat     : CCD
          the corresponding flat field, needed for getting errors right.

       rflat     : CCD
          readnoise in electrons, divided by the flat

       rccd     : CCD
          unprocessed CCD, used to measure saturation

       ccdaper  : hcam.CCDAper
          all apertures of the CCD in question

       ccdwins  : ?
          label of the Window enclosing each aperture

       rfile    :
          reduction control parameters

       store    :
          dictionary of results


    Returns:: (cnam, store, ccdaper, results)

    """

    # At this point 'ccd' contains all the Windows of a CCD, 'ccdaper' all of
    # its apertures, 'ccdwins' the label of the Window enclosing each
    # aperture, 'rfile' contains control parameters, 'rflat' contains the
    # readout noise in electrons and divided by the flat as a CCD, 'store' is
    # a dictionary initially with jus 'mfwhm' and 'mbeta' set = -1, but will
    # pick up extra stuff from moveApers for use by extractFlux along with
    # revised values of mfwhm and mbeta which are used to initialise profile
    # fits next time.

    # move the apertures
    moveApers(cnam, ccd, flat, rflat, ccdaper, ccdwins, rfile, store)

    # extract flux from all apertures of each CCD. Return with the CCD
    # name, the store dictionary, ccdaper and then the results from
    # extractFlux for compatibility with multiprocessing. Note
    return (
        cnam, store, ccdaper,
        extractFlux(
            cnam, ccd, flat, rflat, rccd, ccdaper, ccdwins, rfile, store),
    )
