
# /work/asr3/luescher/setups-data/librispeech/best-model/960h_2019-04-10/
from sisyphus import gs, tk, Path


import os
import sys
from typing import Optional, Union, Dict

import i6_core.corpus as corpus_recipe
import i6_core.rasr as rasr
import i6_core.text as text
import i6_core.features as features
from i6_core.returnn.config import CodeWrapper
import i6_core.util

import i6_experiments.common.setups.rasr.gmm_system as gmm_system
import i6_experiments.common.setups.rasr.hybrid_system as hybrid_system
import i6_experiments.common.setups.rasr.util as rasr_util
import i6_experiments.common.datasets.librispeech as lbs_dataset

import copy
import numpy as np

import i6_core.returnn as returnn

from i6_experiments.users.luescher.helpers.search_params import get_search_parameters

# TODO remove these
import i6_experiments.users.luescher.setups.librispeech.pipeline_base_args as lbs_gmm_setups


def run():
  filename_handle = os.path.splitext(os.path.basename(__file__))[0]
  gs.ALIAS_AND_OUTPUT_SUBDIR = f"{filename_handle}/"
  rasr.flow.FlowNetwork.default_flags = {"cache_mode": "task_dependent"}

  # TODO ...

  nn_args = get_nn_args()

  nn_steps = rasr_util.RasrSteps()
  nn_steps.add_step("nn", nn_args)

  lbs_nn_system = hybrid_system.HybridSystem()
  lbs_nn_system.init_system(**get_chris_hybrid_system_init_args())
  lbs_nn_system.run(nn_steps)

  gs.ALIAS_AND_OUTPUT_SUBDIR = ""


def default_gmm_hybrid_init_args():
  # hybrid_init_args = lbs_gmm_setups.get_init_args()
  dc_detection: bool = True
  scorer: Optional[str] = None
  mfcc_filter_width: Union[float, Dict] = 268.258

  am_args = {
    "state_tying": "monophone",
    "states_per_phone": 3,
    "state_repetitions": 1,
    "across_word_model": True,
    "early_recombination": False,
    "tdp_scale": 1.0,
    "tdp_transition": (3.0, 0.0, 30.0, 0.0),  # loop, forward, skip, exit
    "tdp_silence": (0.0, 3.0, "infinity", 20.0),
    "tying_type": "global",
    "nonword_phones": "",
    "tdp_nonword": (
      0.0,
      3.0,
      "infinity",
      6.0,
    ),  # only used when tying_type = global-and-nonword
  }

  costa_args = {"eval_recordings": True, "eval_lm": False}
  default_mixture_scorer_args = {"scale": 0.3}

  mfcc_cepstrum_options = {
    "normalize": False,
    "outputs": 16,
    "add_epsilon": False,
  }

  feature_extraction_args = {
    "mfcc": {
      "num_deriv": 2,
      "num_features": None,  # 33 (confusing name: # max features, above -> clipped)
      "mfcc_options": {
        "warping_function": "mel",
        "filter_width": mfcc_filter_width,
        "normalize": True,
        "normalization_options": None,
        "without_samples": False,
        "samples_options": {
          "audio_format": "wav",
          "dc_detection": dc_detection,
        },
        "cepstrum_options": mfcc_cepstrum_options,
        "fft_options": None,
      },
    },
    "gt": {
      "gt_options": {
        "minfreq": 100,
        "maxfreq": 7500,
        "channels": 50,
        # "warp_freqbreak": 7400,
        "tempint_type": "hanning",
        "tempint_shift": 0.01,
        "tempint_length": 0.025,
        "flush_before_gap": True,
        "do_specint": False,
        "specint_type": "hanning",
        "specint_shift": 4,
        "specint_length": 9,
        "normalize": True,
        "preemphasis": True,
        "legacy_scaling": False,
        "without_samples": False,
        "samples_options": {
          "audio_format": "wav",
          "dc_detection": dc_detection,
        },
        "normalization_options": {},
      }
    },
    "energy": {
      "energy_options": {
        "without_samples": False,
        "samples_options": {
          "audio_format": "wav",
          "dc_detection": dc_detection,
        },
        "fft_options": {},
      }
    },
  }

  return rasr_util.RasrInitArgs(
    costa_args=costa_args,
    am_args=am_args,
    feature_extraction_args=feature_extraction_args,
    default_mixture_scorer_args=default_mixture_scorer_args,
    scorer=scorer,
  )


