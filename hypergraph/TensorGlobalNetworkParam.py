import threading
import torch
import torch.nn as nn
from hypergraph.NetworkConfig import NetworkConfig
from termcolor import colored

class TensorGlobalNetworkParam(nn.Module):

    def __init__(self):
        super(TensorGlobalNetworkParam, self).__init__()
        self.locked = False
        self._size = 0

        self.tuple2id = {}
        self.tuple2id[()] = 0
        self.transition_mat = None

        self.lock = threading.Lock()

        self.network2nodeid2nn = None
        self.network2stagenodes2nodeid2nn = None

    def set_network2nodeid2nn_size(self, size):
        self.network2nodeid2nn = [None] * size
        self.network2stagenodes2nodeid2nn = [None] * size

    def is_locked(self):
        return self.locked


    def size(self):
        return self._size



    def finalize_transition(self):
        self.tuple_size = len(self.tuple2id)
        if NetworkConfig.IGNORE_TRANSITION:
            self.transition_mat = nn.Parameter(torch.zeros(self.tuple_size)).to(NetworkConfig.DEVICE)
            #self.transition_mat.requires_grad = False
        else:
            self.transition_mat = nn.Parameter(torch.randn(self.tuple_size)).to(NetworkConfig.DEVICE)

        self.transition_mat.data[0] = -float('inf') # padding

        self.locked = True


    def add_transition(self, transition):
        with self.lock:
            parent_label_id, children_label_ids = transition
            t = tuple([parent_label_id] + children_label_ids)
            if not self.locked and t not in self.tuple2id:
                tuple2id_size = len(self.tuple2id)
                self.tuple2id[t] = tuple2id_size

            return self.tuple2id[t]








