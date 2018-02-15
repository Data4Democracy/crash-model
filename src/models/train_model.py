# Training code for D4D Boston Crash Model project
# Developed by: bpben

import re
import csv
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import scipy.stats as ss
from glob import glob
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from scipy.stats import describe
from model_utils import *
from model_classes import *
import os
import argparse
import random
import pickle

# all model outputs must be stored in the "data/processed/" directory
BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__))))

DATA_FP = BASE_DIR + '/data/processed/'

# parse arguments
parser = argparse.ArgumentParser(description="Train crash model.  Additional features specify '' to not include")
parser.add_argument("-m", "--modelname", nargs="+", 
					default='LR_base',
                    help="name of the model, for consistency")
parser.add_argument("-seg", "--seg_data", type=str, 
					default=DATA_FP+'vz_predict_dataset.csv.gz',
                    help="path to the segment data (see data standards) default vz_predict_dataset.csv.gz")
parser.add_argument("-concern", "--concern_column", nargs="+", 
					default='concern',
                    help="Feature name of concern data in segment data.  Let equal '' to not include. default 'concern'")
parser.add_argument("-atr", "--atr_data", nargs="+", 
					default=DATA_FP+'atrs_predicted.csv',
                    help="path to the ATR data (see data standards) default atrs_predicted.csv")
parser.add_argument("--atr_columns", nargs="+", 
					default=['speed_coalesced', 'volume_coalesced'],
                    help="features from atr file")
parser.add_argument("-tmc", "--tmc_data", nargs="+", 
					default=DATA_FP+'tmc_summary.json',
                    help="path to the TMC data (see data standards) default tmc_summary.json")
parser.add_argument("--tmc_columns", nargs="+", 
					default=['Conflict'],
                    help="features from tmc file")
parser.add_argument("-time", "--time_target", nargs="+",
					default=tuple([19,2017]),
                    help="tuple (week,year) for prediction target")
parser.add_argument("-f_cat", "--features_categorical", nargs="+",
					default=['SPEEDLIMIT', 'Struct_Cnd', 'Surface_Tp', 'F_F_Class'],
                    help="list of categorical segment features")
parser.add_argument("-f_cont", "--features_continuous", nargs="+",
					default=['AADT'],
                    help="list of segment features to incude")
parser.add_argument("-process", "--process_features", nargs="+",
					default=True,
                    help="Make categorical into dummies, standardize continuous")
args = parser.parse_args()

week = int(args.time_target[0])
year = int(args.time_target[1])
f_cat = args.features_categorical
f_cont = args.features_continuous

# Read in data
data = pd.read_csv(args.seg_data, dtype={'segment_id':'str'})
data.sort_values(['segment_id', 'year', 'week'], inplace=True)
# get segments with non-zero crashes
data_nonzero = data.set_index('segment_id').loc[data.groupby('segment_id').crash.sum()>0]
data_nonzero.reset_index(inplace=True)
# segment chars
data_segs = data_nonzero.groupby('segment_id')[f_cont+f_cat].max()  # grab the highest values from each column
data_segs.reset_index(inplace=True)

# create featureset holder
features = f_cont+f_cat
print('Segment features included: {}'.format(features))

# add concern
if args.concern_column!=['']:
	print('Adding concerns')
	concern_observed = data[data.year==2016].groupby('segment_id')[args.concern_column].max()
	features.append(args.concern_column)
	data_segs = data_segs.merge(concern_observed.reset_index(), on='segment_id')

# add in atrs if filepath present
if args.atr_data!=['']:
	print('Adding atrs')
	atrs = pd.read_csv(args.atr_data, dtype={'id':'str'})
	# for some reason pandas reads the id as float before str conversions
	atrs['id'] = atrs.id.apply(lambda x: x.split('.')[0])
	data_segs = data_segs.merge(atrs[['id']+args.atr_columns], 
	                            left_on='segment_id', right_on='id')
	features += args.atr_columns

# add in tmcs if filepath present
if args.tmc_data!=['']:
	print('Adding tmcs')
	tmcs = pd.read_json(args.tmc_data,
	                   dtype={'near_id':str})[['near_id']+args.tmc_columns]
	data_segs = data_segs.merge(tmcs, left_on='segment_id', right_on='near_id', how='left')
	data_segs[args.tmc_columns] = data_segs[args.tmc_columns].fillna(0)
	features += args.tmc_columns