def get_data_inputs(
      train_corpus="train-other-960",
      add_unknown_phoneme_and_mapping=True,
      use_eval_data_subset: bool = False,
  ):
    corpus_object_dict = lbs_dataset.get_corpus_object_dict(
      audio_format="wav",
      output_prefix="corpora",
    )

    lm = {
      "filename": lbs_dataset.get_arpa_lm_dict()["4gram"],
      "type": "ARPA",
      "scale": 10,
    }

    use_stress_marker = False

    original_bliss_lexicon = {
      "filename": lbs_dataset.get_bliss_lexicon(
        use_stress_marker=use_stress_marker,
        add_unknown_phoneme_and_mapping=add_unknown_phoneme_and_mapping,
      ),
      "normalize_pronunciation": False,
    }

    augmented_bliss_lexicon = {
      "filename": lbs_dataset.get_g2p_augmented_bliss_lexicon_dict(
        use_stress_marker=use_stress_marker,
        add_unknown_phoneme_and_mapping=add_unknown_phoneme_and_mapping,
      )[train_corpus],
      "normalize_pronunciation": False,
    }

    train_data_inputs = {}
    dev_data_inputs = {}
    test_data_inputs = {}

    train_data_inputs[train_corpus] = rasr_util.RasrDataInput(
      corpus_object=corpus_object_dict[train_corpus],
      concurrent=300,
      lexicon=augmented_bliss_lexicon,
    )

    dev_corpus_keys = (
      ["dev-other"] if use_eval_data_subset else ["dev-clean", "dev-other"]
    )
    test_corpus_keys = [] if use_eval_data_subset else ["test-clean", "test-other"]

    for dev_key in dev_corpus_keys:
      dev_data_inputs[dev_key] = rasr_util.RasrDataInput(
        corpus_object=corpus_object_dict[dev_key],
        concurrent=20,
        lexicon=original_bliss_lexicon,
        lm=lm,
      )

    for tst_key in test_corpus_keys:
      test_data_inputs[tst_key] = rasr_util.RasrDataInput(
        corpus_object=corpus_object_dict[tst_key],
        concurrent=20,
        lexicon=original_bliss_lexicon,
        lm=lm,
      )

    return train_data_inputs, dev_data_inputs, test_data_inputs


