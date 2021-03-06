***************
Parallel Groups
***************

When systems are added to a ParallelGroup, they will be executed in parallel, assuming that the ParallelGroup is
given an MPI communicator of sufficient size.  Adding subsystems to a ParallelGroup is no different than adding them
to a normal Group.  For example:


.. embed-test::
  openmdao.core.tests.test_parallel_groups.TestParallelGroups.test_fan_in_grouped_feature


In this example, components *c1* and *c2* will be executed in parallel, provided that the ParallelGroup is given 2
MPI processes.  If the name of the python file containing our example were `my_par_model.py`, we could run it under
MPI and give it 2 processes using the following command:


.. code-block:: console

  mpirun -n 2 python my_par_model.py


.. note::

  This will only work if you've installed the mpi4py and petsc4py python packages, which are not installed by default
  in OpenMDAO.


In the previous example, both components in the ParallelGroup required just a single MPI process, but
what happens if we want to add subsystems to a ParallelGroup that have other processor requirements?
In OpenMDAO, we control process allocation behavior by setting the *min_procs* and/or *max_procs* or
*proc_weights* args when we call the *add_subsystem* function to add a particular subsystem to
a ParallelGroup.


.. automethod:: openmdao.core.group.Group.add_subsystem
    :noindex:


If you use both *min_procs/max_procs* and *proc_weights*, it can become less obvious what the
resulting process allocation will be, so you may want to stick to just using one or the other.
The algorithm used for the allocation starts, assuming that the number of processes is greater or
equal to the number of subsystems, by assigning the *min_procs* for each subsystem.  It then adds
any remaining processes to subsystems based on their weights, being careful not to exceed their
specified *max_procs*, if any.

If the  number of processes is less than the number of subsystems then each subsystem, one at a
time starting with the one with the highest *proc_weight*, is allocated to the least
loaded process.  An exception will be raised if any of the subsystems in this case have a
*min_procs* value greater than 1.
