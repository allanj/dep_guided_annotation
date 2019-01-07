from hypergraph.NetworkCompiler import NetworkCompiler
import numpy as np
from hypergraph.NetworkIDMapper import NetworkIDMapper
from hypergraph.TensorBaseNetwork import TensorBaseNetwork
from hypergraph.TensorGlobalNetworkParam import TensorGlobalNetworkParam
from hypergraph.FeatureManager import FeatureManager
from hypergraph.NetworkModel import NetworkModel
import torch.nn as nn
from hypergraph.Utils import *
from common.LinearInstance import LinearInstance
from example.eval import nereval
import re
from termcolor import colored

class TagNetworkCompiler(NetworkCompiler):

    def __init__(self, label_map):
        super().__init__()
        self.labels = ["x"] * len(label_map)
        self.label2id = label_map
        print(self.labels)
        for key in self.label2id:
            self.labels[self.label2id[key]] = key

        print("Inside compiler: ", self.labels)
        NetworkIDMapper.set_capacity(np.asarray([200, 100, 3], dtype=np.int64))

        print(self.label2id)
        print(self.labels)
        self._all_nodes = None
        self._all_children = None
        self._max_size = 100

        # self.build_generic_network()

    def to_root(self, size):
        return self.to_node(size - 1, len(self.labels) - 1, 2)

    def to_tag(self, pos, label_id):
        return self.to_node(pos, label_id, 1)

    def to_leaf(self, ):
        return self.to_node(0, 0, 0)

    def to_node(self, pos, label_id, node_type):
        return NetworkIDMapper.to_hybrid_node_ID(np.asarray([pos, label_id, node_type]))

    def compile_labeled(self, network_id, inst, param):

        builder = TensorBaseNetwork.NetworkBuilder.builder()
        leaf = self.to_leaf()
        builder.add_node(leaf)

        output = inst.get_output()
        children = [leaf]
        for i in range(inst.size()):
            label = output[i]
            tag_node = self.to_tag(i, self.label2id[label])
            builder.add_node(tag_node)
            builder.add_edge(tag_node, children)
            children = [tag_node]
        root = self.to_root(inst.size())
        builder.add_node(root)
        builder.add_edge(root, children)
        network = builder.build(network_id, inst, param, self)
        return network

    def compile_unlabeled(self, network_id, inst, param):
        # return self.compile_labeled(network_id, inst, param)
        builder = TensorBaseNetwork.NetworkBuilder.builder()
        leaf = self.to_leaf()
        builder.add_node(leaf)

        children = [leaf]
        for i in range(inst.size()):
            current = [None for k in range(len(self.labels))]
            for l in range(len(self.labels)):
                tag_node = self.to_tag(i, l)
                builder.add_node(tag_node)
                for child in children:
                    builder.add_edge(tag_node, [child])
                current[l] = tag_node

            children = current
        root = self.to_root(inst.size())
        builder.add_node(root)
        for child in children:
            builder.add_edge(root, [child])
        network = builder.build(network_id, inst, param, self)
        return network

    # def build_generic_network(self, ):
    #
    #     network = builder.build(None, None, None, None)
    #     self._all_nodes = network.get_all_nodes()
    #     self._all_children = network.get_all_children()

    def decompile(self, network):
        inst = network.get_instance()

        size = inst.size()
        root_node = self.to_root(size)
        all_nodes = network.get_all_nodes()
        curr_idx = np.argwhere(all_nodes == root_node)[0][0] #network.count_nodes() - 1 #self._all_nodes.index(root_node)
        prediction = [None for i in range(size)]
        for i in range(size):
            children = network.get_max_path(curr_idx)
            child = children[0]
            child_arr = network.get_node_array(child)

            prediction[size - i - 1] = self.labels[child_arr[1]]

            curr_idx = child

        inst.set_prediction(prediction)
        return inst


class TagFeatureManager(FeatureManager):
    def __init__(self, param_g, voc_size):
        super().__init__(param_g)
        self.token_embed = 100
        print("vocab size: ", voc_size)
        # self.word_embed = nn.Embedding(voc_size, self.token_embed, padding_idx=0).to(NetworkConfig.DEVICE)
        self.word_embed = nn.Embedding(voc_size, self.token_embed).to(NetworkConfig.DEVICE)

        self.rnn = nn.LSTM(self.token_embed, self.token_embed, batch_first=True,bidirectional=True).to(NetworkConfig.DEVICE)
        self.linear = nn.Linear(self.token_embed * 2, param_g.label_size).to(NetworkConfig.DEVICE)
        #self.rnn = nn.LSTM(self.token_embed, self.token_embed, batch_first=True, bidirectional=True).to(NetworkConfig.DEVICE)
        #self.linear = nn.Linear(self.token_embed, param_g.label_size, bias=False).to(NetworkConfig.DEVICE)




    def load_pretrain(self, path, word2idx):
        emb = load_emb_glove(path, word2idx, self.token_embed)
        self.word_embed.from_pretrained(torch.FloatTensor(emb), freeze=False)
        self.word_embed = self.word_embed.to(NetworkConfig.DEVICE)

    # @abstractmethod
    # def extract_helper(self, network, parent_k, children_k, children_k_index):
    #     pass
    def build_nn_graph(self, instance):

        word_vec = self.word_embed(instance.word_seq).unsqueeze(0)
        #
        lstm_out, _ = self.rnn(word_vec, None)
        linear_output = self.linear(lstm_out).squeeze(0)
        #word_vec = self.word_embed(instance.word_seq) #.unsqueeze(0)
        #linear_output = self.linear(word_vec)#.squeeze(0)
        return linear_output

    def generate_batches(self, train_insts, batch_size):
        '''
        :param instances:
        :param batch_size:
        :return: A list of tuple (input_seqs, network_id_range)
        '''

        max_size = 0
        for inst in train_insts:
            size = inst.word_seq.shape[0]
            if max_size < size:
                max_size = size

        batches = []
        for i in range(0, len(train_insts), batch_size):

            batch_input_seqs = []
            for b in range(i, i + batch_size):
                if b >= len(train_insts):
                    break
                padding_seq = [0] * (max_size - len(train_insts[b].input))
                word_seq = [vocab2id[word] for word in train_insts[b].input] + padding_seq
                word_seq = torch.tensor(word_seq).to(NetworkConfig.DEVICE)
                batch_input_seqs.append(word_seq)

            batch_input_seqs = torch.stack(batch_input_seqs, 0)

            network_id_range = (i, min(i + batch_size, len(train_insts)))

            batch = (batch_input_seqs, network_id_range)
            batches.append(batch)

        return batches

    def build_nn_graph_batch(self, batch_input_seqs):

        word_vec = self.word_embed(batch_input_seqs)
        lstm_out, _ = self.rnn(word_vec, None)
        linear_output = self.linear(lstm_out)  #batch_size, seq_len, hidden_size
        return linear_output


    def extract_helper(self, network, parent_k):
        parent_arr = network.get_node_array(parent_k)  # pos, label_id, node_type
        pos = parent_arr[0]
        label_id = parent_arr[1]
        node_type = parent_arr[2]

        if node_type == 0 or node_type == 2: #Start, End
            return torch.tensor(0.0).to(NetworkConfig.DEVICE)
        else:
            nn_output = network.nn_output
            return nn_output[pos][label_id]


    def get_label_id(self, network, parent_k):
        parent_arr = network.get_node_array(parent_k)
        return parent_arr[1]


