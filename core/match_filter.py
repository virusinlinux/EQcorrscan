#!/usr/bin/python
"""
Function to cross-correlate templates generated by template_gen function with
data and output the detecitons.  The main component of this script is the
normxcorr2 function from the openCV image processing package.  This is a highly
optimized and accurate normalized cross-correlation routine.  The details of
this code can be found here:
    http://www.cs.ubc.ca/research/deaton/remarks_ncc.html
The cpp code was first tested using the Matlab mex wrapper, and has since been
ported to a python callable dynamic library.

Part of the EQcorrscan module to integrate seisan nordic files into a full
cross-channel correlation for detection routine.
EQcorrscan is a python module designed to run match filter routines for
seismology, within it are routines for integration to seisan and obspy.
With obspy integration (which is necessary) all main waveform formats can be
read in and output.

This main section contains a script, LFE_search.py which demonstrates the usage
of the built in functions from template generation from picked waveforms
through detection by match filter of continuous data to the generation of lag
times to be used for relative locations.

The match-filter routine described here was used a previous Matlab code for the
Chamberlain et al. 2014 G-cubed publication.  The basis for the lag-time
generation section is outlined in Hardebeck & Shelly 2011, GRL.

Code generated by Calum John Chamberlain of Victoria University of Wellington,
2015.

All rights reserved.

Pre-requisites:
    gcc             - for the installation of the openCV correlation routine
    python-joblib   - used for parallel processing
    python-obspy    - used for lots of common seismological processing
                    - requires:
                        numpy
                        scipy
                        matplotlib
    python-pylab    - used for plotting
"""
import numpy as np

class DETECTION(object):
    """
    Information required for a full detection based on cross-channel
    correlation sums.

    Attributes:
        :type template_name: str
        :param template_name: The name of the template for which this detection\
        was made
        :type detect_time: :class: 'obspy.UTCDateTime'
        :param detect_time: Time of detection as an obspy UTCDateTime object
        :type no_chans: int
        :param no_chans: The number of channels for which the cross-channel\
        correlation sum was calculated over.
        :type chans: list of str
        :param chans: List of stations for the detection
        :type cccsum_val: float
        :param cccsum_val: The raw value of the cross-channel correlation sum\
        for this detection.
        :type threshold: float
        :param threshold: The value of the threshold used for this detection,\
        will be the raw threshold value related to the cccsum.
        :type typeofdet: str
        :param typeofdet: Type of detection, STA, corr, bright
    """
    detectioncount=0
    def __init__(self, template_name, detect_time,
                 no_chans, detect_val,
                 threshold, typeofdet,
                 chans=None):

        self.template_name=template_name
        self.detect_time=detect_time
        self.no_chans=no_chans
        self.chans=chans
        self.detect_val=detect_val
        self.threshold=threshold
        self.typeofdet=typeofdet
        self.detectioncount+=1

def normxcorr2(template, image):
    """
    Base function to call the c++ correlation routine from the openCV image
    processing suite.  Requires you to have installed the openCV python
    bindings, which can be downloaded on Linux machines using:
        sudo apt-get install python-openCV
    Here we use the cv2.TM_CCOEFF_NORMED method within openCV to give the
    normalized cross-correaltion.  Documentation on this function can be
    found here:
        http://docs.opencv.org/modules/imgproc/doc/object_detection.html?highlight=matchtemplate#cv2.matchTemplate

    :type template: :class: 'numpy.array'
    :type image: :class: 'numpy.array'
    :param image: Requires two numpy arrays, the template and the image to scan
    the template through.  The order of these matters, if you put the template
    after the imag you will get a reversed correaltion matrix

    :return: New :class: 'numpy.array' object of the correlation values for the
    correaltion of the image with the template.
    """
    import cv2
    # Check that we have been passed numpy arrays
    if type(template) != np.ndarray or type(image) != np.ndarray:
        print 'You hav not provided numpy arrays, I will not convert them'
        return 'NaN'
    # Convert numpy arrays to float 32
    cv_template=template.astype(np.float32)
    cv_image=image.astype(np.float32)
    ccc=cv2.matchTemplate(cv_image,cv_template,cv2.TM_CCOEFF_NORMED)
    # Reshape ccc to be a 1D vector as is useful for seismic data
    ccc=ccc.reshape((1,len(ccc)))
    return ccc

