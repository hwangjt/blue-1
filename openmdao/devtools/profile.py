from __future__ import print_function

import os
import sys
from time import time as etime
from inspect import getmembers, getmro
from fnmatch import fnmatchcase
import argparse
import json
import atexit
import types
from string import Template
from collections import OrderedDict, defaultdict
from functools import wraps
from struct import Struct
from ctypes import Structure, c_uint, c_float
from types import MethodType

from six import iteritems, itervalues

try:
    from mpi4py import MPI
except ImportError:
    MPI = None

from openmdao.devtools.webview import webview

def get_actual_class(frame, class_):
    """Given a frame and a class, find the class that matches the"""
    frame.f_code.co_filename
    for cls in getmro(meth.__self__.__class__):
        if meth.__name__ in cls.__dict__:
            return cls

def _prof_node(name, obj=None):
    return {
        'name': name,
        'time': 0.,
        'count': 0,
        'tot_time': 0.,
        'tot_count': 0,
        'children': [],
        'obj': obj,
    }

_profile_methods = None
_profile_prefix = None
_profile_out = None
_profile_start = None
_profile_setup = False
_profile_total = 0.0
_profile_matches = {}
_call_stack = []
_timing_stack = []
_inst_data = {}
_objs = {}   # mapping of ids to instance objects
_file2class = {}


def setup(prefix='prof_raw', methods=None, prof_dir=None):
    """
    Instruments certain important openmdao methods for profiling.

    Args
    ----

    prefix : str ('prof_raw')
        Prefix used for the raw profile data. Process rank will be appended
        to it to get the actual filename.  When not using MPI, rank=0.

    methods : dict, optional
        A dict of profiled methods to override the default set.  The key
        is the method name or glob pattern and the value is a tuple of class
        objects used for isinstance checking.  The default set of methods is:

        ::

            {
                "*": (System, Jacobian, Matrix, Solver, Driver, Problem),
            }

    prof_dir : str
        Directory where the profile files will be written.

    """

    global _profile_prefix, _profile_methods, _profile_matches
    global _profile_setup, _profile_total, _profile_out, _file2class

    if _profile_setup:
        raise RuntimeError("profiling is already set up.")

    if prof_dir is None:
        _profile_prefix = os.path.join(os.getcwd(), prefix)
    else:
        _profile_prefix = os.path.join(os.path.abspath(prof_dir), prefix)

    _profile_setup = True

    if methods is None:
        from openmdao.core.problem import Problem
        from openmdao.core.system import System
        from openmdao.core.driver import Driver
        from openmdao.solvers.solver import Solver
        from openmdao.jacobians.jacobian import Jacobian
        from openmdao.matrices.matrix import Matrix
        from openmdao.vectors.vector import Vector

        _profile_methods = {
            "*": (System, Jacobian, Matrix, Vector, Solver, Driver, Problem),
        }
    else:
        _profile_methods = methods

    rank = MPI.COMM_WORLD.rank if MPI else 0
    _profile_out = open("%s.%d" % (_profile_prefix, rank), 'wb')

    atexit.register(_finalize_profile)

    _profile_matches, _file2class = _collect_methods(_profile_methods)


def _collect_methods(method_dict):
    """
    Iterate over a dict of method name patterns mapped to classes.  Search
    through the classes for anything that matches and return a dict of
    exact name matches and their correspoding classes.

    Parameters
    ----------
    method_dict : {pattern1: classes1, ... pattern_n: classes_n}
        Dict of glob patterns mapped to lists of classes used for isinstance checks

    Returns
    -------
    dict
        Dict of method names and tuples of all classes that matched for that method.
    """
    matches = {}
    file2class = defaultdict(list)  # map files to classes

    for pattern, classes in iteritems(method_dict):
        for class_ in classes:
            fname = sys.modules[class_.__module__].__file__[:-1]
            classes = file2class[fname]
            if class_.__name__ not in classes:
                file2class[fname].append(class_.__name__)

            for name, obj in getmembers(class_):
                if callable(obj) and (pattern == '*' or fnmatchcase(name, pattern)):
                    if name in matches:
                        matches[name].append(class_)
                    else:
                        matches[name] = [class_]

    # convert values to tuples so we can use in isinstance call
    for name in matches:
        matches[name] = tuple(matches[name])

    return matches, file2class

