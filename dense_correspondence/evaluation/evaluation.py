#!/usr/bin/python

import sys, os
import dense_correspondence_manipulation.utils.utils as utils
utils.add_dense_correspondence_to_python_path()
import matplotlib.pyplot as plt
import cv2
from skimage import color


import dense_correspondence as DC
sys.path.insert(0, '../../pytorch-segmentation-detection/vision/')
sys.path.append('../../pytorch-segmentation-detection/')


from PIL import Image

import torch
from torchvision import transforms
from torch.autograd import Variable
import pytorch_segmentation_detection.models.resnet_dilated as resnet_dilated

import numpy as np
import glob

import sys; sys.path.append('../dataset')
sys.path.append('../correspondence_tools')


from dense_correspondence.dataset.spartan_dataset_masked import SpartanDataset
import dense_correspondence.correspondence_tools.correspondence_plotter as correspondence_plotter
import dense_correspondence.correspondence_tools.correspondence_finder as correspondence_finder

import dense_correspondence.evaluation.plotting as dc_plotting

from dense_correspondence.correspondence_tools.correspondence_finder import random_sample_from_masked_image



class DenseCorrespondenceNetwork(object):

    IMAGE_TO_TENSOR = valid_transform = transforms.Compose([transforms.ToTensor(), ])

    def __init__(self, fcn, descriptor_dimension, image_width=640,
                 image_height=480):

        self._fcn = fcn
        self._descriptor_dimension = descriptor_dimension
        self._image_width = image_width
        self._image_height = image_height

    @property
    def fcn(self):
        return self._fcn

    @property
    def descriptor_dimension(self):
        return self._descriptor_dimension

    @property
    def image_shape(self):
        return [self._image_height, self._image_width]

    def forward_on_img(self, img, cuda=True):
        """
        Runs the network forward on an image
        :param img: img is an image as a numpy array in opencv format [0,255]
        :return:
        """
        img_tensor = DenseCorrespondenceNetwork.IMAGE_TO_TENSOR(img)

        if cuda:
            img_tensor.cuda()

        return self.forward_on_img_tensor(img_tensor)


    def forward_on_img_tensor(self, img):
        """
        Runs the network forward on an img_tensor
        :param img: (C x H X W) in range [0.0, 1.0]
        :return:
        """
        img = img.unsqueeze(0)
        img = Variable(img.cuda())
        res = self.fcn(img)
        res = res.squeeze(0)
        res = res.permute(1, 2, 0)
        res = res.data.cpu().numpy().squeeze()

        return res


    @staticmethod
    def from_config(config):
        """
        Load a network from a config file

        :param config: Dict specifying details of the network architecture
        e.g.
            path_to_network: /home/manuelli/code/dense_correspondence/recipes/trained_models/10_drill_long_3d
            parameter_file: dense_resnet_34_8s_03505.pth
            descriptor_dimensionality: 3
            image_width: 640
            image_height: 480

        :return:
        """

        fcn = resnet_dilated.Resnet34_8s(num_classes=config['descriptor_dimension'])
        fcn.load_state_dict(torch.load(config['path_to_network_params']))
        fcn.cuda()
        fcn.eval()

        return DenseCorrespondenceNetwork(fcn, config['descriptor_dimension'],
                                          image_width=config['image_width'],
                                          image_height=config['image_height'])

    @staticmethod
    def find_best_match(pixel_a, res_a, res_b):
        """
        Compute the correspondences between the pixel_a location in image_a
        and image_b

        :param pixel_a: vector of (x,y) pixel coordinates
        :param res_a: array of dense descriptors
        :param res_b: array of dense descriptors
        :param pixel_b: Ground truth . . .
        :return: (best_match_idx, best_match_diff, norm_diffs)
        """

        debug = False

        descriptor_at_pixel = res_a[pixel_a[0], pixel_a[1]]
        height, width, _ = res_a.shape



        if debug:
            print "height: ", height
            print "width: ", width
            print "res_b.shape: ", res_b.shape


        # non-vectorized version
        # norm_diffs = np.zeros([height, width])
        # for i in xrange(0, height):
        #     for j in xrange(0, width):
        #         norm_diffs[i,j] = np.linalg.norm(res_b[i,j] - descriptor_at_pixel)**2

        norm_diffs = np.sum(np.square(res_b - descriptor_at_pixel), axis=2)

        best_match_flattened_idx = np.argmin(norm_diffs)
        best_match_idx = np.unravel_index(best_match_flattened_idx, norm_diffs.shape)
        best_match_diff = norm_diffs[best_match_idx]

        return best_match_idx, best_match_diff, norm_diffs