def _template_loop_dev(template, chan, delays):
    """
    Sister loop to handle the correlation of a single template (of multiple
    channels) with a single channel of data.

    :type template: obspy.Stream
    :type chan: obspy.Trace
    :type delays: List

    :returns: ccc
    """
    from par import match_filter_par as matchdef
    ccc=np.array([np.nan]*(len(chan.data)-len(template[0].data)+1), dtype=np.float32)
    ccc=ccc.reshape((1,len(ccc)))           # Set default value for
                                            # cross-channel correlation in
                                            # case there are no data that
                                            # match our channels.
    for i in xrange(0,len(template)):
        if template[i].stats.station == chan.stats.station and\
           template[i].stats.channel == chan.stats.channel:
            pad=np.array([0]*int(round(delays[i]*chan.stats.sampling_rate)))
            # Apply shift to data
            image=np.append(chan.data,pad)[len(pad):]
            if matchdef.debug>=4:
                # If we really want to debug we should check that the first
                # section of data (the pad) is really a pad
                import matplotlib.pylab as plt
                fig=plt.figure()
                ax1=fig.add_subplot(211)
                plt.title('Last 60s of data')
                ax1.plot(image[len(image)-60*chan.stats.sampling_rate:])
                ax2=fig.add_subplot(212)
                plt.title('First 60s of data')
                ax2.plot(image[0:60*chan.stats.sampling_rate])
                fig.suptitle(chan.stats.station+'.'+chan.stats.channel+' Padded by '+str(delays[i])+'s')
                plt.show()
            # Hand off to the correlation function
            ccc=(normxcorr2(template[i].data, image))
            # Check which channels are not correlating properly --- TESTING DEBUG
    if matchdef.debug >= 3:
        print '********* DEBUG:  '+chan.stats.station+'.'+\
                chan.stats.channel+' ccc: '+str(max(ccc[0]))
    if matchdef.debug >=3:
        print 'shape of ccc: '+str(np.shape(ccc))
        print 'A single ccc is using: '+str(ccc.nbytes/1000000)+'MB'
        print 'ccc type is: '+str(type(ccc))
    # ccc=np.reshape(ccc,(len(ccc),))
    if matchdef.debug >=3:
        print 'shape of ccc: '+str(np.shape(ccc))
    return ccc

