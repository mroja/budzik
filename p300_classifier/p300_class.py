# P300 classifier mockup
# Marian Dovgialo

import numpy as np 
import scipy.signal as ss
import scikit.learn
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
    newlabels = [d for d, m in zip(data, mask) if s]
    newdata = data[mask]
    return data, labels
        

def _feature_extraction(data, Fs, bas=-0.1):
    '''data - 3D numpy array epoch x channels x time,
    returns spatiotemporal features array epoch x features'''
    features = []
    for epoch in data:
        features.append(_feature_extraction_singular(epoch, Fs, bas))
    return np.array(features)
        
    

def _feature_extraction_singular(epoch, Fs, bas=-0.1, targetFs=24,
                                window = 0.5):
    '''performs feature extraction on epoch (array channels x time),
    Fs - sampling in Hz
    bas - baseline in seconds
    targetFs = target sampling in Hz (will be approximated)
    window - timewindow after baseline to select in seconds
    returns  1D array downsampled, len = downsampled samples x channels '''
    
    decimation_factor = int(1.0*Fs/targetFs) 
    selected = epoch[:,-bas*Fs:(-bas+window)*Fs]
    features =  ss.decimate(selected, decimation_factor, axis=1)
    return features.flatten()


class P300EasyClassifier(object):
    
    def __init__(self, fname='./class.joblib.pkl', max_avr=10, decision_stop=3):
        '''fname - classifier file to save or load classifier on disk
        while classifying produce decision after max_avr epochs averaged,
        or after decision_stop succesfull same decisions'''
        self.fname = fname
        self.epoch_buffor = []
        self.max_avr = max_avr
        self.decision_buffor = deque([], decision_stop)
        
    def load_classifier(self, fname=None):
        '''loads classifier from disk, provide fname - path to joblib
        pickle with classifier, or will be used from init'''
        self.clf = joblib.load(fname)
        
    
    def calibrate(self, targets, nontargets, bas=-0.1, Fs=None, clf=None):
        '''targets, nontargets - 3D arrays (epoch x channel x time)
        or list of OBCI smart tags
        if arrays - need to provide Fs (sampling frequency) in Hz
        bas - baseline in seconds'''
    
        if Fs is None:
            Fs = float(targets[0].get_param('sampling_frequency'))
            target_data = _tags_to_array(targets)
            nontarget_dat = _tags_to_array(nontargets)
        data = np.vstack((target_data, nontarget_data))
        labels = np.zeros(len(data))
        labels[:len(target_data] = 1

        features = _feature_extraction(data, Fs, bas)
        
        if clf is None:
            self.clf = LinearDiscriminantAnalysis(solver = 'eigen', shrinkage='auto')
        self.clf.fit(features, labels)
        joblib.dump(self.clf, self.fname, compress=9)
        
    def run(self, epoch, bas, Fs):
        if len(self.epoch_buffor)< self.max_avr:
            self.epoch_buffor.append(epoch)
            avr_epoch = np.mean(self.epoch_buffor, axis=0)
        
        features = _feature_extraction_singular(avr_epoch, Fs, bas)[None, :]
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
            
        
        
    
        
                    