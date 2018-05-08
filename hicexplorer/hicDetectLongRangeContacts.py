from __future__ import division
import argparse
from sklearn.cluster import dbscan
from sklearn.metrics.pairwise import euclidean_distances
from hicexplorer import HiCMatrix as hm
from hicexplorer._version import __version__
from hicexplorer.utilities import toString

import numpy as np
import logging
log = logging.getLogger(__name__)


def parse_arguments(args=None):

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
        description="""
Computes long range contacts within the given contact matrix
""")

    parserRequired = parser.add_argument_group('Required arguments')

    parserRequired.add_argument('--matrix', '-m',
                                help='The matrix to compute the long range contacts on.',
                                nargs=1,
                                required=True)

    parserOpt = parser.add_argument_group('Optional arguments')
    parserOpt.add_argument('--zScoreThreshold', '-zt',
                           type=float,
                           default=2.0,
                           help='z-score threshold to detect long range interactions')

    parserOpt.add_argument('--epsDbscan', '-eps',
                           type=float,
                           default=2.0,
                           help='Epsilon threshold for DBSCAN.')

    parserOpt.add_argument('--minSamplesDbscan', '-msd',
                           type=int,
                           default=2,
                           help='Minimum number of samples needed until they are accepted as a cluster.')

    parserOpt.add_argument('--help', '-h', action='help', help='show this help message and exit')

    parserOpt.add_argument('--version', action='version',
                           version='%(prog)s {}'.format(__version__))

    return parser


def _sum_per_distance(pSum_per_distance, pData, pDistances, pN):
    for i in range(pN):
        pSum_per_distance[pDistances[i]] += pData[i]

    return pSum_per_distance


def compute_zscore_matrix(pMatrix):

    # compute distribution per genomic distance
    # mean
    # sigma

    instances, features = pMatrix.nonzero()
    pMatrix.data = pMatrix.data.astype(float)
    data = pMatrix.data.tolist()

    distances = np.absolute(instances - features)

    # mean = np.zeros(pMatrix.shape[0])
    sigma_2 = np.zeros(pMatrix.shape[0])
    sum_per_distance = np.zeros(pMatrix.shape[0])
    # elements_per_distance = np.zeros(pMatrix.shape[0])

    sum_per_distance = _sum_per_distance(sum_per_distance, data, distances, len(instances))
    # for i in range(len(instances)):
    #     sum_per_distance[distances[i]] += data[i]

    # compute mean
    mean = sum_per_distance / pMatrix.shape[0]

    # compute sigma squared
    for i in range(len(instances)):
        sigma_2[distances[i]] += np.square(data[i] - mean[distances[i]])

    sigma_2 /= pMatrix.shape[0]
    sigma = np.sqrt(sigma_2)

    # z_score (x - mean) / sigma

    for i in range(len(instances)):
        pMatrix.data[i] = (pMatrix.data[i] - mean[distances[i]]) / sigma[distances[i]]

    return pMatrix.data


def compute_long_range_contacts(pHiCMatrix, pThreshold, pEpsDbscan, pMinSamplesDbscan):

    # keep only z-score values if they are higher than pThreshold
    # keep: z-score value, (x, y) coordinate
    # compute all vs. all distances of the coordinates
    # use DBSCAN to cluster this

    zscore_matrix = pHiCMatrix.matrix
    instances, features = zscore_matrix.nonzero()
    data = zscore_matrix.data.astype(float)

    # filter by threshold
    mask = data >= pThreshold
    data = data[mask]
    instances = instances[mask]
    features = features[mask]
    distances_zip = zip(instances, features)
    distances = euclidean_distances(distances_zip)
    # call DBSCAN
    clusters = dbscan(X=distances, eps=pEpsDbscan, metric='precomputed', min_samples=pMinSamplesDbscan)

    # map clusters to contact matrix positions
    return cluster_to_genome_position_mapping(pHiCMatrix, clusters, instances, features)


def cluster_to_genome_position_mapping(pHicMatrix, pCluster, pInstances, pFeatures):
    # mapping: chr_X, start, end, chr_Y, start, end, cluster_id
    mapped_cluster = []
    if len(pCluster[0]) > 0:
        for i in range(len(pInstances)):
            if pCluster[1][i] != -1:
                chr_x, start_x, end_x, _ = pHicMatrix.getBinPos(pInstances[i])
                chr_y, start_y, end_y, _ = pHicMatrix.getBinPos(pFeatures[i])
                mapped_cluster.append((chr_x, start_x, end_x, chr_y, start_y, end_y, pCluster[i]))
    return mapped_cluster


def write_bedgraph(pClusters, pOutFileName):

    with open(pOutFileName, 'w') as fh:
        for cluster_item in pClusters:
            fh.write("%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % cluster_item)


def main():

    args = parse_arguments().parse_args()

    hic_matrix = hm.hiCMatrix(args.matrix)

    hic_matrix.matrix.data = compute_zscore_matrix(hic_matrix.matrix)

    mapped_clusters = compute_long_range_contacts(hic_matrix, args.zScoreThreshold,
                                                  args.epsDbscan, args.minSamplesDbscan)

    # write it to bedgraph / bigwig file
    write_bedgraph(mapped_clusters, args.outFileName)