def get_chris_hybrid_system_init_args():
    # direct paths

    hybrid_init_args = default_gmm_hybrid_init_args()

    train_data_inputs, dev_data_inputs, test_data_inputs = get_data_inputs(use_eval_data_subset=True)

    def _get_data(name: str, inputs, shuffle_data: bool = False):

        crp = rasr.CommonRasrParameters()
        rasr.crp_add_default_output(crp)
        rasr.crp_set_corpus(crp, inputs[name].corpus_object)

        crp.base = rasr.CommonRasrParameters()
        crp.base.acoustic_model_config = rasr.RasrConfig()
        crp.base.acoustic_model_config.state_tying.type = 'cart'
        crp.base.acoustic_model_config.state_tying.file = tk.Path('cart.tree.xml.gz')
        crp.base.acoustic_model_config.allophones.add_from_lexicon = True
        crp.base.acoustic_model_config.allophones.add_all = False
        crp.base.acoustic_model_config.hmm.states_per_phone = 3
        crp.base.acoustic_model_config.hmm.state_repetitions = 1
        crp.base.acoustic_model_config.hmm.across_word_model = True
        crp.base.acoustic_model_config.hmm.early_recombination = False
        crp.base.acoustic_model_config.tdp.scale = 1.0
        crp.base.acoustic_model_config.tdp['*'].loop = 3.0
        crp.base.acoustic_model_config.tdp['*'].forward = 0.0
        crp.base.acoustic_model_config.tdp['*'].skip = 30.0
        crp.base.acoustic_model_config.tdp['*'].exit = 0.0
        crp.base.acoustic_model_config.tdp.silence.loop = 0.0
        crp.base.acoustic_model_config.tdp.silence.forward = 3.0
        crp.base.acoustic_model_config.tdp.silence.skip = 'infinity'
        crp.base.acoustic_model_config.tdp.silence.exit = 20.0
        crp.base.acoustic_model_config.tdp.entry_m1.loop = 'infinity'
        crp.base.acoustic_model_config.tdp.entry_m2.loop = 'infinity'
        crp.base.acoustic_model_post_config = rasr.RasrConfig()
        crp.base.acoustic_model_post_config.allophones.add_from_file = tk.Path('allophones')

        crp.audio_format = 'wav'
        # crp.corpus_duration = 960.9000000000001
        crp.concurrent = 300

        crp.segment_path = i6_core.util.MultiPath(
            'work/i6_core/corpus/segments/SegmentCorpusJob.hWpF8egk46Sw/output/segments.$(TASK)',
            {1: tk.Path('segments.1'), 2: tk.Path('segments.2'), })

        crp.lexicon_config = rasr.RasrConfig()
        crp.lexicon_config.file = tk.Path('oov.lexicon.gz')
        crp.lexicon_config.normalize_pronunciation = False

        feature_path = rasr.FlagDependentFlowAttribute(
            "cache_mode",
            {
                "task_dependent": None,  #  ,self.feature_caches[corpus]["gt"],
                "bundle": None,  # self.feature_bundles[corpus]["gt"],
            },
        )
        feature_flow = features.basic_cache_flow(feature_path)

        return hybrid_system.ReturnnRasrDataInput(
            name="init",
            crp=crp,
            alignments=None,  # TODO
            feature_flow=feature_flow,
            features=None,
            acoustic_mixtures=None,
            feature_scorers={},
            shuffle_data=shuffle_data,
        )

    train_segments = None  # TODO
    cv_segments = None  # TODO
    devtrain_segments = None  # TODO

    nn_train_data = _get_data("train-other-960", train_data_inputs, shuffle_data=True)
    nn_train_data.update_crp_with(segment_path=train_segments, concurrent=1)
    nn_train_data_inputs = {"train-other-960.train": nn_train_data}

    nn_cv_data = _get_data("train-other-960", train_data_inputs)
    nn_cv_data.update_crp_with(segment_path=cv_segments, concurrent=1)
    nn_cv_data_inputs = {"train-other-960.cv": nn_cv_data}

    nn_devtrain_data = _get_data("train-other-960", train_data_inputs)
    nn_devtrain_data.update_crp_with(segment_path=devtrain_segments, concurrent=1)
    nn_devtrain_data_inputs = {"train-other-960.devtrain": nn_devtrain_data}
    nn_dev_data_inputs = {
        # "dev-clean": lbs_gmm_system.outputs["dev-clean"][
        #    "final"
        # ].as_returnn_rasr_data_input(),
        "dev-other": _get_data("dev-other", dev_data_inputs)
    }
    nn_test_data_inputs = {
        # "test-clean": lbs_gmm_system.outputs["test-clean"][
        #    "final"
        # ].as_returnn_rasr_data_input(),
        # "test-other": lbs_gmm_system.outputs["test-other"][
        #    "final"
        # ].as_returnn_rasr_data_input(),
    }

    return dict(
        hybrid_init_args=hybrid_init_args,
        train_data=nn_train_data_inputs,
        cv_data=nn_cv_data_inputs,
        devtrain_data=nn_devtrain_data_inputs,
        dev_data=nn_dev_data_inputs,
        test_data=nn_test_data_inputs,
        train_cv_pairing=[tuple(["train-other-960.train", "train-other-960.cv"])],
    )