class DenseCorrespondenceEvaluation(object):


    def __init__(self, config):
        self._config = config

    def evaluate_network(self, network_data_dict):
        """

        :param network_data_dict: Dict with fields
            - path_to_network
            - parameter_file
            - descriptor_dimensionality
        :return:
        """
        pass

    def load_network_from_config(self, name):
        if name not in self._config["networks"]:
            raise ValueError("Network %s is not in config file" %(name))


        network_config = self._config["networks"][name]
        return DenseCorrespondenceNetwork.from_config(network_config)

    @staticmethod
    def evaluate_network(nn, test_dataset):
        """

        :param nn: A neural network
        :param test_dataset: DenseCorrespondenceDataset
            the dataset to draw samples from
        :return:
        """
        pass

    @staticmethod
    def get_image_data(dataset, scene_name, img_idx):
        """
        Gets RGBD image, pose, mask

        :param dataset: dataset that has image
        :type dataset: DenseCorrespondenceDataset
        :param scene_name: name of scene
        :type scene_name: str
        :param img_idx: index of the image
        :type img_idx: int
        :return: (rgb, depth, mask, pose)
        :rtype: (PIL.Image.Image, PIL.Image.Image, PIL.Image.Image, numpy.ndarray)
        """

        img_idx = utils.getPaddedString(img_idx)
        rgb = dataset.get_rgb_image_from_scene_name_and_idx(scene_name, img_idx)
        depth = dataset.get_depth_image_from_scene_name_and_idx(scene_name, img_idx)
        mask = dataset.get_mask_image_from_scene_name_and_idx(scene_name, img_idx)
        pose = dataset.get_pose_from_scene_name_and_idx(scene_name, img_idx)

        return rgb, depth, mask, pose

    @staticmethod
    def plot_descriptor_colormaps(res_a, res_b):
        """
        Plots the colormaps of descriptors for a pair of images
        :param res_a: descriptors for img_a
        :type res_a: numpy.ndarray
        :param res_b:
        :type res_b: numpy.ndarray
        :return: None
        :rtype: None
        """

        fig, axes = plt.subplots(nrows=1, ncols=2)
        fig.set_figheight(5)
        fig.set_figwidth(15)
        res_a_norm = dc_plotting.normalize_descriptor(res_a)
        axes[0].imshow(res_a_norm)

        res_b_norm = dc_plotting.normalize_descriptor(res_b)
        axes[1].imshow(res_b_norm)

    @staticmethod
    def single_image_pair_qualitative_analysis(dcn, dataset, scene_name,
                                               img_a_idx, img_b_idx,
                                               num_matches=10):
        """
        Computes qualtitative assessment of DCN performance for a pair of
        images

        :param dcn: dense correspondence network to use
        :param dataset: dataset to un the dataset
        :param num_matches: number of matches to generate
        :param scene_name: scene name to use
        :param img_a_idx: index of image_a in the dataset
        :param img_b_idx: index of image_b in the datset


        :type dcn: DenseCorrespondenceNetwork
        :type dataset: DenseCorrespondenceDataset
        :type num_matches: int
        :type scene_name: str
        :type img_a_idx: int
        :type img_b_idx: int
        :type num_matches: int

        :return: None
        """

        rgb_a, depth_a, mask_a, pose_a = DenseCorrespondenceEvaluation.get_image_data(dataset,
                                                                                      scene_name,
                                                                                      img_a_idx)

        rgb_b, depth_b, mask_b, pose_b = DenseCorrespondenceEvaluation.get_image_data(dataset,
                                                                                      scene_name,
                                                                                      img_b_idx)

        # compute dense descriptors
        res_a = dcn.forward_on_img(rgb_a)
        res_b = dcn.forward_on_img(rgb_b)

        # sample points on img_a. Compute best matches on img_b
        sampled_idx_list = random_sample_from_masked_image(mask_a, num_matches)

        # list of cv2.KeyPoint
        kp1 = []
        kp2 = []
        matches = []  # list of cv2.DMatch

        # placeholder constants for opencv
        diam = 0.01
        dist = 0.01

        for i in xrange(0, num_matches):
            pixel_a = [sampled_idx_list[0][i], sampled_idx_list[1][i]]
            best_match_idx, best_match_diff, norm_diffs =\
                DenseCorrespondenceNetwork.find_best_match(pixel_a, res_a,
                                                                                                     res_b)

            # be careful, OpenCV format is x - right, y - down
            kp1.append(cv2.KeyPoint(pixel_a[1], pixel_a[0], diam))
            kp2.append(cv2.KeyPoint(best_match_idx[1], best_match_idx[0], diam))
            matches.append(cv2.DMatch(i, i, dist))

        gray_a_numpy = cv2.cvtColor(np.asarray(rgb_a), cv2.COLOR_BGR2GRAY)
        gray_b_numpy = cv2.cvtColor(np.asarray(rgb_b), cv2.COLOR_BGR2GRAY)
        img3 = cv2.drawMatches(gray_a_numpy, kp1, gray_b_numpy, kp2, matches, flags=2, outImg=gray_b_numpy)
        fig, axes = plt.subplots(nrows=1, ncols=1)
        fig.set_figheight(10)
        fig.set_figwidth(15)
        axes.imshow(img3)
        plt.show()



        # show colormap if possible (i.e. if descriptor dimension is 1 or 3)
        if dcn.descriptor_dimension in [1,3]:
            DenseCorrespondenceEvaluation.plot_descriptor_colormaps(res_a, res_b)




    @staticmethod
    def evaluate_network_qualitative(dcn, num_image_pairs=5, randomize=False):
        dataset = SpartanDataset()

        # Train Data
        print "\n\n-----------Train Data Evaluation----------------"
        if randomize:
            raise NotImplementedError("not yet implemented")
        else:
            scene_name = '13_drill_long_downsampled'
            img_pairs = []
            img_pairs.append([0,737])
            img_pairs.append([409, 1585])
            img_pairs.append([2139, 1041])
            img_pairs.append([235, 1704])

        for img_pair in img_pairs:
            print "Image pair (%d, %d)" %(img_pair[0], img_pair[1])
            DenseCorrespondenceEvaluation.single_image_pair_qualitative_analysis(dcn,
                                                                                 dataset,
                                                                                 scene_name,
                                                                                 img_pair[0],
                                                                                 img_pair[1])

        # Test Data
        print "\n\n-----------Test Data Evaluation----------------"
        dataset.set_test_mode()
        if randomize:
            raise NotImplementedError("not yet implemented")
        else:
            scene_name = '06_drill_long_downsampled'
            img_pairs = []
            img_pairs.append([0, 617])
            img_pairs.append([270, 786])
            img_pairs.append([1001, 2489])
            img_pairs.append([1536, 1917])


        for img_pair in img_pairs:
            print "Image pair (%d, %d)" %(img_pair[0], img_pair[1])
            DenseCorrespondenceEvaluation.single_image_pair_qualitative_analysis(dcn,
                                                                                 dataset,
                                                                                 scene_name,
                                                                                 img_pair[0],
                                                                                 img_pair[1])


    ############ TESTING ################


    @staticmethod
    def test(dcn, dataset, data_idx=1, visualize=False, debug=False, match_idx=10):

        scene_name = '13_drill_long_downsampled'
        img_idx_a = utils.getPaddedString(0)
        img_idx_b = utils.getPaddedString(737)

        DenseCorrespondenceEvaluation.single_image_pair_qualitative_analysis(dcn, dataset,
                                                                             scene_name, img_idx_a,
                                                                             img_idx_b)


def run():
    pass

def main(config):
    eval = DenseCorrespondenceEvaluation(config)
    dcn = eval.load_network_from_config("10_scenes_drill")
    test_dataset = SpartanDataset(mode="test")

    DenseCorrespondenceEvaluation.test(dcn, test_dataset)

def test():
    config_filename = os.path.join(utils.getDenseCorrespondenceSourceDir(), 'config', 'evaluation.yaml')
    config = utils.getDictFromYamlFilename(config_filename)
    default_config = utils.get_defaults_config()
    utils.set_cuda_visible_devices(default_config['cuda_visible_devices'])

    main(config)

if __name__ == "__main__":
    test()