def _instance_profile(frame, event, arg):
    """
    Collects profile data for functions that match _profile_matches.
    The data collected will include time elapsed, number of calls, ...
    """
    global _call_stack, _profile_out, _profile_struct, \
           _profile_funcs_dict, _profile_start, _profile_matches, _file2class

    if event == 'call':
        func_name = frame.f_code.co_name
        if func_name in _profile_matches:
            loc = frame.f_locals
            if 'self' in loc:
                self = loc['self']
                if isinstance(self, _profile_matches[func_name]):
                    classes = _file2class[frame.f_code.co_filename]
                    if not classes:
                        for base in self.__class__.__mro__[:-1]:
                            clist = _file2class[sys.modules[base.__module__].__file__[:-1]]
                            if base.__name__ not in clist:
                                clist.append(base.__name__)
                        classes = _file2class[frame.f_code.co_filename]
                    if len(classes) == 1:
                        name = "<%s#%d>.%s" % (classes[0], id(self), func_name)
                    else:
                        # TODO: fix this
                        raise RuntimeError("multiple classes %s in same module (%s) "
                                           "not supported yet" % (classes,
                                                                  frame.f_code.co_filename))
                    _call_stack.append(name)
                    _timing_stack.append(etime())

    elif event == 'return':
        func_name = frame.f_code.co_name
        if func_name in _profile_matches:
            loc = frame.f_locals
            if 'self' in loc:
                self = loc['self']
                if isinstance(self, _profile_matches[func_name]):
                    path = ','.join(_call_stack)

                    _call_stack.pop()
                    start = _timing_stack.pop()

                    if path not in _inst_data:
                        _inst_data[path] = _prof_node(path, self)

                    pdata = _inst_data[path]
                    pdata['time'] += etime() - start
                    pdata['count'] += 1

def start():
    """Turn on profiling.
    """
    global _profile_start, _profile_setup
    if _profile_start is not None:
        print("profiling is already active.")
        return

    if not _profile_setup:
        setup()  # just do a default setup

    _profile_start = etime()

    sys.setprofile(_instance_profile)

def stop():
    """Turn off profiling.
    """
    global _profile_total, _profile_start
    if _profile_start is None:
        return

    sys.setprofile(None)

    _profile_total += (etime() - _profile_start)
    _profile_start = None


def _finalize_profile():
    """called at exit to write out the file mapping function call paths
    to identifiers.
    """
    global _profile_prefix, _profile_funcs_dict, _profile_total

    stop()

    # fix names in _inst_data
    _obj_map = {}
    for funcpath, data in iteritems(_inst_data):
        fname = funcpath.rsplit(',', 1)[-1]
        try:
            name = data['obj'].pathname
        except AttributeError:
            pass
        else:
            klass = fname.split('#')[0][1:]
            _obj_map[fname] = '.'.join((name, "<%s.%s>" % (klass, fname.rsplit('.', 1)[-1])))

    rank = MPI.COMM_WORLD.rank if MPI else 0

    dname = os.path.dirname(_profile_prefix)
    fname = os.path.basename(_profile_prefix)
    with open("%s.%d" % (fname, rank), 'w') as f:
        f.write("@total 1 %f\n" % _profile_total)
        for name, data in iteritems(_inst_data):
            new_name = ','.join([
                _obj_map.get(s, s) for s in name.split(',')
            ])
            f.write("%s %d %f\n" % (new_name, data['count'], data['time']))


def _iter_raw_prof_file(rawname):
    """
    Returns an iterator of (elapsed_time, timestamp, funcpath)
    from a raw profile data file.
    """
    global _profile_struct

    fn, ext = os.path.splitext(rawname)
    dname = os.path.dirname(rawname)
    fname = os.path.basename(fn)

    with open(rawname, 'r') as f:
        for line in f:
            path, count, elapsed = line.split()
            yield path, int(count), float(elapsed)


