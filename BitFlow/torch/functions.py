import torch as t

K = 10


class _IntRound(t.autograd.Function):

    @staticmethod
    def forward(ctx, x):
        ctx.save_for_backward(x)
        return t.round(x)

    @staticmethod
    def backward(ctx, dy):
        x = ctx.saved_tensors[0]
        rx = t.round(x)
        delta = t.abs(x-rx)
        pi = t.acos(t.zeros(1)).item() * 2

        # return 1 - t.cos(2 * pi * x)
        return (K**(4*delta-1)) * dy


IntRound = _IntRound.apply
