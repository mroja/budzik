# P300 classifier mockup
# Marian Dovgialo
from obci.analysis.obci_signal_processing import read_manager
from obci.analysis.obci_signal_processing.smart_tags_manager import SmartTagsManager
from obci.analysis.obci_signal_processing.tags.smart_tag_definition import SmartTagDurationDefinition
from sklearn.externals import joblib
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
import numpy as np
import pylab as pb
from scipy import linalg
from scipy import signal
import scipy.stats
from helper_functions import mgr_filter
from helper_functions import montage_custom
from helper_functions import montage_csa
from helper_functions import montage_ears
from helper_functions import exclude_channels
import p300_class
from p300_class import P300EasyClassifier
#dataset
ds = u'../../../dane_od/test1.obci'
#~ ds = u'../../../dane_od/diody3'

def target_tags_func(tag):
    return tag['desc'][u'index']==tag['desc'][u'target']

def nontarget_tags_func(tag):
    return tag['desc'][u'index']!=tag['desc'][u'target']
    
def get_epochs_fromfile(ds, start_offset=-0.1,duration=2.0, 
                        filter=None, montage=None,
                        drop_chnls = [ u'AmpSaw', u'DriverSaw']):#, u'trig1', u'trig2']):
    '''For offline calibration and testing, load target and nontarget
    epochs using obci read_manager.
    ds - dataset file name without extension.
    start_offset - baseline,
    duration - duration of the epoch (including baseline),
    filter - list of [wp, ws, gpass, gstop] for scipy.signal.iirdesign
    in Hz, Db
    montage - list of ['montage name', ...] ...-channel names if required
        montage name can be 'ears', 'csa', 'custom'
        ears require 2 channel names for ear channels
        custom requires list of reference channel names
    returns - two lists of smart tags: target_tags, nontarget_tags'''
    eeg_rm = read_manager.ReadManager(ds+'.xml', ds+'.raw', ds+'.tag')
    eeg_rm = exclude_channels(eeg_rm, drop_chnls)
    data=eeg_rm.get_samples()
    pb.plot(data[0])
    pb.show()
    if filter:
        eeg_rm = mgr_filter(eeg_rm, filter[0], filter[1],filter[2], 
                            filter[3], ftype='cheby2', use_filtfilt=True)
    if montage:
        if montage[0] == 'ears':
            eeg_rm = montage_ears(eeg_rm, montage[0], montage[1])
        elif montage[0] == 'csa':
            eeg_rm = montage_csa(eeg_rm)
        elif montage[0] == 'custom':
            eeg_rm = montage_custom(eeg_rm, montage[1:])
        else:
            raise Exception('Unknown montage')
   
    data=eeg_rm.get_samples()
    pb.plot(data[0])
    pb.show()
    
    tag_def = SmartTagDurationDefinition(start_tag_name=u'blink',
                                        start_offset=start_offset,
                                        end_offset=0.0,
                                        duration=duration)
    stags = SmartTagsManager(tag_def, '', '' ,'', p_read_manager=eeg_rm)
    target_tags = stags.get_smart_tags(p_func = target_tags_func, p_from = 60.0, p_len=21400.0*512)
    nontarget_tags = stags.get_smart_tags(p_func = nontarget_tags_func, p_from = 60.0, p_len=21400.0*512)
    
    return target_tags, nontarget_tags
    
def evoked_from_smart_tags(tags, chnames, bas = -0.1):
    '''tags - smart tag list, to average
    chnames - list of channels to use for averaging,
    bas - baseline (in seconds)'''
    min_length = min(i.get_samples().shape[1] for i in tags)
    # really don't like this, but epochs generated by smart tags can vary in length by 1 sample
    channels_data = [] 
    Fs = float(tags[0].get_param('sampling_frequency'))
    for i in tags:
        data = i.get_channels_samples(chnames)[:,:min_length]
        for nr, chnl in enumerate(data):
            data[nr] = chnl - np.mean(chnl[0:-Fs*bas])# baseline correction
        if np.abs(np.max(data))<4000:
            channels_data.append(data)
    print len(channels_data)
    return np.mean(channels_data, axis=0), scipy.stats.sem(channels_data, axis=0)