def process_profile(flist):
    """Take the generated raw profile data, potentially from multiple files,
    and combine it to get hierarchy structure and total execution counts and
    timing data.

    Args
    ----

    flist : list of str
        Names of raw profiling data files.

    """

    nfiles = len(flist)
    funcs = {}
    totals = {}
    total_under_profile = 0.0
    tops = set()

    tree_nodes = {}

    # this name has to be '.' and not '', else we have issues
    # when combining multiple files due to sort order
    tree_nodes['@total'] = _prof_node('@total')

    for fname in flist:
        ext = os.path.splitext(fname)[1]
        try:
            extval = int(ext.lstrip('.'))
            dec = ext
        except:
            dec = False

        for funcpath, count, t in _iter_raw_prof_file(fname):

            # for multi-file MPI profiles, decorate names with the rank
            if nfiles > 1 and dec:
                parts = funcpath.split(',')
                parts = ["%s%s" % (p,dec) for p in parts]
                funcpath = ','.join(parts)

            if ',' not in funcpath:
                tops.add(funcpath)

                if funcpath == '@total':
                    total_under_profile += t

            tree_nodes[funcpath] = node = _prof_node(funcpath)
            node['time'] += t
            node['count'] += count

            funcname = funcpath.rsplit(',', 1)[-1]
            if funcname in totals:
                tnode = totals[funcname]
            else:
                totals[funcname] = tnode = _prof_node(funcname)
            tnode['tot_time'] += t
            tnode['tot_count'] += count

    # create the call tree
    for funcpath, node in iteritems(tree_nodes):
        parts = funcpath.rsplit(',', 1)
        if len(parts) > 1:
            parent, child = parts
            tree_nodes[parent]['children'].append(tree_nodes[funcpath])
        elif funcpath != '@total':
            tree_nodes['@total']['children'].append(tree_nodes[funcpath])

    return tree_nodes['@total'], totals


def prof_dump(fname=None):
    """Print the contents of the given raw profile data file to stdout.

    Args
    ----

    fname : str
        Name of raw profile data file.
    """

    if fname is None:
        fname = sys.argv[1]

    for funcpath, count, t in _iter_raw_prof_file(fname):
        print(funcpath, count, t)


def prof_totals():
    """Called from the command line to create a file containing total elapsed
    times and number of calls for all profiled functions.

    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-o', '--outfile', action='store', dest='outfile',
                        metavar='OUTFILE', default='sys.stdout',
                        help='Name of file containing function total counts and elapsed times.')
    parser.add_argument('rawfiles', metavar='rawfile', nargs='*',
                        help='File(s) containing raw profile data to be processed. Wildcards are allowed.')

    options = parser.parse_args()

    if not options.rawfiles:
        print("No files to process.")
        sys.exit(0)

    if options.outfile == 'sys.stdout':
        out_stream = sys.stdout
    else:
        out_stream = open(options.outfile, 'w')

    _, totals = process_profile(options.rawfiles)

    try:

        out_stream.write("\nTotals\n------\n\n")
        out_stream.write("Total Calls Total Time Function Name\n")

        for func, data in sorted([(k,v) for k,v in iteritems(totals)],
                                    key=lambda x:x[1]['tot_time']):
            out_stream.write("%10d %11f %s\n" %
                               (data['tot_count'], data['tot_time'], func))

            func_name = func.split('.')[-1]

    finally:
        if out_stream is not sys.stdout:
            out_stream.close()

def prof_view():
    """Called from a command line to generate an html viewer for profile data."""

    parser = argparse.ArgumentParser()
    parser.add_argument('--noshow', action='store_true', dest='noshow',
                        help="Don't pop up a browser to view the data.")
    parser.add_argument('-t', '--title', action='store', dest='title',
                        default='Profile of Method Calls by Instance',
                        help='Title to be displayed above profiling view.')
    parser.add_argument('rawfiles', metavar='rawfile', nargs='*',
                        help='File(s) containing raw profile data to be processed. Wildcards are allowed.')

    options = parser.parse_args()

    if not options.rawfiles:
        print("No files to process.")
        sys.exit(0)

    call_graph, _ = process_profile(options.rawfiles)

    viewer = "icicle.html"
    code_dir = os.path.dirname(os.path.abspath(__file__))

    with open(os.path.join(code_dir, viewer), "r") as f:
        template = f.read()

    seen = {id(call_graph)}
    stack = call_graph['children'][:]
    while stack:
        entry = stack.pop()
        if id(entry) not in seen:
            seen.add(id(entry))
        else:
            raise RuntimeError("%s was already seen" % entry['name'])

    graphjson = json.dumps(call_graph)

    outfile = 'profile_' + viewer
    with open(outfile, 'w') as f:
        f.write(Template(template).substitute(call_graph_data=graphjson,
                                              title=options.title))

    if not options.noshow:
        webview(outfile)

if __name__ == '__main__':
    prof_dump(sys.argv[1])