def _channel_loop_dev(templates, delays, stream):
    """
    Loop to generate cross channel correaltion sums for a series of templates -
    hands off the actual correlations to a sister function which can be run in
    parallel.

    :type templates: :class: 'obspy.Stream'
    :param templates: A list of templates, where each one should be an
    obspy.Stream object containing multiple traces of seismic data and the
    relevant header information.
    :type delays: float
    :param delays: A list of lists of delays order in the same way as the
    templates, e.g. delays[1][1] referes to the first trace in templates[1]
    :type stream: :class: 'obspy.Stream'
    :param stream: A single obspy.Stream object containing daylong seismic data
    to be correlated through using the templates.  This is in effect the image

    :return: New list of :class: 'numpy.array' objects.  These will contain the
    correlation sums for each template for this day of data.
    :return: list of ints as number of channels used for each cross-correlation
    """
    from joblib import Parallel, delayed#, load, dump
    #from joblib.pool import has_shareable_memory
    # from obspy import Trace
    import time, multiprocessing
    from par import match_filter_par as matchdef
    num_cores=multiprocessing.cpu_count()
    if len(templates) > num_cores:
        num_cores=len(templates)
    if 'cccs_matrix' in locals():
        del cccs_matrix
    # Dump the large arrays and read them in as memmapped numpy objects
    # temp_folder = tempfile.mkdtemp()
    # filename=os.path.join(temp_folder, 'st.mmap')
    # if os.path.exists(filename): os.unlink(filename)
    # _ = dump(stream, filename)
    # st_memmap = load(filename, mmap_mode='r+')
    # del stream

    # Initialize cccs_matrix, which will be two arrays of len(templates) arrays,
    # where the arrays cccs_matrix[0[:]] will be the cross channel sum for each
    # template.

    # Note: This requires all templates to be the same length, and all channels
    # to be the same length
    cccs_matrix=np.array([np.array([np.array([0.0]*(len(stream[0].data)-\
                                   len(templates[0][0].data)+1))]*\
                          len(templates))]*2)
    # Initialize number of channels array
    no_chans=np.array([0]*len(templates))

    for tr in stream:
        # Send off to sister function
        cccs_list=[]
        tic=time.clock()
        if not len(templates) > 4:
            for i in xrange(0,len(templates)):
                cccs_list.append(_template_loop_dev(templates[i], tr, delays[i]))
            # if matchdef.debug >=3:
                # print 'cccs shape: '+str(np.shape(cccs))
            # Returns a numpy array of the cross-correlation values for that
            # template and channel combination
        else:
            cccs_list=Parallel(n_jobs=num_cores)(delayed\
                                             (_template_loop_dev)(templates[i],\
                                                                  tr, delays[i])\
                                             for i in xrange(len(templates)))
        if matchdef.debug >= 3:
            print 'cccs_list is shaped: '+str(np.shape(cccs_list))
        cccs=np.concatenate(cccs_list, axis=0)
        del cccs_list
        if matchdef.debug >=2:
            print 'After looping through templates the cccs is shaped: '+str(np.shape(cccs))
            print 'cccs is using: '+str(cccs.nbytes/1000000)+' MB of memory'
        cccs_matrix[1]=np.reshape(cccs, (1,len(templates),max(np.shape(cccs))))
        del cccs
        if matchdef.debug >=2:
            print 'cccs_matrix shaped: '+str(np.shape(cccs_matrix))
            print 'cccs_matrix is using '+str(cccs_matrix.nbytes/1000000)+' MB of memory'
        toc=time.clock()
        if matchdef.debug>=2:
            print 'Running the correlation loop for '+tr.stats.station+'.'+\
                    tr.stats.channel+' took: '+str(toc-tic)+' s'
        # Now we have an array of arrays with the first dimensional index giving the
        # channel, the second dimensional index giving the template and the third
        # dimensional index giving the position in the ccc, e.g.:
        # np.shape(cccsums)=(len(stream), len(templates), len(ccc))

        # cccs_matrix=np.array(cccs_matrix)
        # if matchdef.debug >=2:
            # print 'cccs_matrix as a np.array is shaped: '+str(np.shape(cccs_matrix))
        # First work out how many channels were used
        for i in xrange(0,len(templates)):
            if not np.all(np.isnan(cccs_matrix[1][i])):
                # Check that there are some real numbers in the vector rather
                # than being all nan, which is the default case for no match
                # of image and template names
                no_chans[i]+=1
            else:
                # Convert nan arrays to 0.0 so they can be added
                cccs_matrix[1][i]=np.nan_to_num(cccs_matrix[1][i])
        # Now sum along the channel axis for each template to give the cccsum values
        # for each template for each day
        # This loop is disappointingly slow - due to layout in memory - axis=1 is fast
        for i in xrange(0,len(templates)):
            cccsum=np.sum(cccs_matrix[:,[i]], axis=0)
            if matchdef.debug >= 3:
                print 'cccsum is shaped thus: '+str(np.shape(cccsum))
            if not 'cccsums' in locals():
                cccsums=cccsum
            else:
                cccsums=np.append(cccsums,cccsum,axis=0)
        if matchdef.debug>=2:
            print 'cccsums is shaped thus: '+str(np.shape(cccsums))
        cccs_matrix[0]=cccsums
        del cccsums
    if matchdef.debug >=2:
        print 'cccs_matrix is shaped: '+str(np.shape(cccs_matrix))
    ########################## SLOW CONVERSION TO NUMPY ARRAY, DO IT BETTER!
    cccsums=cccs_matrix[0]
    return cccsums, no_chans

