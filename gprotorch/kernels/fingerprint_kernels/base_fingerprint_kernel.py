"""
Module for test_kernels that operate on fingerprint representations (bit vectors or count vectors).
Author: Ryan-Rhys Griffiths 2021
"""

from gpytorch.kernels import Kernel
from gpytorch.kernels.kernel import default_postprocess_script
import torch


class BitDistance(torch.nn.Module):
    r"""
    Distance module for bit vector test_kernels.
    """
    def __init__(self, postprocess_script=default_postprocess_script):
        super().__init__()
        self._postprocess = postprocess_script

    def _sim(self, x1, x2, postprocess, x1_eq_x2=False, metric='tanimoto'):
        r"""
        Computes the similarity between x1 and x2

        Args:
            :attr: `x1`: (Tensor `n x d` or `b x n x d`):
                First set of data where b is a batch dimension
            :attr: `x2`: (Tensor `m x d` or `b x m x d`):
                Second set of data where b is a batch dimension
            :attr: `postprocess` (bool):
                Whether to apply a postprocess script (default is none)
            :attr: `x1_eq_x2` (bool):
                Is x1 equal to x2
            :attr: `metric` (str):
                String specifying the similarity metric. One of ['tanimoto']

        Returns:
            (:class:`Tensor`, :class:`Tensor) corresponding to the similarity matrix between `x1` and `x2`
        """

        # Extend this list when including new metrics

        if metric not in ['tanimoto']:
            raise RuntimeError('Similarity metric not supported. Available options are \'tanimoto\'')

        # Branch for Tanimoto metric
        if metric == 'tanimoto':

            # Tanimoto distance is proportional to (<x, y>) / (||x||^2 + ||y||^2 - <x, y>) where x and y are bit vectors

            x1_norm = x1.pow(2).sum(dim=-1, keepdim=True)  # Compute the squared L2-norm of each datapoint
            if x1_eq_x2 and not x1.requires_grad and not x2.requires_grad:
                x2_norm = x1_norm
            else:
                x2_norm = x2.pow(2).sum(dim=-1, keepdim=False)

            # The following code works for both the batch and non-batch cases
            cross_product = x1.matmul(x2.transpose(-2, -1))

            # Analogue of denominator in Tanimoto formula
            denominator = x1_norm + x2_norm.squeeze(-1) - cross_product

            res = (cross_product/denominator)

            # if x1 and x2 are equal than the Tanimoto similarity is 1
            if x1_eq_x2 and not x1.requires_grad and not x2.requires_grad:
                res.diagonal(dim1=-2, dim2=-1).fill_(1)

            # Zero out negative values
            res.clamp_min_(0)
            return self._postprocess(res) if postprocess else res


class BitKernel(Kernel):
    r"""
    Base class for test_kernels that operate on bit or count vectors such as ECFP fingerprints or RDKit fragments.

    In the typical use case, test_kernels inheriting from this class will specify a similarity metric such as Tanimoto,
    MinMax etc.

   .. note::

    This kernel does not have an `outputscale` parameter. To add a scaling parameter,
    decorate this kernel with a :class:`gpytorch.test_kernels.ScaleKernel`.

    This base :class:`BitKernel` class does not include a lengthscale parameter
    :math:`\Theta`, in contrast to many common kernel functions.

    Base Attributes:
    :attr:`metric` (str):
        The similarity metric to use. One of ['tanimoto'].
    """
    def __init__(self, metric='', **kwargs):
        super().__init__(**kwargs)
        self.metric = metric

    def forward(self, x1, x2, **params):
        return self.covar_dist(x1, x2, **params)

    def covar_dist(
        self,
        x1,
        x2,
        last_dim_is_batch=False,
        dist_postprocess_func=default_postprocess_script,
        postprocess=True,
        **params,
    ):
        r"""
        This is a helper method for computing the bit vector similarity between
        all pairs of points in x1 and x2.

        Args:
            :attr:`x1` (Tensor `n x d` or `b1 x ... x bk x n x d`):
                First set of data.
            :attr:`x2` (Tensor `m x d` or `b1 x ... x bk x m x d`):
                Second set of data.
            :attr:`last_dim_is_batch` (tuple, optional):
                Is the last dimension of the data a batch dimension or not?

        Returns:
            (:class:`Tensor`, :class:`Tensor) corresponding to the distance matrix between `x1` and `x2`.
            The shape depends on the kernel's mode
            * `diag=False`
            * `diag=False` and `last_dim_is_batch=True`: (`b x d x n x n`)
            * `diag=True`
            * `diag=True` and `last_dim_is_batch=True`: (`b x d x n`)
        """
        if last_dim_is_batch:
            x1 = x1.transpose(-1, -2).unsqueeze(-1)
            x2 = x2.transpose(-1, -2).unsqueeze(-1)

        x1_eq_x2 = torch.equal(x1, x2)

        # torch scripts expect tensors
        postprocess = torch.tensor(postprocess)

        res = None

        # Cache the Distance object or else JIT will recompile every time
        if not self.distance_module or self.distance_module._postprocess != dist_postprocess_func:
            self.distance_module = BitDistance(dist_postprocess_func)

        res = self.distance_module._sim(x1, x2, postprocess, x1_eq_x2, self.metric)

        return res
