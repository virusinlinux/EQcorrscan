"""
Functions for despiking seismic data.

:copyright:
    Calum Chamberlain.

:license:
    GNU Lesser General Public License, Version 3
    (https://www.gnu.org/copyleft/lesser.html)
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import numpy as np


def median_filter(tr, multiplier=10, windowlength=0.5,
                  interp_len=0.05, debug=0):
    """
    Filter out spikes in data according to the median absolute deviation of \
    the data.  Replaces spikes with linear interpolation. Works in-place on \
    data.

    :type tr: obspy.Trace
    :param tr: trace to despike
    :type multiplier: float
    :param multiplier: median absolute deviation multiplier to find spikes \
        above.
    :type windowlength: int
    :param windowlength: Length of window to look for spikes in in seconds.
    :type interp_len: int
    :param interp_len: Length in seconds to interpolate around spikes.

    :returns: obspy.trace
    """
    import matplotlib.pyplot as plt
    from multiprocessing import Pool, cpu_count
    from eqcorrscan.utils.timer import Timer

    num_cores = cpu_count()
    if debug >= 1:
        data_in = tr.copy()
    # Note - might be worth finding spikes in filtered data
    filt = tr.copy()
    filt.detrend('linear')
    filt.filter('bandpass', freqmin=10.0,
                freqmax=(tr.stats.sampling_rate / 2) - 1)
    data = filt.data
    del(filt)
    # Loop through windows
    _windowlength = int(windowlength * tr.stats.sampling_rate)
    _interp_len = int(interp_len * tr.stats.sampling_rate)
    peaks = []
    with Timer() as t:
        pool = Pool(processes=num_cores)
        results = [pool.apply_async(_median_window,
                                    args=(data[chunk * _windowlength:
                                               (chunk + 1) * _windowlength],
                                          chunk * _windowlength, multiplier,
                                          tr.stats.starttime + windowlength,
                                          tr.stats.sampling_rate,
                                          debug))
                   for chunk in range(int(len(data) / _windowlength))]
        pool.close()
        for p in results:
            peaks += p.get()
        pool.join()
        for peak in peaks:
            tr.data = _interp_gap(tr.data, peak[1], _interp_len)
    print("Despiking took: %s s" % t.secs)
    if debug >= 1:
        plt.plot(data_in.data, 'r', label='raw')
        plt.plot(tr.data, 'k', label='despiked')
        plt.legend()
        plt.show()
    return tr


def _median_window(window, window_start, multiplier, starttime, sampling_rate,
                   debug=0):
    """Internal function to aid parallel processing

    :type window: np.ndarry
    :param window: Data to look for peaks in.
    :type window_start: int
    :param window_start: Index of window start point in larger array, used \
        for peak indexing.
    :type multiplier: float
    :param multiplier: Multiple of MAD to use as threshold
    :type starttime: obspy.UTCDateTime
    :param starttime: Starttime of window, used in debug plotting.
    :type sampling_rate: float
    :param sampling_rate in Hz, used for debug plotting
    :type debug: int
    :param debug: debug level, if want plots, >= 4.

    :returns: peaks
    """
    from eqcorrscan.utils.findpeaks import find_peaks2_short
    from eqcorrscan.utils.plotting import peaks_plot

    MAD = np.median(np.abs(window))
    thresh = multiplier * MAD
    if debug >= 2:
        print('Threshold for window is: ' + str(thresh) +
              '\nMedian is: ' + str(MAD) +
              '\nMax is: ' + str(np.max(window)))
    peaks = find_peaks2_short(arr=window,
                              thresh=thresh, trig_int=5, debug=0)
    if debug >= 4 and peaks:
        peaks_plot(window, starttime, sampling_rate,
                   save=False, peaks=peaks)
    if peaks:
        peaks = [(peak[0], peak[1] + window_start) for peak in peaks]
    else:
        peaks = []
    return peaks


def _interp_gap(data, peak_loc, interp_len):
    """Internal function for filling gap with linear interpolation

    :type data: numpy.ndarray
    :param data: data to remove peak in
    :type peak_loc: int
    :param peak_loc: peak location position
    :type interp_len: int
    :param interp_len: window to interpolate

    :returns: obspy.tr works in-place
    """
    start_loc = peak_loc - int(0.5 * interp_len)
    end_loc = peak_loc + int(0.5 * interp_len)
    if start_loc < 0:
        start_loc = 0
    if end_loc > len(data) - 1:
        end_loc = len(data) - 1
    fill = np.linspace(data[start_loc], data[end_loc], end_loc - start_loc)
    data[start_loc:end_loc] = fill
    return data


def template_remove(tr, template, cc_thresh, interp_len, debug=0):
    """
    Looks for instances of template in the trace and removes the matches.

    :type tr: obspy.core.Trace
    :param tr: Trace to remove spikes from
    :type template: osbpy.core.Trace
    :param template: Spike template to look for in data
    :type cc_thresh: float
    :param cc_thresh: Cross-correlation trheshold (-1 - 1)
    :type interp_len: float
    :param interp_len: Window length to remove and fill in seconds
    :type debug: int
    :param debug: Debug level

    :returns: tr, works in place
    """
    from eqcorrscan.core.match_filer import normxcorr2
    from eqcorrscan.utils.findpeaks import find_peaks2_short
    from obspy import Trace
    import numpy as np
    from eqcorrscan.utils.timer import Timer
    import matplotlib.pyplot as plt

    data_in = tr.copy()
    _interp_len = int(tr.stats.sampling_rate * interp_len)
    if isinstance(template, Trace):
        template = template.data
    with Timer() as t:
        cc = normxcorr2(tr.data.astype(np.float32),
                        template.astype(np.float32))
        peaks = find_peaks2_short(cc, cc_thresh)
        for peak in peaks:
            tr.data = _interp_gap(tr.data, peak[1], _interp_len)
    print("Despiking took: %s s" % t.secs)
    if debug > 2:
        plt.plot(data_in.data, 'r', label='raw')
        plt.plot(tr.data, 'k', label='despiked')
        plt.legend()
        plt.show()
    return tr