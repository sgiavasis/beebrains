#!/usr/bin/python
"""
Process bee brain calcium images using fMRI techniques.

Command:
python <this file> <table file> <image directory> <output directory> <label>

Example:
python imageB.py data/Bee1_lr120313l.txt data/Bee1_lr120313l.pst output bee1

Test 1. effect of odor vs. no odor (asleep, maximum concentration)
Test 2. effect of odor vs. no odor (awake, maximum concentration)
Test 3. effect of concentration (asleep)
Test 4. effect of concentration (awake)
Test 5. effect of asleep vs. awake (maximum concentration)

Preprocessing steps:

(1) Open a bee's table.
(2) Divide the .pst image files corresponding to one wavelength by those
    corresponding to a second wavelength (assumed to be co-registered),
    and save slice stack in nifti (neuroimaging file) format.
(3) Apply FSL's motion correction.
(4) Smooth each slice image with a Gaussian kernel.

Processing steps:

(1) Mean-scale, de-mean and multiply data by 100
(2) Make the amplitude values span interval [0,1] better
(3) Construct a design matrix from conditions, amplitudes, onsets, and durations,
     with a 2nd degree polynomial drift model to remove linear or quadratic trends in the data
(4) Apply a general linear model to all voxels
(5) Create a contrast image

Plotting steps:

(1) Create a figure whose color indicates effect size and opacity reflects statistical significance
(2) Draw overlay and contour around a statistical threshold

Outputs: Nifti and .png image files for each table (for each bee).

Requirements:
* Python libraries:  nibabel, numpy, scipy, nipy
* FSL's mcflirt registration software for motion correction (https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/MCFLIRT)

fMRI-based analysis after Bertrand Thirion's examples:
https://github.com/nipy/nipy/blob/master/examples/labs/demo_dmtx.py
https://github.com/nipy/nipy/blob/master/examples/labs/example_glm.py

Installation:
https://github.com/binarybottle/beebrains
0. first time (one time): $ git clone git@github.com:binarybottle/beebrains.git
   update: $ git pull
1. install python distribution (e.g., Continuum's Anaconda: https://www.anaconda.com/)
2. install nibabel:
   $ easy_install nibble
3. install nipy:
   $ git clone git@github.com:nipy/nipy.git
   $ cd nipy
   $ python setup.py install
4. install FSL (https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/)


Authors:
Arno Klein          arno@binarybottle.com  .  www.binarybottle.com
Satrajit S. Ghosh   satra@mit.edu

(c) 2012  Mindbogglers (http://mindboggle.info) under Apache License Version 2.0
"""

#-----------------------------------------------------------------------------
# Import Python libraries
#-----------------------------------------------------------------------------
import os, sys
import csv
import nibabel as nb
import numpy as np
import pylab as mp
from nipy.modalities.fmri.design_matrix import make_dmtx
from nipy.modalities.fmri.experimental_paradigm import BlockParadigm
from nipy.modalities.fmri.glm import GeneralLinearModel, data_scaling

#=============================================================================
# Settings
#=============================================================================
xdim = 130  # x dimension for each image
ydim = 172  # y dimension for each image
images_per_run = 232  # number of images for a given set of conditions (or bee)
onset_list = [73, 93]
duration_list = [11, 11]
amplitude_list = [0.000001, 0.0001, 0.001, 0.01]
smooth_sigma = 3  # sigma of Gaussian kernel
zthresh = 3.74  # threshold zvalues
max_effect = 100  # maximum effect size
ext = '.nii.gz'  # output file extension

#-----------------------------------------------------------------------------
# Run processing steps (1=True, 0=False)
#-----------------------------------------------------------------------------
convert_images = 0  # convert .pst image slice stack to 2D nifti files
divide_images  = 0  # divide one wavelength's image volume by the other
correct_motion = 0  # apply registration to correct for motion
smooth_images  = 0  # smooth the resulting motion-corrected images
run_analysis   = 1
ntests = 5
plot_design_matrix = 1
plot_histogram = 0
plot_contrast = 1

#-----------------------------------------------------------------------------
# Table parameters (indices start from 0):
#-----------------------------------------------------------------------------
behavior_column = 1
amplitude_column = 3
wavelength_column = 4
image_file_column = 5
start1_column = 6
stop1_column = 7
start2_column = 8
stop2_column = 9

#-----------------------------------------------------------------------------
# Command-line arguments and output file names
#-----------------------------------------------------------------------------
args = sys.argv[:]
if len(args)<3:
    print("\n\t Please provide the names of two directories: \
                one containing .lst table files, another to save output.")
    print("\t Example: python " + args[0] + \
          " data/Bee1_lr120313l.txt data/Bee1_lr120313l.pst output bee1")
    sys.exit()