# features for linear model
lm_features = features

# add crash data
# create lagged crash values
crash_lags = format_crash_data(data_nonzero.set_index(['segment_id','year','week']), 'crash', 
	week, year)
# add to features
crash_cols = ['pre_week','pre_month','pre_quarter','avg_week']
features += crash_cols

if args.process_features!=['False']:
	print('Processing categorical: {}'.format(f_cat))
	for f in f_cat:
	    t = pd.get_dummies(data_segs[f])
	    t.columns = [f+str(c) for c in t.columns]
	    data_segs = pd.concat([data_segs, t], axis=1)
	    features += t.columns.tolist()
	    # for linear model, allow for intercept
	    lm_features += t.columns.tolist()[1:]
	# aadt - log-transform
	print('Processing continuous: {}'.format(f_cont))
	for f in f_cont:
		data_segs['log_%s' % f] = np.log(data_segs[f]+1)
		features += ['log_%s' % f]
		lm_features += ['log_%s' % f]
	# add segment type
	data_segs['intersection'] = data_segs.segment_id.map(lambda x: x[:2]!='00').astype(int)
	features += ['intersection']
	lm_features += ['intersection']

	# remove duplicated features
	features = list(set(features) - set(f_cat+f_cont))
	lm_features = list(set(lm_features) - set(f_cat+f_cont))

# create model data
data_model = crash_lags.merge(data_segs, left_on='segment_id', right_on='segment_id')
print "full features:{}".format(features)

#Initialize data
df = Indata(data_model, 'target')
#Create train/test split
df.tr_te_split(.7)

#Parameters for model
# class weight
a = data_model['target'].value_counts(normalize=True)
w = 1/a[1]
#Model parameters
params = dict()

#cv parameters
cvp = dict()
cvp['pmetric'] = 'roc_auc'
cvp['iter'] = 5 #number of iterations
cvp['folds'] = 5 #folds for cv (default)
cvp['shuffle'] = True

#LR parameters
mp = dict()
mp['LogisticRegression'] = dict()
mp['LogisticRegression']['penalty'] = ['l1','l2']
mp['LogisticRegression']['C'] = ss.beta(a=5,b=2) #beta distribution for selecting reg strength
mp['LogisticRegression']['class_weight'] = ['balanced']

#xgBoost model parameters
mp['XGBClassifier'] = dict()
mp['XGBClassifier']['max_depth'] = range(3, 7)
mp['XGBClassifier']['min_child_weight'] = range(1, 5)
mp['XGBClassifier']['learning_rate'] = ss.beta(a=2,b=15)
mp['XGBClassifier']['scale_pos_weight'] = [w]

#Initialize tuner
tune = Tuner(df)
#Base XG model
tune.tune('XG_base', 'XGBClassifier', features, cvp, mp['XGBClassifier'])
#Base LR model
tune.tune('LR_base', 'LogisticRegression', lm_features, cvp, mp['LogisticRegression'])

# Run test
test = Tester(df)
test.init_tuned(tune)
test.run_tuned('LR_base', cal=False)
test.run_tuned('XG_base', cal=False)

# sensitivity analysis TODO
# running this to test performance at different weeks
tuned_model = skl.LogisticRegression(**test.rundict['LR_base']['bp'])
# random sets
#print "running sensitivity analysis"

#for i in range(3):
#	test_time = random.choice(data[['year','week']].values)
#	print test_time[0]
#	test_crash = format_crash_data(data_nonzero.set_index(['segment_id','year','week']), 'crash', 
#		test_time[1], test_time[0])
#	test_crash_segs = test_crash.merge(data_segs, left_on='segment_id', right_on='segment_id')
#	tuned_model.fit(test_crash_segs[lm_features], test_crash_segs['target'])
#	print roc_auc_score(test_crash_segs['target'], 
#		tuned_model.predict_proba(test_crash_segs[lm_features])[::,1])

# train, output predictions + model
fit_model = test.rundict['LR_base']['m_fit'].fit(data_model[lm_features], data_model.target)
data_model['preds'] = fit_model.predict_proba(data_model[lm_features])[::,1]
data_model.to_pickle(DATA_FP+'vz_with_predicted.pkl.gz', compression='gzip')
with open('trained_model.pkl', 'w') as f:
	pickle.dump(fit_model, f)

