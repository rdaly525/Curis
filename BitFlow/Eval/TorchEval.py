from .AbstractEval import AbstractEval
from ..node import DagNode
from .torch.functions import IntRound
import torch as t

class TorchEval(AbstractEval):
    def eval_Constant(self, node: DagNode):
        return t.Tensor([node.value])

    def eval_Add(self, a, b, node: DagNode):
        return a + b

    def eval_Sub(self, a, b, node: DagNode):
        return a - b

    def eval_Mul(self, a, b, node: DagNode):
        return a * b

    def eval_Round(self, a, prec, node: DagNode):
        scale = 2.0**prec
        return IntRound(a * scale) / scale