else:
    table_file = str(args[1])
    images_dir = str(args[2])
    out_path = str(args[3])
    try:
        if not os.path.exists(out_path):
            os.mkdir(out_path)
    except IOError:
        print("Cannot make " + out_path + " directory.")
    if len(args) > 4:
        label = str(args[4]) + '_'
    else:
        label = ''

#-----------------------------------------------------------------------------
# Functions
#-----------------------------------------------------------------------------
def norm_amplitudes(amplitudes):
    """Make the amplitude values span interval [0,1] better
    """
    norm_amps = 1 + 0.1 * (np.log10(np.array(amplitudes)))
    return [max([x, 0]) for x in norm_amps]
    #amplitudes = np.array(amplitudes)
    #return amplitudes / max(amplitudes)

def mycmap(E, Z, thresh, sign='pos'):
    """Create a figure whose opacity reflects the statistical significance
    E = effect size
    Z = Zscore
    thresh = value to threshold Zscore at
    """
    tmp = mp.cm.jet((1+E/np.max(np.abs(E)))/2.)
    if sign == 'pos':
        opacity = Z/thresh
    elif sign == 'neg':
        opacity = -Z/thresh
    elif sign == 'abs':
        opacity = abs(Z)/thresh
    else:
        raise ValueError("sign must be one of 'pos', 'neg', 'abs'")
    opacity[opacity>1] = 1.0
    opacity[opacity<0.2] = 0.0
    tmp[:,:,3] = opacity
    return tmp

def draw_overlay(E,Z, thresh=3.):
    """Draw overlay and contour around statistical threshold
    """
    mp.imshow(mycmap(E, Z, thresh))
    mp.contour(Z > thresh, 1)

