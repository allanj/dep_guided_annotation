import torch
import torch.autograd as autograd
import sys
from hypergraph.NetworkConfig import  NetworkConfig
import numpy as np
import pickle
import tqdm
from hypergraph.Network import Network

def to_scalar(var):
    # returns a python float
    return var.view(-1).data.tolist()[0]


def argmax(vec):
    # return the argmax as a python int
    # print("vec is ", vec)
    _, idx = torch.max(vec, 0)
    # print("max is ", idx.view(-1).data.tolist()[0])
    return to_scalar(idx)


def prepare_sequence(seq, to_ix):
    idxs = [to_ix[w] for w in seq]
    tensor = torch.LongTensor(idxs)
    if NetworkConfig.GPU_ID >= 0:
        tensor = tensor.cuda()
    return autograd.Variable(tensor)

    # Compute log sum exp in a numerically stable way for the forward algorithm


def log_sum_exp(vec):
    # print('vec:', vec)
    # max_score = vec[argmax(vec)]
    max_score, _ = torch.max(vec, 0)
    #max_score_broadcast = max_score.view(1, -1).expand(1, vec.size()[1])
    return max_score + \
           torch.log(torch.sum(torch.exp(vec - max_score)))  #max_score_broadcast


def logSumExp(vec):
    """

    :param vec: [max_number * max_hyperedge]
    :return: [max_number]
    """
    maxScores, _ = torch.max(vec, 1)
    #maxScores[maxScores == -float("Inf")] = 0
    maxScoresExpanded = maxScores.view(vec.shape[0], 1).expand(vec.shape[0], vec.shape[1])
    return maxScores + torch.log(torch.sum(torch.exp(vec - maxScoresExpanded), 1))

    #merged_final_vec = (vec - F.log_softmax(vec, dim=1)).mean(1) # batch_size * label_size


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def print_insts(insts):
    print('Instances:')
    for inst in insts:
        print(inst)
    print()



def load_emb_glove(path, word2idx, random_embedding_dim = 100):
    UNK = 'unk'
    embedding_dim = -1
    embedding = dict()

    print("reading the pretraing embedding: %s" % (path), flush=True)
    if path is None:
        print("pretrain embedding in None, using random embedding")
    else:

        with open(path, 'r', encoding='utf-8') as file:
            for line in file.readlines():
                line = line.strip()
                if len(line) == 0:
                    continue
                tokens = line.split()
                if embedding_dim < 0:
                    embedding_dim = len(tokens) - 1
                else:
                    # print(tokens)
                    # print(embedding_dim)
                    assert (embedding_dim + 1 == len(tokens))
                embedd = np.empty([1, embedding_dim])
                embedd[:] = tokens[1:]
                first_col = tokens[0]
                embedding[first_col] = embedd


    if len(embedding) > 0:
        print("[Info] Use the pretrained word embedding to initialize: %d x %d" % (len(word2idx), embedding_dim))
        word_embedding = np.empty([len(word2idx), embedding_dim])
        for word in word2idx:
            if word in embedding:
                word_embedding[word2idx[word]] = embedding[word]
            elif word.lower() in embedding:
                word_embedding[word2idx[word]] = embedding[word.lower()]
            else:
                word_embedding[word2idx[word]] = embedding[UNK]
                # self.word_embedding[self.word2idx[word], :] = np.random.uniform(-scale, scale, [1, self.embedding_dim])
        del embedding
    else:
        embedding_dim = random_embedding_dim
        scale = scale = np.sqrt(3.0 / embedding_dim)
        word_embedding = np.empty([len(word2idx), embedding_dim])
        for word in word2idx:
            word_embedding[word2idx[word]] = np.random.uniform(-scale, scale, [1, embedding_dim])
    return word_embedding


def topological_sort(network : Network):

    size = network.count_nodes()
    dists = [None] * size

    #Find all the leaves and assign them 0
    for k in range(size):
        children_list_k = network.get_children(k)
        if len(children_list_k[0]) == 0:  #leaf
            dists[k] = 0


    # while True:
    #     num_ready = size
    #     for k in range(size):
    #         if dists[k] == None:
    #             num_ready -= 1
    #             ready = True
    #             dist_k = 0
    #
    #             children_list_k = network.get_children(k)
    #             for children_k_index in range(len(children_list_k)):
    #                 children_k = children_list_k[children_k_index]
    #                 for child in children_k:
    #                     if dists[child] == None:
    #                         ready = False
    #                         break
    #                     else:
    #                         if dist_k < dists[child] + 1:
    #                             dist_k = dists[child] + 1
    #
    #             assert ready # ??? can I assert ready is always true when the structure is a Directed Tree? or DAG
    #             if ready:
    #                 dists[k] = dist_k
    #
    #     if num_ready == size:
    #         break


    #make sure the nodes in the network are sorted according to the node value
    for k in range(size):
        if dists[k] == None:
            dist_k = 0

            children_list_k = network.get_children(k)
            for children_k_index in range(len(children_list_k)):
                children_k = children_list_k[children_k_index]
                for child in children_k:
                    if dist_k < dists[child] + 1:
                        dist_k = dists[child] + 1

            dists[k] = dist_k



    from collections import defaultdict
    sorted_list = defaultdict(list)

    for k in range(size):
        dist_k = dists[k]
        sorted_list[dist_k].append(k)

    max_number = max([len(dist_k[k]) for k in dist_k])

    return sorted_list, max_number



from abc import ABC, abstractmethod
class Eval():
    @abstractmethod
    def eval(self, insts):
        pass