class TagReader():
    label2id_map = {}
    label2id_map["<START>"] = 0
    @staticmethod
    def read_insts(file, is_labeled, number):
        insts = []
        inputs = []
        outputs = []
        f = open(file, 'r', encoding='utf-8')
        for line in f:
            line = line.strip()

            if len(line) == 0:
                inst = LinearInstance(len(insts) + 1, 1, inputs, outputs)
                if is_labeled:
                    inst.set_labeled()
                else:
                    inst.set_unlabeled()
                insts.append(inst)

                inputs = []
                outputs = []

                if len(insts) >= number and number > 0:
                    break

            else:
                fields = line.split()
                input = fields[0]
                input = re.sub('\d', '0', input)
                output = fields[-1]

                # if output.endswith("NP"):
                #     output = "NP"
                # else:
                #     output = "O"

                if not output in TagReader.label2id_map:
                    output_id = len(TagReader.label2id_map)
                    TagReader.label2id_map[output] = output_id
                else:
                    output_id = TagReader.label2id_map[output]

                inputs.append(input)
                outputs.append(output)

        f.close()

        return insts


if __name__ == "__main__":

    torch.manual_seed(1234)
    torch.set_num_threads(40)



    train_file = "data/conll/train.txt.bieos"
    dev_file = "data/conll/dev.txt.bieos"
    test_file = "data/conll/test.txt.bieos"
    trial_file = "data/conll/trial.txt.bieos"


    TRIAL = True
    data_size = 20
    num_iter = 3000
    batch_size = 1
    device = "cpu"
    num_thread = 1
    dev_file = test_file


    if TRIAL == True:
        data_size = -1
        train_file = trial_file
        dev_file = trial_file
        test_file = trial_file

    if device == "gpu":
        NetworkConfig.DEVICE = torch.device("cuda:1")

    if num_thread > 1:
        NetworkConfig.NUM_THREADS = num_thread
        print('Set NUM_THREADS = ', num_thread)

    train_insts = TagReader.read_insts(train_file, True, data_size)
    dev_insts = TagReader.read_insts(dev_file, False, data_size)
    test_insts = TagReader.read_insts(test_file, False, data_size)
    TagReader.label2id_map["<ROOT>"] = len(TagReader.label2id_map)
    print("map:", TagReader.label2id_map)
    #vocab2id = {'<PAD>':0}
    vocab2id = {}
    for inst in train_insts + dev_insts + test_insts:
        for word in inst.input:
            if word not in vocab2id:
                vocab2id[word] = len(vocab2id)

    for inst in train_insts + dev_insts + test_insts:
        inst.word_seq = torch.tensor([vocab2id[word] for word in inst.input]).to(NetworkConfig.DEVICE)

    print(colored('vocab_2id:', 'red'), len(vocab2id))

    gnp = TensorGlobalNetworkParam(len(TagReader.label2id_map))
    fm = TagFeatureManager(gnp, len(vocab2id))
    #fm.load_pretrain('data/glove.6B.100d.txt', vocab2id)
    print(list(TagReader.label2id_map.keys()))
    compiler = TagNetworkCompiler(TagReader.label2id_map)


    evaluator = nereval()
    model = NetworkModel(fm, compiler, evaluator)


    # def hookBFunc(m, gi, go):  # 该函数必须是function(grad)这种形式，grad的参数默认给出
    #     print(colored('Bhook:', 'green'), '\t',m)
    #     print(m, gi, go)
    #
    # model.register_backward_hook(hookBFunc)

    if batch_size == 1:
        model.learn(train_insts, num_iter, dev_insts)
    else:
        model.learn_batch(train_insts, num_iter, dev_insts, batch_size)

    results = model.test(test_insts)

    print()
    print('Result:')
    corr = 0
    total = 0
    for i in range(len(test_insts)):
        inst = results[i]
        total += inst.size()
        for pos in range(inst.size()):
            if inst.get_output()[pos] == inst.get_prediction()[pos]:
                corr += 1
        print("resulit is :", results[i].get_prediction())

    print("accuracy: ", str(corr*1.0 / total))
