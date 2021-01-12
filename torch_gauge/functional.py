from typing import Tuple

import torch


class NormContraction1d(torch.autograd.Function):
    """
    Calculate the (stabilized) L2-norm of a 1d spherical tensor
    The representation dimension must be an integer
    The gradients at zero are enforced to be 0 by a non-negative eps
    """

    @staticmethod
    def forward(ctx, data_ten: torch.Tensor, dst_ten: torch.LongTensor, out_shape, dim, eps):
        sum_sqr = torch.zeros(out_shape, device=data_ten.device, dtype=data_ten.dtype).scatter_add_(
            dim=dim, index=dst_ten, src=data_ten.pow(2)
        )
        norm_shifted = (sum_sqr + eps.mul(eps)).sqrt()
        ctx.dim = dim
        ctx.save_for_backward(data_ten, dst_ten, norm_shifted)
        return norm_shifted - eps

    @staticmethod
    def backward(ctx, grad_output):
        data_ten, dst_ten, norm_shifted = ctx.saved_tensors
        gathered_grad_output = torch.gather(grad_output, ctx.dim, dst_ten)
        gathered_norm_shifted = torch.gather(norm_shifted, ctx.dim, dst_ten)
        norm_grad = data_ten / gathered_norm_shifted
        grad_input = gathered_grad_output * norm_grad
        return grad_input, None, None, None, None


class NormContraction2d(torch.autograd.Function):
    """
    Calculate the (stabilized) L2-norm of a 2d spherical tensor
    The representation dimensions must be a 2-tuple (i, i+1)
    """

    @staticmethod
    def forward(
        ctx,
        data_ten: torch.Tensor,
        dst_tens: Tuple[torch.LongTensor],
        out_shape,
        dims,
        eps,
    ):
        # TODO: double-check the column-first behavior
        shape_rep_out = out_shape[dims]
        cache_inds = dst_tens[0] * shape_rep_out[1] + dst_tens[1]  # flattened dst indices
        cache_inds = cache_inds.view(*cache_inds.shape[: dims[0]], -1, *cache_inds.shape[dims[1] + 1 :])
        sum_sqr = torch.zeros(
            *out_shape[: dims[0]],
            shape_rep_out[0] * shape_rep_out[1],
            *out_shape[dims[1] + 1 :],
            device=data_ten.device,
            dtype=data_ten.dtype,
        )
        sum_sqr = sum_sqr.scatter_add_(dim=dims[0], index=cache_inds, src=data_ten.pow(2))
        norm_cache_shifted = (sum_sqr + eps.mul(eps)).sqrt()
        norm_shifted = norm_cache_shifted.view(out_shape)  # must be contiguous at this point
        ctx.dims = dims
        ctx.save_for_backward(data_ten, cache_inds, norm_cache_shifted)
        return norm_shifted - eps

    @staticmethod
    def backward(ctx, grad_output):
        data_ten, cache_inds, norm_cache = ctx.saved_tensors
        dims = ctx.dims
        gathered_grad_output = torch.gather(
            grad_output.view(*grad_output.shape[: dims[0]], -1, *grad_output.shape[dims[1] + 1 :]),
            dims[0],
            cache_inds,
        )
        gathered_norm_shifted = torch.gather(norm_cache, dims[0], cache_inds)
        gathered_norm_shifted = gathered_norm_shifted.view(data_ten.shape)
        norm_grad = data_ten / gathered_norm_shifted
        grad_input = gathered_grad_output * norm_grad
        return grad_input, None, None, None, None
