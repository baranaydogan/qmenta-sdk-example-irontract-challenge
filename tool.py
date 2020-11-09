import os
import amico
import nibabel as nib
import numpy as np
from dipy.io.gradients import read_bvals_bvecs
from dipy.core.geometry import normalized_vector
from dipy.io.streamline import load_tractogram

import shutil
import scipy.ndimage.morphology
from dipy.io.gradients import read_bvals_bvecs
from dipy.tracking import utils
from dipy.tracking.streamlinespeed import length


# AnalysisContext documentation: https://docs.qmenta.com/sdk/sdk.html
def run(context):

    ####################################################
    # Get the path to input files  and other parameter #
    ####################################################
    analysis_data = context.fetch_analysis_data()
    settings = analysis_data['settings']
    postprocessing = settings['postprocessing']

    hcpl_dwi_file_handle = context.get_files('input', modality='HARDI')[0]
    hcpl_dwi_file_path = hcpl_dwi_file_handle.download('/root/')

    hcpl_bvalues_file_handle = context.get_files(
        'input', reg_expression='.*prep.bvalues.hcpl.txt')[0]
    hcpl_bvalues_file_path = hcpl_bvalues_file_handle.download('/root/')
    hcpl_bvecs_file_handle = context.get_files(
        'input', reg_expression='.*prep.gradients.hcpl.txt')[0]
    hcpl_bvecs_file_path = hcpl_bvecs_file_handle.download('/root/')

    inject_file_handle = context.get_files(
        'input', reg_expression='.*prep.inject.nii.gz')[0]
    inject_file_path = inject_file_handle.download('/root/')
    seed_mask_img = nib.load(inject_file_path)
    affine = seed_mask_img.affine

    VUMC_ROIs_file_handle = context.get_files(
        'input', reg_expression='.*VUMC_ROIs.nii.gz')[0]
    VUMC_ROIs_file_path = VUMC_ROIs_file_handle.download('/root/')

    #############################
    # Fitting NODDI using AMICO #
    #############################
    amico.core.setup()

    ae = amico.Evaluation("/root/", ".")

    [_, bvecs] = read_bvals_bvecs(None, hcpl_bvalues_file_path)
    bvecs_norm = normalized_vector(hcpl_bvecs_file_path)
    bvecs_norm[0] = [0, 0, 0]
    np.savetxt('/root/grad_norm.txt', np.matrix.transpose(bvecs_norm), fmt='%.3f')

    amico.util.fsl2scheme(hcpl_bvalues_file_path, '/root/grad_norm.txt')

    ae.load_data(dwi_filename="prep.dwi.hcpl.nii.gz",
                 scheme_filename="bval.scheme", mask_filename="mask.nii.gz", b0_thr=30)

    ae.set_model("NODDI")
    ae.generate_kernels(regenerate=True)
    ae.load_kernels()

    ae.fit()

    ae.save_results()

    ######################################################
    # Computing inclusion/exclusion maps from NODDI maps #
    ######################################################

    os.system('mrcalc /root/AMICO/NODDI/FIT_OD.nii.gz 0.1 -gt ' +
              '/root/AMICO/NODDI/FIT_OD.nii.gz 0.7 -lt -mul /root/wm_mask.nii.gz')

    os.system('mrcalc /root/AMICO/NODDI/FIT_ICVF.nii.gz 0.95 -lt /root/gm_mask.nii.gz')

    os.system('mrcalc /root/AMICO/NODDI/FIT_ISOVF.nii.gz 0 -gt /root/csf_mask.nii.gz')

    ##################################################
    # Doing reconstruction&tracking using TRAMPOLINO #
    ##################################################
    os.chdir('/root')
    os.system('trampolino -r results -n mrtrix_workflow recon -i prep.dwi.hcpl.nii.gz ' +
              '-v prep.gradients.hcpl.txt -b prep.bvalues.hcpl.txt ' +
              '--opt bthres:0,mask:wm_mask.nii.gz mrtrix_msmt_csd track' +
              '-s prep.inject.nii.gz --opt nos:10000,include:gm_mask.nii.gz,exclude:csf_mask.nii.gz ' +
              '--min_length 10,50 --ensemble min_length mrtrix_tckgen ' +
              'convert -r wm_mask.nii.gz tck2trk')

    track = load_tractogram('results/track.trk', 'wm_mask.nii.gz')
    streamlines = track.streamlines

    ###########################################################################
    # Compute 3D volumes for the IronTract Challenge. For 'EPFL', we only     #
    # keep streamlines with length > 1mm. We compute the visitation  count    #
    # image and apply a small gaussian smoothing. The gaussian smoothing      #
    # is especially usefull to increase voxel coverage of deterministic       #
    # algorithms. The log of the smoothed visitation count map is then        #
    # iteratively thresholded producing 200 volumes/operation points.         #
    # For VUMC, additional streamline filtering is done using anatomical      #
    # priors (keeping only streamlines that intersect with at least one ROI). #
    ###########################################################################
    if postprocessing in ["EPFL", "ALL"]:
        context.set_progress(message='Processing density map (EPFL)')
        volume_folder = "/root/vol_epfl"
        output_epfl_zip_file_path = "/root/TrackyMcTrackface_EPFL_example.zip"
        os.mkdir(volume_folder)
        lengths = length(streamlines)
        streamlines = streamlines[lengths > 1]
        density = utils.density_map(streamlines, affine, seed_mask_img.shape)
        density = scipy.ndimage.gaussian_filter(density.astype("float32"), 0.5)

        log_density = np.log10(density + 1)
        max_density = np.max(log_density)
        for i, t in enumerate(np.arange(0, max_density, max_density / 200)):
            nbr = str(i)
            nbr = nbr.zfill(3)
            mask = log_density >= t
            vol_filename = os.path.join(volume_folder,
                                        "vol" + nbr + "_t" + str(t) + ".nii.gz")
            nib.Nifti1Image(mask.astype("int32"), affine,
                            seed_mask_img.header).to_filename(vol_filename)
        shutil.make_archive(output_epfl_zip_file_path[:-4], 'zip', volume_folder)

    if postprocessing in ["VUMC", "ALL"]:
        context.set_progress(message='Processing density map (VUMC)')
        ROIs_img = nib.load(VUMC_ROIs_file_path)
        volume_folder = "/root/vol_vumc"
        output_vumc_zip_file_path = "/root/TrackyMcTrackface_VUMC_example.zip"
        os.mkdir(volume_folder)
        lengths = length(streamlines)
        streamlines = streamlines[lengths > 1]

        rois = ROIs_img.get_fdata().astype(int)
        _, grouping = utils.connectivity_matrix(streamlines, affine, rois,
                                                inclusive=True,
                                                return_mapping=True,
                                                mapping_as_streamlines=False)
        streamlines = streamlines[grouping[(0, 1)]]

        density = utils.density_map(streamlines, affine, seed_mask_img.shape)
        density = scipy.ndimage.gaussian_filter(density.astype("float32"), 0.5)

        log_density = np.log10(density + 1)
        max_density = np.max(log_density)
        for i, t in enumerate(np.arange(0, max_density, max_density / 200)):
            nbr = str(i)
            nbr = nbr.zfill(3)
            mask = log_density >= t
            vol_filename = os.path.join(volume_folder,
                                        "vol" + nbr + "_t" + str(t) + ".nii.gz")
            nib.Nifti1Image(mask.astype("int32"), affine,
                            seed_mask_img.header).to_filename(vol_filename)
        shutil.make_archive(output_vumc_zip_file_path[:-4], 'zip', volume_folder)

    ###################
    # Upload the data #
    ###################
    context.set_progress(message='Uploading results...')
    if postprocessing in ["EPFL", "ALL"]:
        context.upload_file(output_epfl_zip_file_path,
                            'SpaghettiBeans_EPFL.zip')
    if postprocessing in ["VUMC", "ALL"]:
        context.upload_file(output_vumc_zip_file_path,
                            'SpaghettiBeans_VUMC.zip')
