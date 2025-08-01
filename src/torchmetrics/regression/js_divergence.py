# Copyright The Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from math import log
from typing import Any, List, Optional, Sequence, Union, cast

import torch
from torch import Tensor
from typing_extensions import Literal

from torchmetrics.functional.regression.js_divergence import _jsd_compute, _jsd_update
from torchmetrics.metric import Metric
from torchmetrics.utilities.data import dim_zero_cat
from torchmetrics.utilities.imports import _MATPLOTLIB_AVAILABLE
from torchmetrics.utilities.plot import _AX_TYPE, _PLOT_OUT_TYPE

if not _MATPLOTLIB_AVAILABLE:
    __doctest_skip__ = ["JensenShannonDivergence.plot"]


class JensenShannonDivergence(Metric):
    r"""Compute the `Jensen-Shannon divergence`_.

    .. math::
        D_{JS}(P||Q) = \frac{1}{2} D_{KL}(P||M) + \frac{1}{2} D_{KL}(Q||M)

    Where :math:`P` and :math:`Q` are probability distributions where :math:`P` usually represents a distribution
    over data and :math:`Q` is often a prior or approximation of :math:`P`. :math:`D_{KL}` is the `KL divergence`_ and
    :math:`M` is the average of the two distributions. It should be noted that the Jensen-Shannon divergence is a
    symmetrical metric i.e. :math:`D_{JS}(P||Q) = D_{JS}(Q||P)`.

    As input to ``forward`` and ``update`` the metric accepts the following input:

    - ``p`` (:class:`~torch.Tensor`): a data distribution with shape ``(N, d)``
    - ``q`` (:class:`~torch.Tensor`): prior or approximate distribution with shape ``(N, d)``

    As output of ``forward`` and ``compute`` the metric returns the following output:

    - ``js_divergence`` (:class:`~torch.Tensor`): A tensor with the Jensen-Shannon divergence

    Args:
        log_prob: bool indicating if input is log-probabilities or probabilities. If given as probabilities,
            will normalize to make sure the distributes sum to 1.
        reduction:
            Determines how to reduce over the ``N``/batch dimension:

            - ``'mean'`` [default]: Averages score across samples
            - ``'sum'``: Sum score across samples
            - ``'none'`` or ``None``: Returns score per sample

        kwargs: Additional keyword arguments, see :ref:`Metric kwargs` for more info.

    Raises:
        TypeError:
            If ``log_prob`` is not an ``bool``.
        ValueError:
            If ``reduction`` is not one of ``'mean'``, ``'sum'``, ``'none'`` or ``None``.

    .. attention::
        Half precision is only support on GPU for this metric.

    Example:
        >>> from torch import tensor
        >>> from torchmetrics.regression import JensenShannonDivergence
        >>> p = tensor([[0.1, 0.9], [0.2, 0.8], [0.3, 0.7]])
        >>> q = tensor([[0.3, 0.7], [0.4, 0.6], [0.5, 0.5]])
        >>> js_div = JensenShannonDivergence()
        >>> js_div(p, q)
        tensor(0.0259)

    """

    is_differentiable: bool = True
    higher_is_better: bool = False
    full_state_update: bool = False
    plot_lower_bound: float = 0.0
    plot_upper_bound: float = log(2)

    measures: Union[Tensor, List[Tensor]]
    total: Tensor

    def __init__(
        self,
        log_prob: bool = False,
        reduction: Literal["mean", "sum", "none", None] = "mean",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not isinstance(log_prob, bool):
            raise TypeError(f"Expected argument `log_prob` to be bool but got {log_prob}")
        self.log_prob = log_prob

        allowed_reduction = ["mean", "sum", "none", None]
        if reduction not in allowed_reduction:
            raise ValueError(f"Expected argument `reduction` to be one of {allowed_reduction} but got {reduction}")
        self.reduction = reduction

        if self.reduction in ["mean", "sum"]:
            self.add_state("measures", torch.tensor(0.0), dist_reduce_fx="sum")
        else:
            self.add_state("measures", [], dist_reduce_fx="cat")
        self.add_state("total", torch.tensor(0), dist_reduce_fx="sum")

    def update(self, p: Tensor, q: Tensor) -> None:
        """Update the metric state."""
        measures, total = _jsd_update(p, q, self.log_prob)
        if self.reduction is None or self.reduction == "none":
            cast(List[Tensor], self.measures).append(measures)
        else:
            self.measures = cast(Tensor, self.measures) + measures.sum()
            self.total += total

    def compute(self) -> Tensor:
        """Compute metric."""
        measures: Tensor = (
            dim_zero_cat(cast(List[Tensor], self.measures))
            if self.reduction in ["none", None]
            else cast(Tensor, self.measures)
        )
        return _jsd_compute(measures, self.total, self.reduction)

    def plot(
        self, val: Optional[Union[Tensor, Sequence[Tensor]]] = None, ax: Optional[_AX_TYPE] = None
    ) -> _PLOT_OUT_TYPE:
        """Plot a single or multiple values from the metric.

        Args:
            val: Either a single result from calling `metric.forward` or `metric.compute` or a list of these results.
                If no value is provided, will automatically call `metric.compute` and plot that result.
            ax: An matplotlib axis object. If provided will add plot to that axis

        Returns:
            Figure and Axes object

        Raises:
            ModuleNotFoundError:
                If `matplotlib` is not installed

        .. plot::
            :scale: 75

            >>> from torch import randn
            >>> # Example plotting a single value
            >>> from torchmetrics.regression import JensenShannonDivergence
            >>> metric = JensenShannonDivergence()
            >>> metric.update(randn(10,3).softmax(dim=-1), randn(10,3).softmax(dim=-1))
            >>> fig_, ax_ = metric.plot()

        .. plot::
            :scale: 75

            >>> from torch import randn
            >>> # Example plotting multiple values
            >>> from torchmetrics.regression import JensenShannonDivergence
            >>> metric = JensenShannonDivergence()
            >>> values = []
            >>> for _ in range(10):
            ...     values.append(metric(randn(10,3).softmax(dim=-1), randn(10,3).softmax(dim=-1)))
            >>> fig, ax = metric.plot(values)

        """
        return self._plot(val, ax)
