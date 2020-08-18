from .node import Input, Constant, Dag, Add, Sub, Mul, DagNode, Select, LookupTable, BitShift, Concat, Reduce
from DagVisitor import Visitor
from .IA import Interval
from .Eval.IAEval import IAEval
from .Eval.NumEval import NumEval
from math import log2, ceil
from .Precision import PrecisionNode
from scipy.optimize import fsolve, minimize, basinhopping
from gekko import GEKKO
import torch
import copy


class BitFlowVisitor(Visitor):
    def __init__(self, node_values, calculate_IB=True):
        self.node_values = node_values
        self.errors = {}
        self.IBs = {}
        self.area_fn = ""
        self.train_MNIST = True
        if self.train_MNIST:
            self.calculate_IB = False
       # self.calculate_IB = calculate_IB

    def handleIB(self, node):
        if self.calculate_IB:
            ib = 0
            x = self.node_values[node]
            # print(f"{node}: {x}")
            if isinstance(x, Interval):
                alpha = 2 if (log2(abs(x.hi)).is_integer()) else 1
                ib = ceil(log2(max(abs(x.lo), abs(x.hi)))) + alpha
            else:
                if (x == 0.):
                    self.IBs[node.name] = 1
                elif (x < 1.):
                    self.IBs[node.name] = 0
                elif isinstance(x, list):
                    for (ind, val) in enumerate(x):
                        alpha = 2 if (log2(abs(val)).is_integer()) else 1
                        ib = ceil(log2(abs(val))) + alpha
                        self.IBs[f"{node.name}_getitem_{ind}"] = ib
                    return
                else:
                    alpha = 2 if (log2(abs(x)).is_integer()) else 1
                    ib = ceil(log2(abs(x))) + alpha
                    self.IBs[node.name] = int(ib)

    def getChildren(self, node):
        children = []
        for child_node in node.children():
            children.append(child_node)
        if len(children) == 1:
            return children[0]
        return children

    def visit_Input(self, node: Input):
        self.handleIB(node)

        if self.train_MNIST:
            error_mat = []
            for row in range(28):
                error_mat.append([])
                for col in range(28):
                    error_mat[row].append(PrecisionNode(
                        1., f"{node.name}_input_{row}_{col}", []))
            print(node.name)
            self.errors[node.name] = error_mat
            return

        if self.calculate_IB:
            val = 0
            if isinstance(self.node_values[node], Interval):
                x = self.node_values[node]
                val = max(abs(x.lo), abs(x.hi))
            else:
                val = self.node_values[node]

            self.errors[node.name] = PrecisionNode(val, node.name, [])

    def visit_Constant(self, node: Constant):
        self.handleIB(node)

        if self.calculate_IB or self.train_MNIST:
            val = self.node_values[node]
            self.errors[node.name] = PrecisionNode(val, node.name, [])

    def visit_Add(self, node: Add):
        Visitor.generic_visit(self, node)

        self.handleIB(node)

        lhs, rhs = self.getChildren(node)

        if self.calculate_IB or self.train_MNIST:
            self.errors[node.name] = self.errors[lhs.name].add(
                self.errors[rhs.name], node.name)

        if self.calculate_IB:
            self.area_fn += f"+1 * max({self.IBs[lhs.name]} + {lhs.name}, {self.IBs[rhs.name]} + {rhs.name})"
        else:
            self.area_fn += f"+1 * max({lhs.name}_ib + {lhs.name}, {rhs.name}_ib + {rhs.name})"

    def visit_Sub(self, node: Sub):
        Visitor.generic_visit(self, node)

        self.handleIB(node)
        lhs, rhs = self.getChildren(node)

        if self.calculate_IB or self.train_MNIST:
            self.errors[node.name] = self.errors[lhs.name].sub(
                self.errors[rhs.name], node.name)

        if self.calculate_IB:
            self.area_fn += f"+1 * max({self.IBs[lhs.name]} + {lhs.name}, {self.IBs[rhs.name]} + {rhs.name})"
        else:
            self.area_fn += f"+1 * max({lhs.name}_ib + {lhs.name}, {rhs.name}_ib + {rhs.name})"

    def visit_Mul(self, node: Mul):
        Visitor.generic_visit(self, node)

        self.handleIB(node)
        lhs, rhs = self.getChildren(node)

        if self.calculate_IB or self.train_MNIST:
            self.errors[node.name] = self.errors[lhs.name].mul(
                self.errors[rhs.name], node.name)

        if self.calculate_IB:
            self.area_fn += f"+1 * ({self.IBs[lhs.name]} + {lhs.name})*({self.IBs[rhs.name]} + {rhs.name})"
        else:
            self.area_fn += f"+1 * ({lhs.name}_ib + {lhs.name})*({rhs.name}_ib + {rhs.name})"

    def visit_BitShift(self, node: BitShift):
        Visitor.generic_visit(self, node)

        self.handleIB(node)
        lhs, rhs = self.getChildren(node)

        if self.calculate_IB:
            self.errors[node.name] = self.errors[lhs.name].mul(
                self.errors[rhs.name], node.name)

    def visit_Select(self, node: Select):
        Visitor.generic_visit(self, node)

        self.handleIB(node)
        input_signal = self.getChildren(node)

        if self.train_MNIST:
            self.errors[node.name] = self.errors[input_signal.name][node.index]

    def visit_Concat(self, node: Concat):
        Visitor.generic_visit(self, node)

        self.handleIB(node)
        inputs = self.getChildren(node)

        if self.train_MNIST:
            precisions = []
            for i in inputs:
                precisions.append(copy.deepcopy(self.errors[i]))
            self.errors[node.name] = precisions

    def visit_Reduce(self, node: Reduce):
        Visitor.generic_visit(self, node)

        self.handleIB(node)
        input_vector = self.getChildren(node)

        if self.train_MNIST:
            self.errors[node.name] = PrecisionNode.reduce(
                self.errors[input_vector.name], node.name)

    def visit_LookupTable(self, node: LookupTable):
        Visitor.generic_visit(self, node)

        self.handleIB(node)
        input_signal = self.getChildren(node)
        node.child = input_signal

        if self.calculate_IB:
            self.area_fn += f"+1 * (2 ** ({self.IBs[input_signal.name]} + {input_signal.name})) * ({node.name} + {self.IBs[node.name]})"
            self.errors[node.name] = PrecisionNode(
                self.errors[input_signal.name].val, node.name, self.errors[input_signal.name].error)
        else:
            self.area_fn += f"+1 * (2 ** ({input_signal.name} + {input_signal.name}_ib)) * ({node.name} + {node.name}_ib)"

        # if self.calculate_IB:
        #     self.area_fn += f"+1 * ({node.numel}) * ({node.name} + {self.IBs[node.name]})"
        # else:
        #     self.area_fn += f"+1 * ({node.numel}) * ({node.name} + {node.name}_ib)"


