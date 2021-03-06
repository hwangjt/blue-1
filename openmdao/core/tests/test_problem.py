""" Unit tests for the problem interface."""

import unittest
import warnings
from six import assertRaisesRegex

import numpy as np

from openmdao.core.group import get_relevant_vars
from openmdao.api import Problem, Group, IndepVarComp, PETScVector, NonlinearBlockGS, ScipyOptimizer, \
     ExecComp, Group, NewtonSolver, ImplicitComponent, ScipyKrylov
from openmdao.devtools.testutil import assert_rel_error

from openmdao.test_suite.components.paraboloid import Paraboloid
from openmdao.test_suite.components.sellar import SellarDerivatives, SellarDerivativesConnected


class TestProblem(unittest.TestCase):

    def test_feature_simple_run_once_no_promote(self):
        from openmdao.api import Problem, Group, IndepVarComp
        from openmdao.test_suite.components.paraboloid import Paraboloid

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 3.0))
        model.add_subsystem('p2', IndepVarComp('y', -4.0))
        model.add_subsystem('comp', Paraboloid())

        model.connect('p1.x', 'comp.x')
        model.connect('p2.y', 'comp.y')

        prob.setup()
        prob.run_model()

        assert_rel_error(self, prob['comp.f_xy'], -15.0)


    def test_feature_simple_run_once_input_input(self):
        from openmdao.api import Problem, Group, IndepVarComp
        from openmdao.test_suite.components.paraboloid import Paraboloid

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 3.0))

        #promote the two inputs to the same name
        model.add_subsystem('comp1', Paraboloid(), promotes_inputs=['x'])
        model.add_subsystem('comp2', Paraboloid(), promotes_inputs=['x'])

        #connect the source to the common name
        model.connect('p1.x', 'x')

        prob.setup()
        prob.run_model()

        assert_rel_error(self, prob['comp1.f_xy'], 13.0)
        assert_rel_error(self, prob['comp2.f_xy'], 13.0)

    def test_feature_simple_run_once_compute_totals(self):
        from openmdao.api import Problem, Group, IndepVarComp
        from openmdao.test_suite.components.paraboloid import Paraboloid

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 3.0))
        model.add_subsystem('p2', IndepVarComp('y', -4.0))
        model.add_subsystem('comp', Paraboloid())

        model.connect('p1.x', 'comp.x')
        model.connect('p2.y', 'comp.y')

        prob.setup()
        prob.run_model()

        assert_rel_error(self, prob['comp.f_xy'], -15.0)

        prob.compute_totals(of=['comp.f_xy'], wrt=['p1.x', 'p2.y'])

    def test_feature_simple_run_once_set_deriv_mode(self):
        from openmdao.api import Problem, Group, IndepVarComp
        from openmdao.test_suite.components.paraboloid import Paraboloid

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 3.0))
        model.add_subsystem('p2', IndepVarComp('y', -4.0))
        model.add_subsystem('comp', Paraboloid())

        model.connect('p1.x', 'comp.x')
        model.connect('p2.y', 'comp.y')

        prob.setup(mode='rev')
        #prob.setup(mode='fwd')
        prob.run_model()

        assert_rel_error(self, prob['comp.f_xy'], -15.0)

        prob.compute_totals(of=['comp.f_xy'], wrt=['p1.x', 'p2.y'])

    def test_set_2d_array(self):
        import numpy as np

        from openmdao.api import Problem, IndepVarComp, Group

        prob = Problem(model=Group())
        model = prob.model
        model.add_subsystem(name='indeps',
                            subsys=IndepVarComp(name='X_c', shape=(3, 1)))
        prob.setup()

        new_val = -5*np.ones((3, 1))
        prob['indeps.X_c'] = new_val
        prob.final_setup()

        assert_rel_error(self, prob['indeps.X_c'], new_val, 1e-10)

        new_val = 2.5*np.ones(3)
        prob['indeps.X_c'][:, 0] = new_val
        prob.final_setup()

        assert_rel_error(self, prob['indeps.X_c'], new_val.reshape((3,1)), 1e-10)
        assert_rel_error(self, prob['indeps.X_c'][:, 0], new_val, 1e-10)

    def test_set_checks_shape(self):

        model = Group()

        indep = model.add_subsystem('indep', IndepVarComp())
        indep.add_output('num')
        indep.add_output('arr', shape=(10, 1))

        prob = Problem(model)
        prob.setup()

        msg = "Incompatible shape for '.*': Expected (.*) but got (.*)"

        # check valid scalar value
        new_val = -10.
        prob['indep.num'] = new_val
        assert_rel_error(self, prob['indep.num'], new_val, 1e-10)

        # check bad scalar value
        bad_val = -10*np.ones((10))
        prob['indep.num'] = bad_val
        with assertRaisesRegex(self, ValueError, msg):
            prob.final_setup()
        prob._initial_condition_cache = {}

        # check assign scalar to array
        arr_val = new_val*np.ones((10, 1))
        prob['indep.arr'] = new_val
        prob.final_setup()
        assert_rel_error(self, prob['indep.arr'], arr_val, 1e-10)

        # check valid array value
        new_val = -10*np.ones((10, 1))
        prob['indep.arr'] = new_val
        assert_rel_error(self, prob['indep.arr'], new_val, 1e-10)

        # check bad array value
        bad_val = -10*np.ones((10))
        with assertRaisesRegex(self, ValueError, msg):
            prob['indep.arr'] = bad_val

        # check valid list value
        new_val = new_val.tolist()
        prob['indep.arr'] = new_val
        assert_rel_error(self, prob['indep.arr'], new_val, 1e-10)

        # check bad list value
        bad_val = bad_val.tolist()
        with assertRaisesRegex(self, ValueError, msg):
            prob['indep.arr'] = bad_val

    def test_compute_totals_basic(self):
        # Basic test for the method using default solvers on simple model.

        prob = Problem()
        model = prob.model = Group()
        model.add_subsystem('p1', IndepVarComp('x', 0.0), promotes=['x'])
        model.add_subsystem('p2', IndepVarComp('y', 0.0), promotes=['y'])
        model.add_subsystem('comp', Paraboloid(), promotes=['x', 'y', 'f_xy'])

        prob.setup(check=False, mode='fwd')
        prob.set_solver_print(level=0)
        prob.run_model()

        of = ['f_xy']
        wrt = ['x', 'y']
        derivs = prob.compute_totals(of=of, wrt=wrt)

        assert_rel_error(self, derivs['f_xy', 'x'], [[-6.0]], 1e-6)
        assert_rel_error(self, derivs['f_xy', 'y'], [[8.0]], 1e-6)

        prob.setup(check=False, mode='rev')
        prob.run_model()

        of = ['f_xy']
        wrt = ['x', 'y']
        derivs = prob.compute_totals(of=of, wrt=wrt)

        assert_rel_error(self, derivs['f_xy', 'x'], [[-6.0]], 1e-6)
        assert_rel_error(self, derivs['f_xy', 'y'], [[8.0]], 1e-6)

    def test_compute_totals_basic_return_dict(self):
        # Make sure 'dict' return_format works.

        prob = Problem()
        model = prob.model = Group()
        model.add_subsystem('p1', IndepVarComp('x', 0.0), promotes=['x'])
        model.add_subsystem('p2', IndepVarComp('y', 0.0), promotes=['y'])
        model.add_subsystem('comp', Paraboloid(), promotes=['x', 'y', 'f_xy'])

        prob.setup(check=False, mode='fwd')
        prob.set_solver_print(level=0)
        prob.run_model()

        of = ['f_xy']
        wrt = ['x', 'y']
        derivs = prob.compute_totals(of=of, wrt=wrt, return_format='dict')

        assert_rel_error(self, derivs['f_xy']['x'], [[-6.0]], 1e-6)
        assert_rel_error(self, derivs['f_xy']['y'], [[8.0]], 1e-6)

        prob.setup(check=False, mode='rev')
        prob.run_model()

        of = ['f_xy']
        wrt = ['x', 'y']
        derivs = prob.compute_totals(of=of, wrt=wrt, return_format='dict')

        assert_rel_error(self, derivs['f_xy']['x'], [[-6.0]], 1e-6)
        assert_rel_error(self, derivs['f_xy']['y'], [[8.0]], 1e-6)

    def test_feature_set_indeps(self):
        from openmdao.api import Problem, Group, IndepVarComp
        from openmdao.test_suite.components.paraboloid import Paraboloid

        prob = Problem()

        model = prob.model = Group()
        model.add_subsystem('p1', IndepVarComp('x', 0.0), promotes=['x'])
        model.add_subsystem('p2', IndepVarComp('y', 0.0), promotes=['y'])
        model.add_subsystem('comp', Paraboloid(), promotes=['x', 'y', 'f_xy'])

        prob.setup()

        prob['x'] = 2.
        prob['y'] = 10.
        prob.run_model()
        assert_rel_error(self, prob['f_xy'], 214.0, 1e-6)

    def test_feature_numpyvec_setup(self):
        from openmdao.api import Problem, Group, IndepVarComp
        from openmdao.test_suite.components.paraboloid import Paraboloid

        prob = Problem()
        model = prob.model = Group()
        model.add_subsystem('p1', IndepVarComp('x', 0.0), promotes=['x'])
        model.add_subsystem('p2', IndepVarComp('y', 0.0), promotes=['y'])
        model.add_subsystem('comp', Paraboloid(), promotes=['x', 'y', 'f_xy'])

        prob.setup()

        prob['x'] = 2.
        prob['y'] = 10.
        prob.run_model()
        assert_rel_error(self, prob['f_xy'], 214.0, 1e-6)

        prob['x'] = 0.
        prob['y'] = 0.
        prob.run_model()
        assert_rel_error(self, prob['f_xy'], 22.0, 1e-6)

        # skip the setup error checking
        prob.setup(check=False)
        prob['x'] = 4
        prob['y'] = 8.

        prob.run_model()
        assert_rel_error(self, prob['f_xy'], 174.0, 1e-6)

    @unittest.skipUnless(PETScVector, "PETSc is required.")
    def test_feature_petsc_setup(self):
        from openmdao.api import Problem, Group, IndepVarComp, PETScVector
        from openmdao.test_suite.components.paraboloid import Paraboloid

        prob = Problem()
        model = prob.model = Group()
        model.add_subsystem('p1', IndepVarComp('x', 0.0), promotes=['x'])
        model.add_subsystem('p2', IndepVarComp('y', 0.0), promotes=['y'])
        model.add_subsystem('comp', Paraboloid(), promotes=['x', 'y', 'f_xy'])

        # use PETScVector when using any PETSc linear solvers or running under MPI
        prob.setup(vector_class=PETScVector)
        prob['x'] = 2.
        prob['y'] = 10.

        prob.run_model()
        assert_rel_error(self, prob['f_xy'], 214.0, 1e-6)

    def test_feature_check_totals_manual(self):
        from openmdao.api import Problem, NonlinearBlockGS
        from openmdao.test_suite.components.sellar import SellarDerivatives

        prob = Problem()
        prob.model = SellarDerivatives()
        prob.model.nonlinear_solver = NonlinearBlockGS()

        prob.setup()
        prob.run_model()

        # manually specify which derivatives to check
        prob.check_totals(of=['obj', 'con1'], wrt=['x', 'z'])

    def test_feature_check_totals_from_driver_compact(self):
        from openmdao.api import Problem, NonlinearBlockGS
        from openmdao.test_suite.components.sellar import SellarDerivatives

        prob = Problem()
        prob.model = SellarDerivatives()
        prob.model.nonlinear_solver = NonlinearBlockGS()

        prob.model.add_design_var('x', lower=-100, upper=100)
        prob.model.add_design_var('z', lower=-100, upper=100)
        prob.model.add_objective('obj')
        prob.model.add_constraint('con1', upper=0.0)
        prob.model.add_constraint('con2', upper=0.0)

        prob.setup()

        # We don't call run_driver() here because we don't
        # actually want the optimizer to run
        prob.run_model()

        # check derivatives of all obj+constraints w.r.t all design variables
        prob.check_totals(compact_print=True)

    def test_feature_check_totals_from_driver(self):
        from openmdao.api import Problem, NonlinearBlockGS
        from openmdao.test_suite.components.sellar import SellarDerivatives

        prob = Problem()
        prob.model = SellarDerivatives()
        prob.model.nonlinear_solver = NonlinearBlockGS()

        prob.model.add_design_var('x', lower=-100, upper=100)
        prob.model.add_design_var('z', lower=-100, upper=100)
        prob.model.add_objective('obj')
        prob.model.add_constraint('con1', upper=0.0)
        prob.model.add_constraint('con2', upper=0.0)

        prob.setup()

        # We don't call run_driver() here because we don't
        # actually want the optimizer to run
        prob.run_model()

        # check derivatives of all obj+constraints w.r.t all design variables
        prob.check_totals()

    def test_feature_check_totals_suppress(self):
        from openmdao.api import Problem, NonlinearBlockGS
        from openmdao.test_suite.components.sellar import SellarDerivatives

        prob = Problem()
        prob.model = SellarDerivatives()
        prob.model.nonlinear_solver = NonlinearBlockGS()

        prob.model.add_design_var('x', lower=-100, upper=100)
        prob.model.add_design_var('z', lower=-100, upper=100)
        prob.model.add_objective('obj')
        prob.model.add_constraint('con1', upper=0.0)
        prob.model.add_constraint('con2', upper=0.0)

        prob.setup()

        # We don't call run_driver() here because we don't
        # actually want the optimizer to run
        prob.run_model()

        # check derivatives of all obj+constraints w.r.t all design variables
        totals = prob.check_totals(suppress_output=True)
        print(totals)

    def test_feature_check_totals_cs(self):
        from openmdao.api import Problem, NonlinearBlockGS
        from openmdao.test_suite.components.sellar import SellarDerivatives

        prob = Problem()
        prob.model = SellarDerivatives()
        prob.model.nonlinear_solver = NonlinearBlockGS()

        prob.model.add_design_var('x', lower=-100, upper=100)
        prob.model.add_design_var('z', lower=-100, upper=100)
        prob.model.add_objective('obj')
        prob.model.add_constraint('con1', upper=0.0)
        prob.model.add_constraint('con2', upper=0.0)

        prob.setup(force_alloc_complex=True)

        # We don't call run_driver() here because we don't
        # actually want the optimizer to run
        prob.run_model()

        # check derivatives with complex step and a larger step size.
        prob.check_totals(method='cs', step=1.0e-1)

    def test_feature_run_driver(self):
        import numpy as np

        from openmdao.api import Problem, NonlinearBlockGS, ScipyOptimizer
        from openmdao.test_suite.components.sellar import SellarDerivatives

        prob = Problem()
        model = prob.model = SellarDerivatives()
        model.nonlinear_solver = NonlinearBlockGS()

        prob.driver = ScipyOptimizer()
        prob.driver.options['optimizer'] = 'SLSQP'
        prob.driver.options['tol'] = 1e-9

        model.add_design_var('z', lower=np.array([-10.0, 0.0]), upper=np.array([10.0, 10.0]))
        model.add_design_var('x', lower=0.0, upper=10.0)
        model.add_objective('obj')
        model.add_constraint('con1', upper=0.0)
        model.add_constraint('con2', upper=0.0)

        prob.setup()
        prob.run_driver()

        assert_rel_error(self, prob['x'], 0.0, 1e-5)
        assert_rel_error(self, prob['y1'], 3.160000, 1e-2)
        assert_rel_error(self, prob['y2'], 3.755278, 1e-2)
        assert_rel_error(self, prob['z'], [1.977639, 0.000000], 1e-2)
        assert_rel_error(self, prob['obj'], 3.18339395, 1e-2)

    def test_feature_promoted_sellar_set_get_outputs(self):
        from openmdao.api import Problem, NonlinearBlockGS
        from openmdao.test_suite.components.sellar import SellarDerivatives

        prob = Problem()
        prob.model = SellarDerivatives()
        prob.model.nonlinear_solver = NonlinearBlockGS()

        prob.setup()

        prob['x'] = 2.75

        prob.run_model()

        assert_rel_error(self, prob['x'], 2.75, 1e-6)

        assert_rel_error(self, prob['y1'], 27.3049178437, 1e-6)

    def test_feature_not_promoted_sellar_set_get_outputs(self):
        from openmdao.api import Problem, NonlinearBlockGS
        from openmdao.test_suite.components.sellar import SellarDerivativesConnected

        prob = Problem()
        prob.model = SellarDerivativesConnected()
        prob.model.nonlinear_solver = NonlinearBlockGS()

        prob.setup()

        prob['px.x'] = 2.75

        prob.run_model()

        assert_rel_error(self, prob['px.x'], 2.75, 1e-6)

        assert_rel_error(self, prob['d1.y1'], 27.3049178437, 1e-6)

    def test_feature_promoted_sellar_set_get_inputs(self):
        from openmdao.api import Problem, NonlinearBlockGS
        from openmdao.test_suite.components.sellar import SellarDerivatives

        prob = Problem()
        prob.model = SellarDerivatives()
        prob.model.nonlinear_solver = NonlinearBlockGS()

        prob.setup()

        prob['x'] = 2.75

        prob.run_model()

        assert_rel_error(self, prob['x'], 2.75, 1e-6)

        # the output variable, referenced by the promoted name
        assert_rel_error(self, prob['y1'], 27.3049178437, 1e-6)
        # the connected input variable, referenced by the absolute path
        assert_rel_error(self, prob['d2.y1'], 27.3049178437, 1e-6)

    def test_feature_set_get_array(self):
        import numpy as np

        from openmdao.api import Problem, NonlinearBlockGS
        from openmdao.test_suite.components.sellar import SellarDerivatives

        prob = Problem()
        prob.model = SellarDerivatives()
        prob.model.nonlinear_solver = NonlinearBlockGS()

        prob.setup()

        # default value from the class definition
        assert_rel_error(self, prob['x'], 1.0, 1e-6)
        prob['x'] = 2.75
        assert_rel_error(self, prob['x'], 2.75, 1e-6)

        assert_rel_error(self, prob['z'], [5.0, 2.0], 1e-6)
        prob['z'] = [1.5, 1.5]  # for convenience we convert the list to an array.
        assert_rel_error(self, prob['z'], [1.5, 1.5], 1e-6)
        prob['z'] = [1.5, 1.5]  # for convenience we convert the list to an array.
        assert_rel_error(self, prob['z'], (1.5, 1.5), 1e-6)

        prob.run_model()
        assert_rel_error(self, prob['y1'], 5.43379016853, 1e-6)
        assert_rel_error(self, prob['y2'], 5.33104915618, 1e-6)

        prob['z'] = np.array([2.5, 2.5])
        assert_rel_error(self, prob['z'], [2.5, 2.5], 1e-6)

        prob.run_model()
        assert_rel_error(self, prob['y1'], 9.87161739688, 1e-6)
        assert_rel_error(self, prob['y2'], 8.14191301549, 1e-6)

    def test_feature_residuals(self):
        from openmdao.api import Problem, NonlinearBlockGS
        from openmdao.test_suite.components.sellar import SellarDerivatives

        prob = Problem()
        prob.model = SellarDerivatives()
        prob.model.nonlinear_solver = NonlinearBlockGS()

        prob.setup()

        # default value from the class definition

        prob['z'] = [1.5, 1.5]  # for convenience we convert the list to an array.
        prob.run_model()

        inputs, outputs, residuals = prob.model.get_nonlinear_vectors()

        self.assertLess(residuals['y1'], 1e-6)
        self.assertLess(residuals['y2'], 1e-6)

    def test_setup_bad_mode(self):
        # Test error message when passing bad mode to setup.

        prob = Problem()

        try:
            prob.setup(mode='junk')
        except ValueError as err:
            msg = "Unsupported mode: 'junk'. Use either 'fwd' or 'rev'."
            self.assertEqual(str(err), msg)
        else:
            self.fail('Expecting ValueError')

    def test_setup_bad_mode_direction_fwd(self):

        prob = Problem()
        prob.model.add_subsystem("indep", IndepVarComp("x", np.ones(99)))
        prob.model.add_subsystem("C1", ExecComp("y=2.0*x", x=np.zeros(10), y=np.zeros(10)))

        prob.model.connect("indep.x", "C1.x", src_indices=list(range(10)))

        prob.model.add_design_var("indep.x")
        prob.model.add_objective("C1.y")

        prob.setup(mode='fwd')

        with warnings.catch_warnings(record=True) as w:
            prob.final_setup()

        self.assertEqual(len(w), 1)
        self.assertTrue(issubclass(w[0].category, RuntimeWarning))
        self.assertEqual(str(w[0].message),
                         "Inefficient choice of derivative mode.  "
                         "You chose 'fwd' for a problem with 99 design variables and 10 "
                         "response variables (objectives and constraints).")

    def test_setup_bad_mode_direction_rev(self):

        prob = Problem()
        prob.model.add_subsystem("indep", IndepVarComp("x", np.ones(10)))
        prob.model.add_subsystem("C1", ExecComp("y=2.0*x", x=np.zeros(10), y=np.zeros(10)))
        prob.model.add_subsystem("C2", ExecComp("y=2.0*x", x=np.zeros(10), y=np.zeros(10)))

        prob.model.connect("indep.x", ["C1.x", "C2.x"])

        prob.model.add_design_var("indep.x")
        prob.model.add_constraint("C1.y")
        prob.model.add_constraint("C2.y")

        prob.setup(mode='rev')

        with warnings.catch_warnings(record=True) as w:
            prob.final_setup()

        self.assertEqual(len(w), 1)
        self.assertTrue(issubclass(w[0].category, RuntimeWarning))
        self.assertEqual(str(w[0].message),
                         "Inefficient choice of derivative mode.  "
                         "You chose 'rev' for a problem with 10 design variables and 20 "
                         "response variables (objectives and constraints).")

    def test_run_before_setup(self):
        # Test error message when running before setup.

        prob = Problem()

        try:
            prob.run_model()
        except RuntimeError as err:
            msg = "The `setup` method must be called before `run_model`."
            self.assertEqual(str(err), msg)
        else:
            self.fail('Expecting RuntimeError')

        try:
            prob.run_driver()
        except RuntimeError as err:
            msg = "The `setup` method must be called before `run_driver`."
            self.assertEqual(str(err), msg)
        else:
            self.fail('Expecting RuntimeError')

    def test_root_deprecated(self):
        # testing the root property
        msg = "The 'root' property provides backwards compatibility " \
            + "with OpenMDAO <= 1.x ; use 'model' instead."

        prob = Problem()

        # check deprecation on setter
        with warnings.catch_warnings(record=True) as w:
            prob.root = Group()

        self.assertEqual(len(w), 1)
        self.assertTrue(issubclass(w[0].category, DeprecationWarning))
        self.assertEqual(str(w[0].message), msg)

        # check deprecation on getter
        with warnings.catch_warnings(record=True) as w:
            prob.root

        self.assertEqual(len(w), 1)
        self.assertTrue(issubclass(w[0].category, DeprecationWarning))
        self.assertEqual(str(w[0].message), msg)

        # testing the root kwarg
        with self.assertRaises(ValueError) as cm:
            prob = Problem(root=Group(), model=Group())
        err = cm.exception
        self.assertEqual(str(err), "cannot specify both `root` and `model`. `root` has been "
                         "deprecated, please use model")

        with warnings.catch_warnings(record=True) as w:
            prob = Problem(root=Group)

        self.assertEqual(str(w[0].message), "The 'root' argument provides backwards "
                         "compatibility with OpenMDAO <= 1.x ; use 'model' instead.")

    def test_relevance(self):
        p = Problem()
        model = p.model

        indep1 = model.add_subsystem("indep1", IndepVarComp('x', 1.0))
        G1 = model.add_subsystem('G1', Group())
        G1.add_subsystem('C1', ExecComp(['x=2.0*a', 'y=2.0*b', 'z=2.0*a']))
        G1.add_subsystem('C2', ExecComp(['x=2.0*a', 'y=2.0*b', 'z=2.0*b']))
        model.add_subsystem("C3", ExecComp(['x=2.0*a', 'y=2.0*b+3.0*c']))
        model.add_subsystem("C4", ExecComp(['x=2.0*a', 'y=2.0*b']))
        indep2 = model.add_subsystem("indep2", IndepVarComp('x', 1.0))
        G2 = model.add_subsystem('G2', Group())
        G2.add_subsystem('C5', ExecComp(['x=2.0*a', 'y=2.0*b+3.0*c']))
        G2.add_subsystem('C6', ExecComp(['x=2.0*a', 'y=2.0*b+3.0*c']))
        G2.add_subsystem('C7', ExecComp(['x=2.0*a', 'y=2.0*b']))
        model.add_subsystem("C8", ExecComp(['y=1.5*a+2.0*b']))
        model.add_subsystem("Unconnected", ExecComp('y=99.*x'))

        model.connect('indep1.x', 'G1.C1.a')
        model.connect('indep2.x', 'G2.C6.a')
        model.connect('G1.C1.x', 'G1.C2.b')
        model.connect('G1.C2.z', 'C4.b')
        model.connect('G1.C1.z', ('C3.b', 'C3.c', 'G2.C5.a'))
        model.connect('C3.y', 'G2.C5.b')
        model.connect('C3.x', 'C4.a')
        model.connect('G2.C6.y', 'G2.C7.b')
        model.connect('G2.C5.x', 'C8.b')
        model.connect('G2.C7.x', 'C8.a')

        p.setup(check=False, mode='rev')

        g = p.model.compute_sys_graph(comps_only=True)
        relevant = get_relevant_vars(g, ['indep1.x', 'indep2.x'], ['C8.y', 'Unconnected.y'],
                                     mode='rev')

        indep1_ins = set(['C3.b', 'C3.c', 'C8.b', 'G1.C1.a', 'G2.C5.a', 'G2.C5.b'])
        indep1_outs = set(['C3.y', 'C8.y', 'G1.C1.z', 'G2.C5.x', 'indep1.x'])
        indep1_sys = set(['C3', 'C8', 'G1.C1', 'G2.C5', 'indep1', 'G1', 'G2', ''])

        dct, systems = relevant['C8.y']['indep1.x']
        inputs = dct['input']
        outputs = dct['output']

        self.assertEqual(inputs, indep1_ins)
        self.assertEqual(outputs, indep1_outs)
        self.assertEqual(systems, indep1_sys)

        dct, systems = relevant['C8.y']['indep1.x']
        inputs = dct['input']
        outputs = dct['output']

        self.assertEqual(inputs, indep1_ins)
        self.assertEqual(outputs, indep1_outs)
        self.assertEqual(systems, indep1_sys)

        indep2_ins = set(['C8.a', 'G2.C6.a', 'G2.C7.b'])
        indep2_outs = set(['C8.y', 'G2.C6.y', 'G2.C7.x', 'indep2.x'])
        indep2_sys = set(['C8', 'G2.C6', 'G2.C7', 'indep2', 'G2', ''])

        dct, systems = relevant['C8.y']['indep2.x']
        inputs = dct['input']
        outputs = dct['output']

        self.assertEqual(inputs, indep2_ins)
        self.assertEqual(outputs, indep2_outs)
        self.assertEqual(systems, indep2_sys)

        dct, systems = relevant['C8.y']['indep2.x']
        inputs = dct['input']
        outputs = dct['output']

        self.assertEqual(inputs, indep2_ins)
        self.assertEqual(outputs, indep2_outs)
        self.assertEqual(systems, indep2_sys)

        dct, systems = relevant['C8.y']['@all']
        inputs = dct['input']
        outputs = dct['output']

        self.assertEqual(inputs, indep1_ins | indep2_ins)
        self.assertEqual(outputs, indep1_outs | indep2_outs)
        self.assertEqual(systems, indep1_sys | indep2_sys)

    def test_system_setup_and_configure(self):
        # Test that we can change solver settings on a subsystem in a system's setup method.
        # Also assures that highest system's settings take precedence.

        class ImplSimple(ImplicitComponent):

            def setup(self):
                self.add_input('a', val=1.)
                self.add_output('x', val=0.)

            def apply_nonlinear(self, inputs, outputs, residuals):
                residuals['x'] = np.exp(outputs['x']) - \
                    inputs['a']**2 * outputs['x']**2

            def linearize(self, inputs, outputs, jacobian):
                jacobian['x', 'x'] = np.exp(outputs['x']) - \
                    2 * inputs['a']**2 * outputs['x']
                jacobian['x', 'a'] = -2 * inputs['a'] * outputs['x']**2


        class Sub(Group):

            def setup(self):
                self.add_subsystem('comp', ImplSimple())

                # This will not solve it
                self.nonlinear_solver = NonlinearBlockGS()

            def configure(self):
                # This will not solve it either.
                self.nonlinear_solver = NonlinearBlockGS()


        class Super(Group):

            def setup(self):
                self.add_subsystem('sub', Sub())

            def configure(self):
                # This will solve it.
                self.sub.nonlinear_solver = NewtonSolver()
                self.sub.linear_solver = ScipyKrylov()


        top = Problem()
        top.model = Super()

        top.setup(check=False)

        self.assertTrue(isinstance(top.model.sub.nonlinear_solver, NewtonSolver))
        self.assertTrue(isinstance(top.model.sub.linear_solver, ScipyKrylov))

    def test_post_setup_solver_configure(self):
        # Test that we can change solver settings after we have instantiated our model.

        class ImplSimple(ImplicitComponent):

            def setup(self):
                self.add_input('a', val=1.)
                self.add_output('x', val=0.)

            def apply_nonlinear(self, inputs, outputs, residuals):
                residuals['x'] = np.exp(outputs['x']) - \
                    inputs['a']**2 * outputs['x']**2

            def linearize(self, inputs, outputs, jacobian):
                jacobian['x', 'x'] = np.exp(outputs['x']) - \
                    2 * inputs['a']**2 * outputs['x']
                jacobian['x', 'a'] = -2 * inputs['a'] * outputs['x']**2


        class Sub(Group):

            def setup(self):
                self.add_subsystem('comp', ImplSimple())

                # This solver will get over-ridden below
                self.nonlinear_solver = NonlinearBlockGS()

            def configure(self):
                # This solver will get over-ridden below
                self.nonlinear_solver = NonlinearBlockGS()


        class Super(Group):

            def setup(self):
                self.add_subsystem('sub', Sub())


        top = Problem()
        top.model = Super()

        top.setup(check=False)

        # These solvers override the ones set in the setup method of the 'sub' groups
        top.model.sub.nonlinear_solver = NewtonSolver()
        top.model.sub.linear_solver = ScipyKrylov()

        self.assertTrue(isinstance(top.model.sub.nonlinear_solver, NewtonSolver))
        self.assertTrue(isinstance(top.model.sub.linear_solver, ScipyKrylov))

    def test_feature_system_configure(self):
        from openmdao.api import Problem, Group, ImplicitComponent, NewtonSolver, ScipyKrylov, NonlinearBlockGS

        class ImplSimple(ImplicitComponent):

            def setup(self):
                self.add_input('a', val=1.)
                self.add_output('x', val=0.)

            def apply_nonlinear(self, inputs, outputs, residuals):
                residuals['x'] = np.exp(outputs['x']) - \
                    inputs['a']**2 * outputs['x']**2

            def linearize(self, inputs, outputs, jacobian):
                jacobian['x', 'x'] = np.exp(outputs['x']) - \
                    2 * inputs['a']**2 * outputs['x']
                jacobian['x', 'a'] = -2 * inputs['a'] * outputs['x']**2


        class Sub(Group):
            def setup(self):
                self.add_subsystem('comp', ImplSimple())

            def configure(self):
                # This solver won't solve the sytem. We want
                # to override it in the parent.
                self.nonlinear_solver = NonlinearBlockGS()


        class Super(Group):
            def setup(self):
                self.add_subsystem('sub', Sub())

            def configure(self):
                # This will solve it.
                self.sub.nonlinear_solver = NewtonSolver()
                self.sub.linear_solver = ScipyKrylov()


        top = Problem()
        top.model = Super()

        top.setup(check=False)

        print(isinstance(top.model.sub.nonlinear_solver, NewtonSolver))
        print(isinstance(top.model.sub.linear_solver, ScipyKrylov))

    def test_feature_post_setup_solver_configure(self):
        from openmdao.api import Problem, Group, ImplicitComponent, NewtonSolver, ScipyKrylov, NonlinearBlockGS

        class ImplSimple(ImplicitComponent):

            def setup(self):
                self.add_input('a', val=1.)
                self.add_output('x', val=0.)

            def apply_nonlinear(self, inputs, outputs, residuals):
                residuals['x'] = np.exp(outputs['x']) - \
                    inputs['a']**2 * outputs['x']**2

            def linearize(self, inputs, outputs, jacobian):
                jacobian['x', 'x'] = np.exp(outputs['x']) - \
                    2 * inputs['a']**2 * outputs['x']
                jacobian['x', 'a'] = -2 * inputs['a'] * outputs['x']**2


        class Sub(Group):

            def setup(self):
                self.add_subsystem('comp', ImplSimple())

                # This will not solve it
                self.nonlinear_solver = NonlinearBlockGS()

            def configure(self):
                # This will not solve it either.
                self.nonlinear_solver = NonlinearBlockGS()


        class Super(Group):

            def setup(self):
                self.add_subsystem('sub', Sub())


        top = Problem()
        top.model = Super()

        top.setup(check=False)

        # This will solve it.
        top.model.sub.nonlinear_solver = NewtonSolver()
        top.model.sub.linear_solver = ScipyKrylov()

        self.assertTrue(isinstance(top.model.sub.nonlinear_solver, NewtonSolver))
        self.assertTrue(isinstance(top.model.sub.linear_solver, ScipyKrylov))

if __name__ == "__main__":
    unittest.main()
