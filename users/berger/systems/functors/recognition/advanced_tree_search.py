import copy
import itertools
from typing import Dict, List

from i6_core import mm, rasr, recognition, returnn
from sisyphus import tk

from ... import types
from ..base import AbstractRecognitionFunctor
from ..rasr_base import RasrFunctor


class AdvancedTreeSearchFunctor(
    AbstractRecognitionFunctor[returnn.ReturnnTrainingJob, returnn.ReturnnConfig],
    RasrFunctor,
):
    def __call__(
        self,
        train_job: types.NamedTrainJob[returnn.ReturnnTrainingJob],
        prior_config: returnn.ReturnnConfig,
        recog_config: types.NamedConfig[returnn.ReturnnConfig],
        recog_corpus: types.NamedCorpusInfo,
        num_inputs: int,
        num_classes: int,
        epochs: List[types.EpochType],
        lm_scales: List[float],
        prior_scales: List[float] = [0],
        pronunciation_scales: List[float] = [0],
        prior_args: Dict = {},
        lattice_to_ctm_kwargs: Dict = {},
        flow_args: Dict = {},
        **kwargs,
    ) -> List[Dict]:
        crp = copy.deepcopy(recog_corpus.corpus_info.crp)
        assert recog_corpus.corpus_info.scorer is not None

        acoustic_mixture_path = mm.CreateDummyMixturesJob(
            num_classes, num_inputs
        ).out_mixtures

        base_feature_flow = self._make_base_feature_flow(
            recog_corpus.corpus_info, **flow_args
        )

        recog_results = []

        for lm_scale, prior_scale, pronunciation_scale, epoch in itertools.product(
            lm_scales, prior_scales, pronunciation_scales, epochs
        ):
            tf_graph = self._make_tf_graph(
                train_job=train_job.job,
                returnn_config=recog_config.config,
                epoch=epoch,
            )
            checkpoint = self._get_checkpoint(train_job.job, epoch)
            prior_file = self._get_prior_file(
                prior_config=prior_config,
                checkpoint=checkpoint,
                **prior_args,
            )

            crp.language_model_config.scale = lm_scale  # type: ignore

            feature_scorer = rasr.PrecomputedHybridFeatureScorer(
                prior_mixtures=acoustic_mixture_path,
                priori_scale=prior_scale,
                prior_file=prior_file,
            )

            model_combination_config = rasr.RasrConfig()
            model_combination_config.pronunciation_scale = pronunciation_scale

            feature_flow = self._make_tf_feature_flow(
                base_feature_flow,
                tf_graph,
                checkpoint,
            )

            rec = recognition.AdvancedTreeSearchJob(
                crp=crp,
                feature_flow=feature_flow,
                feature_scorer=feature_scorer,
                model_combination_config=model_combination_config,
                **kwargs,
            )

            exp_full = f"{recog_config.name}_e-{self._get_epoch_string(epoch)}_pron-{pronunciation_scale:02.2f}_prior-{prior_scale:02.2f}_lm-{lm_scale:02.2f}"
            path = f"nn_recog/{recog_corpus.name}/{train_job.name}/{exp_full}"
            rec.set_vis_name(f"Recog {path}")
            rec.add_alias(path)

            scorer_job = self._lattice_scoring(
                crp=crp,
                lattice_bundle=rec.out_lattice_bundle,
                scorer=recog_corpus.corpus_info.scorer,
                **lattice_to_ctm_kwargs,
            )
            tk.register_output(
                f"{path}.reports",
                scorer_job.out_report_dir,
            )

            recog_results.append(
                {
                    types.SummaryKey.TRAIN_NAME.value: train_job.name,
                    types.SummaryKey.RECOG_NAME.value: recog_config.name,
                    types.SummaryKey.CORPUS.value: recog_corpus.name,
                    types.SummaryKey.EPOCH.value: self._get_epoch_value(
                        train_job.job, epoch
                    ),
                    types.SummaryKey.PRON.value: pronunciation_scale,
                    types.SummaryKey.PRIOR.value: prior_scale,
                    types.SummaryKey.LM.value: lm_scale,
                    types.SummaryKey.WER.value: scorer_job.out_wer,
                    types.SummaryKey.SUB.value: scorer_job.out_percent_substitution,
                    types.SummaryKey.DEL.value: scorer_job.out_percent_deletions,
                    types.SummaryKey.INS.value: scorer_job.out_percent_insertions,
                    types.SummaryKey.ERR.value: scorer_job.out_num_errors,
                }
            )

        return recog_results