class BitFlowOptimizer():
    def __init__(self, evaluator, outputs):

        node_values = evaluator.node_values
        visitor = BitFlowVisitor(node_values)
        visitor.run(evaluator.dag)

        self.visitor = visitor
        self.error_fn = ""
        self.ufb_fn = ""
        self.optim_error_fn = " >= "
        for output in outputs:
            self.error_fn += f"+2**(-{outputs[output]}-1) - (" + \
                visitor.errors[output].getExecutableError() + ")"
            self.optim_error_fn = f"+ 2**(-{outputs[output]}-1)" + \
                self.optim_error_fn + \
                visitor.errors[output].getExecutableError()
            self.ufb_fn += visitor.errors[output].getExecutableUFB()
        self.area_fn = visitor.area_fn[1:]
        self.outputs = outputs

        print(f"ERROR EQ: {self.error_fn}")
        print(f"AREA EQ: {self.area_fn}")

        vars = list(visitor.node_values)
        for (i, var) in enumerate(vars):
            vars[i] = var.name
        self.vars = vars

    def calculateInitialValues(self):
        # print("CALCULATING INITIAL VALUES USING UFB METHOD...")
        # bnd = f"{-2**(-self.output_precision-1)} == 0"
        bnd = ""
        for output in self.outputs:
            bnd += f"{-2**(-self.outputs[output]-1)}"
        self.ufb_fn += bnd
        # print(f"UFB EQ: {self.ufb_fn}")
        # print(f"-----------")

        exec(f'''def UFBOptimizerFn(UFB):
             return  {self.ufb_fn}''', globals())

        sol = ceil(fsolve(UFBOptimizerFn, 0.01))
        self.initial = sol

        # m = GEKKO()
        # UFB = m.Var(value=0,integer=True)
        # m.options.IMODE=2
        # m.options.SOLVER=3
        #
        # exec(f'''def UFBOptimizerFn(UFB):
        #     return  {self.ufb_fn}''', globals())
        #
        # m.Equation(UFBOptimizerFn(UFB))
        # m.solve(disp=True)
        #
        # sol = ceil(UFB.value[0])
        # self.initial = sol
        # print(f"UFB = {sol}\n")

    def solve(self):
        self.calculateInitialValues()
        print("SOLVING AREA/ERROR...")
        # self.error_fn = f"2**(-{self.output_precision}-1)>=" + self.error_fn

        print(f"ERROR EQ: {self.optim_error_fn}")
        print(f"AREA EQ: {self.area_fn}")
        print(f"-----------")

        filtered_vars = []
        for var in self.vars:
            if var not in self.outputs:
                filtered_vars.append(var)

        exec(f'''def ErrorConstraintFn(x):
             {','.join(filtered_vars)} = x
             return  {self.error_fn}''', globals())

        exec(f'''def AreaOptimizerFn(x):
             {','.join(filtered_vars)} = x
             return  {self.area_fn}''', globals())

        x0 = [self.initial for i in range(len(filtered_vars))]
        bounds = [(0, 64) for i in range(len(filtered_vars))]

        con = {'type': 'ineq', 'fun': ErrorConstraintFn}

        # note: minimize uses SLSQP by default but I specify it to be explicit; we're using basinhopping to find the global minimum while using SLSQP to find local minima
        minimizer_kwargs = {'constraints': (
            [con]), 'bounds': bounds, 'method': "SLSQP"}
        solution = basinhopping(AreaOptimizerFn, x0,
                                minimizer_kwargs=minimizer_kwargs)

        sols = dict(zip(filtered_vars, solution.x))

        for key in sols:
            sols[key] = ceil(sols[key])
            print(f"{key}: {sols[key]}")

        self.fb_sols = sols

        # namespace = {"m": GEKKO()}
        # m = namespace["m"]
        # m.options.IMODE = 2
        # m.options.SOLVER = 3

        # filtered_vars = []
        # for var in self.vars:
        #     if var not in self.outputs:
        #         filtered_vars.append(var)

        # vars_init = ','.join(
        #     filtered_vars) + f" = [m.Var(value={self.initial}, integer=True, lb=0, ub=64) for i in range({len(filtered_vars)})]"
        # exec(vars_init, namespace)

        # exec(f'''def ErrorOptimizerFn({','.join(filtered_vars)}):
        #     return  {self.optim_error_fn}''', namespace)

        # exec(f'''def AreaOptimizerFn({','.join(filtered_vars)}):
        #     return  {self.area_fn.replace("max", "m.max2")}''', namespace)

        # params = [namespace[v] for v in filtered_vars]

        # m.Equation(namespace["ErrorOptimizerFn"](*params))
        # m.Obj(namespace["AreaOptimizerFn"](*params))
        # m.solve(disp=True)

        # sols = dict(zip(filtered_vars, params))

        # for key in sols:
        #     sols[key] = ceil(sols[key].value[0])
        #     print(f"{key}: {sols[key]}")

        # self.fb_sols = sols