def evoked_pair_plot_smart_tags(tags1, tags2, chnames=['O1', 'O2', 'Pz', 'PO7', 'PO8', 'PO3', 'PO4', 'Cz',],
                                start_offset=-0.1, labels=['target', 'nontarget']):
    '''debug evoked potential plot,
     pairwise comparison of 2 smarttag lists
     chnames - channels to plot
     start_offset - baseline in seconds'''
    ev1, std1 = evoked_from_smart_tags(tags1, chnames, start_offset)
    ev2, std2 = evoked_from_smart_tags(tags2, chnames, start_offset)
    Fs = float(tags1[0].get_param('sampling_frequency'))
    time = np.linspace(0+start_offset, ev1.shape[1]/Fs+start_offset, ev1.shape[1])
    pb.figure()
    for nr, i in enumerate(chnames):
        pb.subplot( (len(chnames)+1)/2, 2, nr+1)
        pb.plot(time, ev1[nr], 'r',label = labels[0])
        pb.fill_between(time, ev1[nr]-std1[nr], ev1[nr]+std1[nr],
                            color = 'red', alpha=0.3, )
        pb.plot(time, ev2[nr], 'b', label = labels[1])
        pb.fill_between(time, ev2[nr]-std2[nr], ev2[nr]+std2[nr],
                        color = 'blue', alpha=0.3)
        
        pb.title(i)
    pb.legend()
    
    pb.show()
    
def testing_class(epochs, cl, target=1):
    ''' testing p300easy, for one class
    epochs - 3d array or list smart tag object of epochs of
    one type (target or nontarget)
    cl - p300easyclassifier
    target - class target or nontarget (1, 0)
    
    returns accuracy
    '''
    ndec = 0
    ncorr = 0
    nepochs = []
    for i in epochs:
        nepoch = len(cl.epoch_buffor)
        dec = cl.run(i)
        if not dec is None:
            ndec += 1
            nepochs.append(nepoch+1)
            if int(target)==int(dec):
                ncorr +=1
            

        #~ print dec, target, cl.decision_buffor
    print 'ndec', ndec
    return ncorr*1./ndec, np.mean(nepochs)
    

if __name__=='__main__':
    filter = [[1, 30.0], [0.5, 35.0], 3, 12]
    #~ filter = [30, 35, 3, 30]
    montage = ['custom', 'Cz']
    baseline = -.2
    window = 0.6
    ept, epnt = get_epochs_fromfile(ds, filter = filter, duration = 1,
                                    montage = montage,
                                    start_offset = baseline,
                                    )
    print ept[0].get_params()
    evoked_pair_plot_smart_tags(ept, epnt, labels=['target', 'nontarget'], chnames=['O1', 'O2'])
    
    training_split = 20
    tFs = 24
    feature_reduction = None
    
    cl = P300EasyClassifier(decision_stop=3, max_avr=1000, targetFs = tFs,
                            feature_reduction = feature_reduction)
    print
    
    print  "Accuracy on training set", cl.calibrate(ept[:training_split], epnt[:training_split], bas=baseline, window=window)
    result = testing_class(ept[training_split:], cl, 1)
    print "Accuracy on TARGETS", result[0], 'Mean epochs averaged:', result[1]
    result = testing_class(epnt[training_split:], cl, 0)
    print "Accuracy on NONTARGETS", result[0], 'Mean epochs averaged:', result[1]

    
    
    
    et = p300_class._tags_to_array(ept)
    ft = p300_class._feature_extraction(et, 128., baseline, window, targetFs=tFs)
    ent = p300_class._tags_to_array(epnt)
    fnt = p300_class._feature_extraction(ent, 128., baseline, window, targetFs=tFs)
    f = np.vstack((ft, fnt))
    labels = np.zeros(len(f))
    labels[:len(ft)] = 1
    if feature_reduction:
        rmask = p300_class._feature_reduction_mask(f, labels, feature_reduction)
    else:
        rmask = np.ones(ft.shape[1],dtype=bool)
    pb.subplot(121)
    pb.plot(ft[:, rmask].T)
    pb.title('Target features')
    pb.subplot(122)
    pb.title('NON Target features')
    pb.plot(fnt[:, rmask].T)
    pb.show()


