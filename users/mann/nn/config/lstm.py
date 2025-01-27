from collections import ChainMap

from .configs import blstm_config
from .networks import blstm_network
from .constants import (
    BASE_CRNN_CONFIG,
    BASE_LSTM_CONFIG,
    BASE_NETWORK_CONFIG,
    BASE_VITERBI_LRS,
    TINA_UPDATES_1K,
)

def blstm_network_helper(layers, dropout, l2, **_ignored):
    return blstm_network(layers, dropout, l2)

def viterbi_lstm(num_input, network_kwargs={}, **kwargs):
    kwargs = {**BASE_CRNN_CONFIG, **BASE_VITERBI_LRS, **kwargs}
    lr = kwargs.pop("lr")
    # del kwargs["dropout"], kwargs["l2"]
    network_kwargs = ChainMap(network_kwargs, BASE_LSTM_CONFIG, BASE_NETWORK_CONFIG)
    config = blstm_config(
        num_input,
        # network = blstm_network_helper(**BASE_LSTM_CONFIG, **network_kwargs),
        network = blstm_network(**network_kwargs),
        learning_rate=lr,
        **kwargs
    )
    config_ = config.config
    del config_['max_seq_length']
    config_['network']['output']['loss_opts'] = {"focal_loss_factor": 2.0}
    config_["network"]["output"]["loss"] = "ce"
    return config


def viterbi_lstm_tina(num_input, **kwargs):
    kwargs = {**BASE_CRNN_CONFIG, **BASE_VITERBI_LRS, **kwargs}
    network_kwargs = kwargs.copy()
    lr = kwargs.pop("lr")
    del kwargs["dropout"], kwargs["l2"]
    config = blstm_config(
        num_input,
        network = blstm_network_helper(**BASE_LSTM_CONFIG, **network_kwargs),
        learning_rate=lr,
        **kwargs
    )
    config_ = config.config
    del config_['max_seq_length'], config_['adam']
    config_['network']['output']['loss_opts'] = {"focal_loss_factor": 2.0}
    config_["network"]["output"]["loss"] = "ce"
    return config