def match_filter(template_names, templates, delays, stream, threshold,
                 threshold_type, trig_int, plotvar):
    """
    Over-arching code to run the correlations of given templates with a day of
    seismic data and output the detections based on a given threshold.

    :type templates: list :class: 'obspy.Stream'
    :param templates: A list of templates of which each template is a Stream of
    obspy traces containing seismic data and header information.
    :type stream: :class: 'obspy.Stream'
    :param stream: An obspy.Stream object containing all the data available and
    required for the correlations with templates given.  For efficiency this
    should contain no excess traces which are not in one or more of the
    templates.
    :type threshold: float
    :param threshold: A threshold value set based on the threshold_type
    :type threshold_type: str
    :param threshold:type: The type of threshold to be used, can be MAD,
    absolute or av_chan_corr.
    MAD threshold is calculated as the
    threshold*(mean(abs(cccsum))) where cccsum is the cross-correlation sum
    for a given template.
    absolute threhsold is a true absolute threshold based on the cccsum value
    av_chan_corr is based on the mean values of single-channel
    cross-correlations assuming all data are present as required for the
    template, e.g. av_chan_corr_thresh=threshold*(cccsum/len(template)) where
    template is a single template from the input and the length is the number
    of channels within this template.

    :return: :class: 'DETECTIONS' detections for each channel formatted as
    :class: 'obspy.UTCDateTime' objects.

    """
    from utils import findpeaks, EQcorrscan_plotting
    import time, copy
    from obspy import Trace
    from par import match_filter_par as matchdef
    # Debug option to confirm that the channel names match those in the templates
    if matchdef.debug>=2:
        template_stachan=[]
        data_stachan=[]
        for template in templates:
            for tr in template:
                template_stachan.append(tr.stats.station+'.'+tr.stats.channel)
        for tr in stream:
            data_stachan.append(tr.stats.station+'.'+tr.stats.channel)
        template_stachan=list(set(template_stachan))
        data_stachan=list(set(data_stachan))
        if matchdef.debug >= 3:
            print 'I have template info for these stations:'
            print template_stachan
            print 'I have daylong data for these stations:'
            print data_stachan
    # Perform a check that the daylong vectors are daylong
    for tr in stream:
        if not tr.stats.sampling_rate*86400 == tr.stats.npts:
            raise ValueError ('Data are not daylong for '+tr.stats.station+\
                              '.'+tr.stats.channel)
    # Call the _template_loop function to do all the correlation work
    outtic=time.clock()
    # Edit here from previous, stable, but slow match_filter
    # [cccsums, no_chans]=_template_loop(templates, delays, stream, plotvar)
    [cccsums, no_chans]=_channel_loop_dev(templates, delays, stream)
    if len(cccsums[0])==0:
        raise ValueError('Correlation has not run, zero length cccsum')
    outtoc=time.clock()
    if matchdef.debug >=1:
        print 'Looping over templates and streams took: '+str(outtoc-outtic)+' s'
    if matchdef.debug>=2:
        print 'The shape of the returned cccsums is: '+str(np.shape(cccsums))
        print 'This is from '+str(len(templates))+' templates'
        print 'Correlated with '+str(len(stream))+' channels of data'
    i=0
    detections=[]
    for cccsum in cccsums:
        template=templates[i]
        if threshold_type=='MAD':
            rawthresh=threshold*np.median(np.abs(cccsum))
        elif threshold_type=='absolute':
            rawthresh=threshold
        elif threshold=='av_chan_corr':
            rawthresh=threshold*(cccsum/len(template))
        else:
            print 'You have not selected the correct threshold type, I will use MAD as I like it'
            rawthresh=threshold*np.mean(np.abs(cccsum))
        # Findpeaks returns a list of tuples in the form [(cccsum, sample)]
        print 'Threshold is set at: '+str(rawthresh)
        print 'Max of data is: '+str(max(cccsum))
        # Set up a trace object for the cccsum as this is easier to plot and
        # maintins timeing
        if plotvar:
            # Downsample for plotting
            stream_plot=copy.deepcopy(stream[0])
            stream_plot.decimate(int(stream[0].stats.sampling_rate/25))
            cccsum_plot=Trace(cccsum)
            cccsum_plot.stats.sampling_rate=stream[0].stats.sampling_rate
            cccsum_plot=cccsum_plot.decimate(int(stream[0].stats.sampling_rate/25)).data
            # Enforce same length
            stream_plot.data=stream_plot.data[0:len(cccsum_plot)]
            EQcorrscan_plotting.triple_plot(cccsum_plot, stream_plot,\
                                            rawthresh, True,\
                                          'cccsum_plot_'+template_names[i]+'_'+\
                                          str(stream[0].stats.starttime.year)+'-'+\
                                          str(stream[0].stats.starttime.month)+'-'+\
                                          str(stream[0].stats.starttime.day)+'.pdf')
        tic=time.clock()
        if matchdef.debug>=3 and max(cccsum)>rawthresh:
            peaks=findpeaks.find_peaks2(cccsum, rawthresh, \
                                        trig_int*stream[0].stats.sampling_rate,\
                                        matchdef.debug, stream[0].stats.starttime,
                                        stream[0].stats.sampling_rate)
        elif max(cccsum)>rawthresh:
            peaks=findpeaks.find_peaks2(cccsum, rawthresh, \
                                        trig_int*stream[0].stats.sampling_rate,\
                                        matchdef.debug)
        else:
            print 'No peaks found above threshold'
            peaks=False
        toc=time.clock()
        if matchdef.debug >= 1:
            print 'Finding peaks took: '+str(toc-tic)+' s'
        if peaks:
            for peak in peaks:
                detecttime=stream[0].stats.starttime+\
                            peak[1]/stream[0].stats.sampling_rate
                detections.append(DETECTION(template_names[i],
                                             detecttime,
                                             no_chans[i], peak[0], rawthresh,
                                             'corr'))
        i+=1

    return detections