def get_orig_chris_hybrid_system_init_args():
    # ******************** Settings ********************

    filename_handle = os.path.splitext(os.path.basename(__file__))[0]
    gs.ALIAS_AND_OUTPUT_SUBDIR = f"{filename_handle}/"
    rasr.flow.FlowNetwork.default_flags = {"cache_mode": "task_dependent"}

    # ******************** GMM Init ********************

    (
        train_data_inputs,
        dev_data_inputs,
        test_data_inputs,
    ) = lbs_gmm_setups.get_data_inputs(
        use_eval_data_subset=True,
    )
    hybrid_init_args = lbs_gmm_setups.get_init_args()
    mono_args = lbs_gmm_setups.get_monophone_args(allow_zero_weights=True)
    cart_args = lbs_gmm_setups.get_cart_args()
    tri_args = lbs_gmm_setups.get_triphone_args()
    vtln_args = lbs_gmm_setups.get_vtln_args(allow_zero_weights=True)
    sat_args = lbs_gmm_setups.get_sat_args(allow_zero_weights=True)
    vtln_sat_args = lbs_gmm_setups.get_vtln_sat_args()
    final_output_args = lbs_gmm_setups.get_final_output()

    steps = rasr_util.RasrSteps()
    steps.add_step("extract", hybrid_init_args.feature_extraction_args)
    steps.add_step("mono", mono_args)
    steps.add_step("cart", cart_args)
    steps.add_step("tri", tri_args)
    steps.add_step("vtln", vtln_args)
    steps.add_step("sat", sat_args)
    steps.add_step("vtln+sat", vtln_sat_args)
    steps.add_step("output", final_output_args)

    # ******************** GMM System ********************

    lbs_gmm_system = gmm_system.GmmSystem()
    lbs_gmm_system.init_system(
        hybrid_init_args=hybrid_init_args,
        train_data=train_data_inputs,
        dev_data=dev_data_inputs,
        test_data=test_data_inputs,
    )
    lbs_gmm_system.run(steps)

    train_corpus_path = lbs_gmm_system.corpora["train-other-960"].corpus_file
    total_train_num_segments = 281241
    cv_size = 3000 / total_train_num_segments

    all_segments = corpus_recipe.SegmentCorpusJob(
        train_corpus_path, 1
    ).out_single_segment_files[1]

    splitted_segments_job = corpus_recipe.ShuffleAndSplitSegmentsJob(
        all_segments, {"train": 1 - cv_size, "cv": cv_size}
    )
    train_segments = splitted_segments_job.out_segments["train"]
    cv_segments = splitted_segments_job.out_segments["cv"]
    devtrain_segments = text.TailJob(
        train_segments, num_lines=1000, zip_output=False
    ).out

    # ******************** NN Init ********************

    nn_train_data = lbs_gmm_system.outputs["train-other-960"][
        "final"
    ].as_returnn_rasr_data_input(shuffle_data=True)
    # _dump_crp(nn_train_data.crp)
    # sys.exit(1)
    nn_train_data.update_crp_with(segment_path=train_segments, concurrent=1)
    nn_train_data_inputs = {
        "train-other-960.train": nn_train_data,
    }

    nn_cv_data = lbs_gmm_system.outputs["train-other-960"][
        "final"
    ].as_returnn_rasr_data_input()
    nn_cv_data.update_crp_with(segment_path=cv_segments, concurrent=1)
    nn_cv_data_inputs = {
        "train-other-960.cv": nn_cv_data,
    }

    nn_devtrain_data = lbs_gmm_system.outputs["train-other-960"][
        "final"
    ].as_returnn_rasr_data_input()
    nn_devtrain_data.update_crp_with(segment_path=devtrain_segments, concurrent=1)
    nn_devtrain_data_inputs = {
        "train-other-960.devtrain": nn_devtrain_data,
    }
    nn_dev_data_inputs = {
        # "dev-clean": lbs_gmm_system.outputs["dev-clean"][
        #    "final"
        # ].as_returnn_rasr_data_input(),
        "dev-other": lbs_gmm_system.outputs["dev-other"][
            "final"
        ].as_returnn_rasr_data_input(),
    }
    nn_test_data_inputs = {
        # "test-clean": lbs_gmm_system.outputs["test-clean"][
        #    "final"
        # ].as_returnn_rasr_data_input(),
        # "test-other": lbs_gmm_system.outputs["test-other"][
        #    "final"
        # ].as_returnn_rasr_data_input(),
    }

    gs.ALIAS_AND_OUTPUT_SUBDIR = ""

    return dict(
        hybrid_init_args=hybrid_init_args,
        train_data=nn_train_data_inputs,
        cv_data=nn_cv_data_inputs,
        devtrain_data=nn_devtrain_data_inputs,
        dev_data=nn_dev_data_inputs,
        test_data=nn_test_data_inputs,
        train_cv_pairing=[tuple(["train-other-960.train", "train-other-960.cv"])],
    )


# from i6_experiments.users.luescher.setups.librispeech.pipeline_hybrid_args

def get_nn_args(num_outputs: int = 9001, num_epochs: int = 500):
    returnn_configs = get_returnn_configs(
        num_inputs=40, num_outputs=num_outputs, batch_size=24000, num_epochs=num_epochs
    )

    training_args = {
        "log_verbosity": 4,
        "num_epochs": num_epochs,
        "num_classes": num_outputs,
        "save_interval": 1,
        "keep_epochs": None,
        "time_rqmt": 168,
        "mem_rqmt": 7,
        "cpu_rqmt": 3,
        "partition_epochs": {"train": 20, "dev": 1},
        "use_python_control": False,
    }
    recognition_args = {
        "dev-other": {
            "epochs": list(np.arange(250, num_epochs + 1, 10)),
            "feature_flow_key": "gt",
            "prior_scales": [0.3],
            "pronunciation_scales": [6.0],
            "lm_scales": [20.0],
            "lm_lookahead": True,
            "lookahead_options": None,
            "create_lattice": True,
            "eval_single_best": True,
            "eval_best_in_lattice": True,
            "search_parameters": get_search_parameters(),
            "lattice_to_ctm_kwargs": {
                "fill_empty_segments": True,
                "best_path_algo": "bellman-ford",
            },
            "optimize_am_lm_scale": False,
            "rtf": 50,
            "mem": 8,
            "parallelize_conversion": True,
        },
    }
    test_recognition_args = None

    nn_args = rasr_util.HybridArgs(
        returnn_training_configs=returnn_configs,
        returnn_recognition_configs=returnn_configs,
        training_args=training_args,
        recognition_args=recognition_args,
        test_recognition_args=test_recognition_args,
    )

    return nn_args


