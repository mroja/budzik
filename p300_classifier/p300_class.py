# P300 classifier mockup
# Marian Dovgialo

import numpy as np 
import scipy.stats
import scipy.signal as ss
from sklearn.externals import joblib
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from collections import deque

def _tags_to_array(tags):
    '''returns 3D numpy array from OBCI smart tags
    epochs x channels x time'''
    min_length = min(i.get_samples().shape[1] for i in tags)
# really don't like this, but epochs generated by smart tags can vary in length by 1 sample
    array = np.dstack([i.get_samples()[:,:min_length] for i in tags])
    return np.rollaxis(array,2)

def _remove_artifact_epochs(data, labels):
    ''' data - 3D numpy array epoch x channels x time,
    labels - list of epochs labels
    returns clean data and labels
    Provisional version'''
    mask = np.ones(len(data), dtype = bool)
    for id, i in enumerate(data):
        if np.max(np.abs(i))>3000:
            mask[id]=False
    newlabels = [d for d, m in zip(data, mask) if m]
    newdata = data[mask]
    return data, labels
        

def _feature_extraction(data, Fs, bas=-0.1, window=0.4, targetFs=34):
    '''data - 3D numpy array epoch x channels x time,
    returns spatiotemporal features array epoch x features'''
    features = []
    for epoch in data:
        features.append(_feature_extraction_singular(epoch, Fs, bas,
                                                    window, targetFs))
    return np.array(features)
        
    

def _feature_extraction_singular(epoch, Fs, bas=-0.1, 
                                window = 0.5,
                                targetFs=30,):
    '''performs feature extraction on epoch (array channels x time),
    Fs - sampling in Hz
    bas - baseline in seconds
    targetFs = target sampling in Hz (will be approximated)
    window - timewindow after baseline to select in seconds
    returns  1D array downsampled, len = downsampled samples x channels
    
    epoch minus mean of baseline, downsampled by factor int(Fs/targetFs)
    samples used - from end of baseline to window timepoint
     '''
    mean = np.mean(epoch[:, :-bas*Fs], axis=1) 
    decimation_factor = int(1.0*Fs/targetFs) 
    selected = epoch[:,-bas*Fs:(-bas+window)*Fs]-mean[:, None]
    features =  ss.decimate(selected, decimation_factor, axis=1, ftype='fir')
    return features.flatten()
    
def _feature_reduction_mask(ft, labels, mode):
    ''' ft - features 2d array nsamples x nfeatures
    labels - nsamples array of labels 0, 1,
    mode - 'auto', int
    returns - features mask'''
    tscore, p = scipy.stats.ttest_ind(ft[labels==1], ft[labels==0])
    if mode == 'auto':
        mask = p<0.05
        if mask.sum()<1:
            raise Exception('Feature reduction produced zero usable features')
    elif isinstance(mode, int):
        mask_ind = np.argsort(p)[-mode:]
        mask = np.zeros_like(p, dtype=bool)
        mask[mask_ind] = True
    return mask
    


class P300EasyClassifier(object):
    '''Easy and modular P300 classifier
    attributes"
    fname - classifier save filename
    epoch_buffor - current epoch buffor
    max_avr - maximum epochs to average
    decision_buffor - last decisions buffor, when full of identical
    decisions final decision is made
    clf - core classifier from sklearn
    feature_s - feature length'''
    
    def __init__(self, fname='./class.joblib.pkl', max_avr=10,
                    decision_stop=3, targetFs=30, clf=None,
                    feature_reduction = None):
        '''fname - classifier file to save or load classifier on disk
        while classifying produce decision after max_avr epochs averaged,
        or after decision_stop succesfull same decisions
        targetFs - on feature extraction downsample to this Hz
        clf - sklearn type classifier to use as core
        feature_reduction - 'auto', int, None. If 'auto' - features are
        reduced, features left are those which have statistically
        significant (p<0.05) difference in target and nontarget,
        if int - use feature_reduction most significant features, if 
        None don't use reduction
        '''
        self.targetFs = targetFs
        self.fname = fname
        self.epoch_buffor = []
        self.max_avr = max_avr
        self.decision_buffor = deque([], decision_stop)
        self.feature_reduction = feature_reduction
        if clf is None:
            self.clf = LinearDiscriminantAnalysis(solver = 'lsqr', shrinkage='auto')
        
    def load_classifier(self, fname=None):
        '''loads classifier from disk, provide fname - path to joblib
        pickle with classifier, or will be used from init'''
        self.clf = joblib.load(fname)
        
    
    def calibrate(self, targets, nontargets, bas=-0.1, window=0.4, Fs=None):
        '''targets, nontargets - 3D arrays (epoch x channel x time)
        or list of OBCI smart tags
        if arrays - need to provide Fs (sampling frequency) in Hz
        bas - baseline in seconds(negative), in other words start offset'''
    
        if Fs is None:
            Fs = float(targets[0].get_param('sampling_frequency'))
            target_data = _tags_to_array(targets)
            nontarget_data = _tags_to_array(nontargets)
        data = np.vstack((target_data, nontarget_data))
        self.epoch_l = data.shape[2]
        labels = np.zeros(len(data))
        labels[:len(target_data)] = 1
        data, labels = _remove_artifact_epochs(data, labels)
        features = _feature_extraction(data, Fs, bas, window, self.targetFs)
        
        if self.feature_reduction:
            mask = _feature_reduction_mask(features, labels, self.feature_reduction)
            self.feature_reduction_mask = mask
            features = features[:, mask]
        
        
        self.feature_s = features.shape[1]
        self.bas = bas
        self.window = window
        

        self.clf.fit(features, labels)
        joblib.dump(self.clf, self.fname, compress=9)
        return self.clf.score(features, labels)
        
    
        
        
    def run(self, epoch, Fs=None):
        '''epoch - array (channels x time) or smarttag/readmanager object,
         bas - baseline in seconds (negative),
        Fs - sampling frequency Hz, leave None if epoch is smart tag,
        returns decision - 1 for target, 0 for nontarget, 
        None - for no decision'''
        bas = self.bas
        window = self.window
        if Fs is None:
            Fs = float(epoch.get_param('sampling_frequency'))
            epoch = epoch.get_samples()[:,:self.epoch_l]
        if len(self.epoch_buffor)< self.max_avr:
            self.epoch_buffor.append(epoch)
            avr_epoch = np.mean(self.epoch_buffor, axis=0)
        
        features = _feature_extraction_singular(avr_epoch,
                                               Fs, bas, window, self.targetFs)[None, :]
        if self.feature_reduction:
            mask = self.feature_reduction_mask 
            features = features[:, mask]
        decision = self.clf.predict(features)[0]
        self.decision_buffor.append(decision)
        if len(self.decision_buffor) == self.decision_buffor.maxlen:
            if len(set(self.decision_buffor))==1:
                self.decision_buffor.clear()
                self.epoch_buffor = []
                return decision
        if len(self.epoch_buffor) == self.max_avr:
            self.decision_buffor.clear()
            self.epoch_buffor = []
            return decision
        return None
            
        
        
    
        
                    