#=============================================================================
# Loop through tests
#=============================================================================
for itest in range(ntests):
    ntest = itest + 1

    #=========================================================================
    # Models for analysis
    #=========================================================================
    if ntest == 1:
        #---------------------------------------------------------------------
        # Test 1. effect of odor vs. no odor (asleep, maximum concentration)
        #---------------------------------------------------------------------
        desc = 'Odor vs. no odor: asleep (max. concentration)'
        print(desc)
        rows_lambda1 = [9]
        rows_lambda2 = [10]
        conditions = [0, 0]
        amplitudes = [1, 1]
        onsets = [onset_list[0], onset_list[1]]
        durations = duration_list
    elif ntest == 2:
        #---------------------------------------------------------------------
        # Test 2. effect of odor vs. no odor (awake, maximum concentration)
        #---------------------------------------------------------------------
        desc = 'Odor vs. no odor: awake (max. concentration)'
        print(desc)
        rows_lambda1 = [19]
        rows_lambda2 = [20]
        conditions = [0, 0]
        amplitudes = [1, 1]
        onsets = [onset_list[0], onset_list[1]]
        durations = duration_list
    elif ntest == 3:
        #---------------------------------------------------------------------
        # Test 3. effect of odor concentration (asleep)
        #---------------------------------------------------------------------
        desc = 'Effect of odor concentration: asleep'
        print(desc)
        rows_lambda1 = [3, 5, 7, 9]
        rows_lambda2 = [4, 6, 8, 10]
        n_runs = len(rows_lambda1)
        conditions = np.zeros(2 * len(amplitude_list), dtype=int).tolist()
        conditions.extend([x + 1 for x in range(n_runs)])
        oneruns = [1 for x in range(n_runs)]
        amplitudes = [[x, x] for x in amplitude_list]
        amplitudes.append(oneruns)
        amplitudes = [x for lst in amplitudes for x in lst]
        # Normalize amplitudes
        amplitudes = norm_amplitudes(amplitudes)
        onsets = []
        for irun in range(n_runs):
            offset = irun * images_per_run
            onsets.append(offset + onset_list[0])
            onsets.append(offset + onset_list[1])
        durations = []
        [durations.extend(duration_list) for x in range(n_runs)]
        for irun in range(n_runs):
            offset = irun * images_per_run
            onsets.append(offset)
            durations.append(images_per_run)
    elif ntest == 4:
        #---------------------------------------------------------------------
        # Test 4. effect of odor concentration (awake)
        #---------------------------------------------------------------------
        desc = 'Effect of odor concentration: awake'
        print(desc)
        rows_lambda1 = [13, 15, 17, 19]
        rows_lambda2 = [14, 16, 18, 20]
        n_runs = len(rows_lambda1)
        conditions = np.zeros(2 * len(amplitude_list), dtype=int).tolist()
        conditions.extend([x + 1 for x in range(n_runs)])
        oneruns = [1 for x in range(n_runs)]
        amplitudes = [[x, x] for x in amplitude_list]
        amplitudes.append(oneruns)
        amplitudes = [x for lst in amplitudes for x in lst]
        # Normalize amplitudes
        amplitudes = norm_amplitudes(amplitudes)
        onsets = []
        for irun in range(n_runs):
            offset = irun * images_per_run
            onsets.append(offset + onset_list[0])
            onsets.append(offset + onset_list[1])
        durations = []
        [durations.extend(duration_list) for x in range(n_runs)]
        for irun in range(n_runs):
            offset = irun * images_per_run
            onsets.append(offset)
            durations.append(images_per_run)
    elif ntest == 5:
        #---------------------------------------------------------------------
        # Test 5. effect of asleep vs. awake (maximum concentration)
        #---------------------------------------------------------------------
        desc = 'Asleep vs. awake (max. concentration)'
        print(desc)
        rows_lambda1_asleep = [9]
        rows_lambda2_asleep = [10]
        rows_lambda1_awake = [19]
        rows_lambda2_awake = [20]
        rows_lambda1 = rows_lambda1_asleep
        rows_lambda1.extend(rows_lambda1_awake)
        rows_lambda2 = rows_lambda2_asleep
        rows_lambda2.extend(rows_lambda2_awake)
        conditions = [0, 0, 0, 0, 1, 2]
        amplitudes = [1, 1, 1, 1, 1, 1]
        onsets = [onset_list[0], onset_list[1],
                  onset_list[0] + images_per_run, onset_list[1] + images_per_run,
                  0, images_per_run]
        durations = [duration_list[0], duration_list[1],
                     duration_list[0], duration_list[1]]
        durations.extend([images_per_run, images_per_run])

    #=========================================================================
    # Preprocess (divide, coregister, and smooth) images
    #=========================================================================
    n_images = len(rows_lambda1) * images_per_run
    ratio_file = os.path.join(out_path, label + 'ratio_test' + str(ntest) + ext)
    moco_file =  os.path.join(out_path, label + 'moco_test' + str(ntest) + ext)
    smooth_file = os.path.join(out_path, label + 'smooth_test' + str(ntest) + ext)
    #-------------------------------------------------------------------------
    # Divide the .pst image files corresponding to one wavelength by those
    # corresponding to a second wavelength (assumed to be co-registered),
    # and save slice stack in nifti (neuroimaging file) format
    #-------------------------------------------------------------------------
    if convert_images:
        print('Convert images...')

        # Load table
        try:
            csv_reader = csv.reader(open(table_file, 'rU'), dialect=csv.excel_tab)
        except IOError:
            print("  Cannot open " + table_file + ".")

        # Loop through wavelength 1 rows and stack images
        count = 0
        image_stack = np.zeros((xdim, ydim, 1, n_images), dtype=float)
        for irow, row in enumerate(csv_reader):
            if irow in rows_lambda1:
                # Load .pst file containing multiple images
                file = os.path.join(images_dir, row[image_file_column])
                print('  Loading ' + file + ' and stacking images...')
                raw = np.fromfile(file, dtype='<i2')
                for iframe in range(images_per_run):
                    image_vector = raw[iframe * xdim * ydim :
                                       (iframe + 1) * xdim * ydim]
                    image_matrix = np.reshape(image_vector, (xdim, ydim))
                    # Stack
                    image_stack[:, :, 0, count] = image_matrix
                    count += 1

        # Reload table
        try:
            csv_reader = csv.reader(open(table_file, 'rU'), dialect=csv.excel_tab)
        except IOError:
            print("  Cannot open " + table_file + ".")

        # Loop through wavelength 2 rows and divide wavelength 1 images
        count = 0
        for irow, row in enumerate(csv_reader):
            if irow in rows_lambda2:
                # Load .pst file containing multiple images
                file = os.path.join(images_dir, row[image_file_column])
                print('  Loading ' + file + ' and dividing wavelength images...')
                raw = np.fromfile(file, dtype='<i2')
                for iframe in range(images_per_run):
                    image_vector = raw[iframe * xdim * ydim :
                                       (iframe + 1) * xdim * ydim]
                    image_matrix = np.reshape(image_vector, (xdim, ydim))
                    # Divide first by second wavelength (alternate rows)
                    # NOTE: two wavelength images assumed to be co-registered
                    image_stack[:, :, 0, count] = \
                    image_stack[:, :, 0, count] / image_matrix
                    count += 1

        nb.save(nb.Nifti1Image(image_stack, np.eye(4)), ratio_file)

    #-------------------------------------------------------------------------
    # Apply FSL's motion correction
    #-------------------------------------------------------------------------
    if correct_motion:
        print('Correcting motion...')
        cmd = ['  mcflirt -in', ratio_file, '-out', moco_file]
        print(' '.join(cmd)); os.system(' '.join(cmd))

    #-------------------------------------------------------------------------
    # Smooth each slice image with a Gaussian kernel
    #-------------------------------------------------------------------------
    if smooth_images:
        print('Smoothing image')
        cmd = ['  fslmaths', moco_file, '-s', str(smooth_sigma), smooth_file]
        print(' '.join(cmd)); os.system(' '.join(cmd))

    #=========================================================================
    # Conduct a general linear model analysis on the preprocessed images per test
    # (Requires the preprocessed image and the following paradigm lists from above:
    #  conditions, onsets, durations, amplitudes)
    #=========================================================================
    if run_analysis:
        ('Run general linear model analysis for each test...')
        img = nb.load(smooth_file)

        #-----------------------------------------------------------------
        # Construct a design matrix for each test
        #-----------------------------------------------------------------
        print('  Make design matrix...')
        print('    Conditions:\n      {}'.format(conditions))
        print('    Amplitudes:\n      {}'.format(amplitudes))
        print('    Onsets:\n      {}'.format(onsets))
        print('    Durations:\n      {}'.format(durations))
        paradigm = BlockParadigm(con_id=conditions, onset=onsets,
                                 duration=durations, amplitude=amplitudes)
        frametimes = np.linspace(0, n_images-1, n_images)

        if ntest < 3:
            dmtx = make_dmtx(frametimes, paradigm, hrf_model='FIR',
                             drift_model='polynomial', drift_order=2, hfcut=np.inf)
        else:
            dmtx = make_dmtx(frametimes, paradigm, hrf_model='FIR', hfcut=np.inf)
        design_matrix = dmtx.matrix

        # Plot the design matrix
        if plot_design_matrix:
            fig1 = mp.figure(figsize=(10, 6))
            dmtx.show()
            mp.title(desc)
            fig1_file = os.path.join(out_path, label + 'design_matrix_test' + \
                                               str(ntest) + '.png')
            mp.savefig(fig1_file)

        #-----------------------------------------------------------------
        # Mean-scale, de-mean and multiply data by 100
        #-----------------------------------------------------------------
        mask = np.sum(img.get_data(), axis=-1) > 0
        data, mean = data_scaling(img.get_data()[mask].T)
        if np.size(data):
            mean.shape = mask.shape

            #-----------------------------------------------------------------
            # Apply a general linear model to all pixels
            #-----------------------------------------------------------------
            print('   Apply general linear model...')
            model = "ar1"
            glm = GeneralLinearModel(design_matrix)
            glm.fit(data, model=model)

            #-----------------------------------------------------------------
            # Create a contrast image
            #
            # Contrast condition 1 vs. condition 2, holding condition 3 constant
            # (sleep vs. awake holding concentration of odorant constant)
            #-----------------------------------------------------------------
            print('  Make contrast image...')

            # Specify the contrast [1 -1 0 ..]
            contrast = np.zeros(design_matrix.shape[1])
            if ntest < 5:
                contrast[0] = 1
            else:
                contrast[1] = 1
                contrast[2] = -1
            glm_contrast = glm.contrast(contrast)

            # Compute the contrast image
            zvalues = glm_contrast.z_score()
            zvalues.shape = mask.shape
            effect = glm_contrast.effect.copy()
            effect.shape = mask.shape

            # Save the contrast as an image in a neuroimaging format
            contrast_image = nb.Nifti1Image(zvalues, np.eye(4))
            contrast_file = os.path.join(out_path,
                                    label + 'zmap_test' + str(ntest) + ext)
            nb.save(contrast_image, contrast_file)

            # Plot contrast image
            if plot_contrast:
                print('    Plotting contrast image...')
                fig3 = mp.figure()
                mp.imshow(np.squeeze(mean).T, cmap=mp.cm.gray)
                if np.max(zvalues) > zthresh and np.max(effect) < max_effect:
                    print('    Plotting overlays...')
                    draw_overlay(np.squeeze(effect).T, np.squeeze(zvalues).T,
                                 thresh=zthresh)
                mp.title(desc)
                fig3_file = os.path.join(out_path,
                                    label + 'contrast_test' + str(ntest) + '.png')
                mp.savefig(fig3_file)