def get_returnn_configs(
    num_inputs: int, num_outputs: int, batch_size: int, num_epochs: int
):
    # ******************** blstm base ********************

    base_config = {
        "use_tensorflow": True,
        "debug_print_layer_output_template": True,
        "log_batch_size": True,
        "tf_log_memory_usage": True,
        "cache_size": "0",
        "window": 1,
        "update_on_device": True,
        "extern_data": {
            "data": {"dim": num_inputs},
            "classes": {"dim": num_outputs, "sparse": True},
        },
    }
    base_post_config = {
        "cleanup_old_models": {
            "keep_last_n": 5,
            "keep_best_n": 5,
            "keep": returnn.CodeWrapper(f"list(np.arange(10, {num_epochs + 1}, 10))"),
        },
    }

    blstm_base_config = copy.deepcopy(base_config)
    blstm_base_config.update(
        {
            "batch_size": batch_size,  # {"classes": batch_size, "data": batch_size},
            "chunking": "100:50",
            "optimizer": {"class": "nadam"},
            "optimizer_epsilon": 1e-8,
            "gradient_noise": 0.1,
            "learning_rates": returnn.CodeWrapper("list(np.linspace(3e-4, 8e-4, 10))"),
            "learning_rate_control": "newbob_multi_epoch",
            "learning_rate_control_min_num_epochs_per_new_lr": 3,
            "learning_rate_control_relative_error_relative_lr": True,
            "min_learning_rate": 1e-5,
            "newbob_learning_rate_decay": 0.9,
            "newbob_multi_num_epochs": 40,
            "newbob_multi_update_interval": 1,
            "network": {
              # TODO ....
                "output": {
                    "class": "softmax",
                    "loss": "ce",
                    "dropout": 0.1,
                    "from": "data",
                },
            },
        }
    )

    blstm_base_returnn_config = returnn.ReturnnConfig(
        config=blstm_base_config,
        post_config=base_post_config,
        hash_full_python_code=True,
        python_prolog={"numpy": "import numpy as np"},
        pprint_kwargs={"sort_dicts": False},
    )

    return {
        "dummy_nn": blstm_base_returnn_config,
    }


def test_run():
    new_obj = get_chris_hybrid_system_init_args()
    orig_obj = get_orig_chris_hybrid_system_init_args()

    obj_types = (
        rasr_util.RasrInitArgs,
        rasr_util.ReturnnRasrDataInput,
        rasr.CommonRasrParameters,
    )

    def _assert_equal(prefix, orig, new):
        if orig is None and new is None:
            return
        assert type(orig) == type(new), f"{prefix} diff type: {_repr(orig)} != {_repr(new)}"
        if isinstance(orig, dict):
            _assert_equal(f"{prefix}:keys", set(orig.keys()), set(new.keys()))
            for key in orig.keys():
                _assert_equal(f"{prefix}[{key!r}]", orig[key], new[key])
            return
        if isinstance(orig, set):
            _assert_equal(f"{prefix}:sorted", sorted(orig), sorted(new))
            return
        if isinstance(orig, (list, tuple)):
            assert len(orig) == len(new), f"{prefix} diff len: {_repr(orig)} != {_repr(new)}"
            for i in range(len(orig)):
                _assert_equal(f"{prefix}[{i}]", orig[i], new[i])
            return
        if isinstance(orig, (int, float, str)):
            assert orig == new, f"{prefix} diff: {_repr(orig)} != {_repr(new)}"
            return
        if isinstance(orig, obj_types):
            orig_attribs = set(vars(orig).keys())
            new_attribs = set(vars(new).keys())
            _assert_equal(f"{prefix}:attribs", orig_attribs, new_attribs)
            for key in orig_attribs:
                _assert_equal(f"{prefix}.{key}", getattr(orig, key), getattr(new, key))
            return
        raise TypeError(f"unexpected type {type(orig)}")

    _assert_equal("obj", orig_obj, new_obj)


