
from sisyphus import tk
from ..datasets import librispeech
from i6_core.returnn import ReturnnConfig, ReturnnTrainingJob
from returnn_common import nn


def run():
  for name, path in librispeech.librispeech_ogg_zip_dict.items():
    tk.register_output(f"librispeech/dataset/{name}", path)

  tk.register_output("librispeech/sentencepiece-2k.model", librispeech.spm_2k)

  input_dim = nn.FeatureDim("input", 40)
  time_dim = nn.SpatialDim("time")
  targets_time_dim = nn.SpatialDim("targets-time")
  output_dim = nn.FeatureDim("output", 2000)

  class Model(nn.ConformerEncoder):
    def __init__(self):
      super(Model, self).__init__(num_layers=6, num_heads=4, out_dim=nn.FeatureDim("conformer", 256))
      self.output = nn.Linear(output_dim + 1)  # +1 for blank

    def __call__(self, x: nn.Tensor, *, in_spatial_dim: nn.Dim, **kwargs) -> nn.Tensor:
      x, out_spatial_dim = super(Model, self).__call__(x, in_spatial_dim=in_spatial_dim, **kwargs)
      assert isinstance(out_spatial_dim, nn.Dim)
      if out_spatial_dim != in_spatial_dim:
        out_spatial_dim.declare_same_as(nn.SpatialDim("downsampled-time"))
      x = self.output(x)
      return x

  # TODO specaug
  model = Model()
  logits = model(
    nn.get_extern_data(nn.Data("data", dim_tags=[nn.batch_dim, time_dim, input_dim])),
    in_spatial_dim=time_dim)
  loss = nn.ctc_loss(
    logits=logits,
    targets=nn.get_extern_data(nn.Data("classes", dim_tags=[nn.batch_dim, targets_time_dim], sparse_dim=output_dim)))
  loss.mark_as_loss()
  model_py_code_str = nn.get_returnn_config().get_complete_py_code_str(model)

  returnn_train_config_dict = dict(
    use_tensorflow=True,

    **librispeech.default_dataset_config,

    batching="random",
    log_batch_size=True,
    batch_size=1000,
    max_seqs=200,
    max_seq_length={"classes": 75},

    gradient_clip=0,
    # gradient_clip_global_norm = 1.0
    optimizer={"class": "nadam", "epsilon": 1e-8},
    # debug_add_check_numerics_ops = True
    # debug_add_check_numerics_on_output = True
    # stop_on_nonfinite_train_score = False,
    tf_log_memory_usage=True,
    tf_session_opts={"gpu_options": {"allow_growth": True}},
    gradient_noise=0.0,
    learning_rate=0.001,
    learning_rate_control="newbob_multi_epoch",
    # learning_rate_control_error_measure = "dev_score_output"
    learning_rate_control_relative_error_relative_lr=True,
    learning_rate_control_min_num_epochs_per_new_lr=3,
    use_learning_rate_control_always=True,
    newbob_multi_num_epochs=librispeech.default_epoch_split,
    newbob_multi_update_interval=1,
    newbob_learning_rate_decay=0.9,
 )

  returnn_train_config = ReturnnConfig(
    returnn_train_config_dict,
    python_epilog=[
      model_py_code_str,
      # https://github.com/rwth-i6/returnn/issues/957
      # https://stackoverflow.com/a/16248113/133374
      """
import resource
import sys
try:
  resource.setrlimit(resource.RLIMIT_STACK, (2 ** 29, -1))
except Exception as exc:
  print(f"resource.setrlimit {type(exc).__name__}: {exc}")
sys.setrecursionlimit(10 ** 6)
"""
    ],
    post_config=dict(cleanup_old_models=True),
    sort_config=False,
  )
  returnn_train_job = ReturnnTrainingJob(returnn_train_config, log_verbosity=5, num_epochs=100)
  tk.register_output("librispeech/ctc-model/learning-rates", returnn_train_job.out_learning_rates)