_valid_primitive_types = (type(None), int, float, str, bool, i6_core.util.MultiPath)


def _dump_crp(crp: rasr.CommonRasrParameters, *, _lhs=None):
    if _lhs is None:
        _lhs = "crp"
    print(f"{_lhs} = rasr.CommonRasrParameters()")
    for k, v in vars(crp).items():
        if isinstance(v, rasr.RasrConfig):
            _dump_rasr_config(f"{_lhs}.{k}", v, parent_is_config=False)
        elif isinstance(v, rasr.CommonRasrParameters):
            _dump_crp(v, _lhs=f"{_lhs}.{k}")
        elif isinstance(v, dict):
            _dump_crp_dict(f"{_lhs}.{k}", v)
        elif isinstance(v, _valid_primitive_types):
            print(f"{_lhs}.{k} = {_repr(v)}")
        else:
            raise TypeError(f"{_lhs}.{k} is type {type(v)}")


def _dump_crp_dict(lhs: str, d: dict):
    for k, v in d.items():
        if isinstance(v, rasr.RasrConfig):
            _dump_rasr_config(f"{lhs}.{k}", v, parent_is_config=False)
        elif isinstance(v, _valid_primitive_types):
            print(f"{lhs}.{k} = {_repr(v)}")
        else:
            raise TypeError(f"{lhs}.{k} is type {type(v)}")


def _dump_rasr_config(lhs: str, config: rasr.RasrConfig, *, parent_is_config: bool):
    kwargs = {}
    for k in ["prolog", "epilog"]:
        v = getattr(config, f"_{k}")
        h = getattr(config, f"_{k}_hash")
        if v:
            kwargs[k] = v
            if h != v:
                kwargs[f"{k}_hash"] = h
        else:
            assert not h
    if kwargs or not parent_is_config:
        assert config._value is None
        print(f"{lhs} = rasr.RasrConfig({', '.join(f'{k}={v!r}' for (k, v) in kwargs.items())})")
    else:
        if config._value is not None:
            print(f"{lhs} = {config._value!r}")
    for k in config:
        v = config[k]
        py_attr = k.replace("-", "_")
        if _is_valid_python_attrib_name(py_attr):
            sub_lhs = f"{lhs}.{py_attr}"
        else:
            sub_lhs = f"{lhs}[{k!r}]"
        if isinstance(v, rasr.RasrConfig):
            _dump_rasr_config(sub_lhs, v, parent_is_config=True)
        else:
            print(f"{sub_lhs} = {_repr(v)}")


def _is_valid_python_attrib_name(name: str) -> bool:
    # Very hacky. I'm sure there is some clever regexp but I don't find it and too lazy...
    class _Obj:
        pass
    obj = _Obj()
    try:
        exec(f"obj.{name} = 'ok'", {"obj": obj})
    except SyntaxError:
        return False
    assert getattr(obj, name) == "ok"
    return True


def _repr(obj):
    """
    Unfortunately some of the repr implementations are messed up, so need to use some custom here.
    """
    if isinstance(obj, tk.Path):
        return f"tk.Path({obj.path!r})"
    if isinstance(obj, i6_core.util.MultiPath):
        return _multi_path_repr(obj)
    if isinstance(obj, dict):
        return f"{{{', '.join(f'{_repr(k)}: {_repr(v)}' for (k, v) in obj.items())}}}"
    if isinstance(obj, list):
        return f"[{', '.join(f'{_repr(v)}' for v in obj)}]"
    if isinstance(obj, tuple):
        return f"({''.join(f'{_repr(v)}, ' for v in obj)})"
    return repr(obj)


def _multi_path_repr(p: i6_core.util.MultiPath):
    args = [p.path_template, p.hidden_paths, p.cached]
    if p.path_root == gs.BASE_DIR:
        args.append(CodeWrapper("gs.BASE_DIR"))
    else:
        args.append(p.path_root)
    kwargs = {}
    if p.hash_overwrite:
        kwargs["hash_overwrite"] = p.hash_overwrite
    return (
        f"MultiPath("
        f"{', '.join(f'{_repr(v)}' for v in args)}"
        f"{''.join(f', {k}={_repr(v)}' for (k, v) in kwargs.items())})")
