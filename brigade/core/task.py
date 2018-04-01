from builtins import super

from brigade.core.exceptions import BrigadeExecutionError


class Task(object):
    """
    A task is basically a wrapper around a function that has to be run against multiple devices.
    You won't probably have to deal with this class yourself as
    :meth:`brigade.core.Brigade.run` will create it automatically.

    Arguments:
        task (callable): function or callable we will be calling
        name (``string``): name of task, defaults to ``task.__name__``
        **kwargs: Parameters that will be passed to the ``task``

    Attributes:
        task (callable): function or callable we will be calling
        name (``string``): name of task, defaults to ``task.__name__``
        params: Parameters that will be passed to the ``task``.
        self.results (:obj:`brigade.core.task.MultiResult`): Intermediate results
        host (:obj:`brigade.core.inventory.Host`): Host we are operating with. Populated right
          before calling the ``task``
        brigade(:obj:`brigade.core.Brigade`): Populated right before calling
          the ``task``
    """

    def __init__(self, task, name=None, **kwargs):
        self.name = name or task.__name__
        self.task = task
        self.params = kwargs
        self.results = MultiResult(self.name)

    def __repr__(self):
        return self.name

    def _start(self, host, brigade, sub_task=False):
        self.host = host
        self.brigade = brigade
        r = self.task(self, **self.params) or Result(host)
        r.name = self.name

        if sub_task:
            return r
        else:
            self.results.insert(0, r)
            return self.results

    def run(self, task, **kwargs):
        """
        This is a utility method to call a task from within a task. For instance:

            def grouped_tasks(task):
                task.run(my_first_task)
                task.run(my_second_task)

            brigade.run(grouped_tasks)

        This method will ensure the subtask is run only for the host in the current thread.
        """
        if not self.host or not self.brigade:
            msg = ("You have to call this after setting host and brigade attributes. ",
                   "You probably called this from outside a nested task")
            raise Exception(msg)

        r = Task(task, **kwargs)._start(self.host, self.brigade, sub_task=True)

        if isinstance(r, MultiResult):
            self.results.extend(r)
        else:
            self.results.append(r)
        return r

    def is_dry_run(self, override=None):
        """
        Returns whether current task is a dry_run or not.

        Arguments:
            override (bool): Override for current task
        """
        return override if override is not None else self.brigade.dry_run


class Result(object):
    """
    Result of running individual tasks.

    Arguments:
        changed (bool): ``True`` if the task is changing the system
        diff (obj): Diff between state of the system before/after running this task
        result (obj): Result of the task execution, see task's documentation for details
        host (:obj:`brigade.core.inventory.Host`): Reference to the host that lead ot this result
        failed (bool): Whether the execution failed or not
        exception (Exception): uncaught exception thrown during the exection of the task (if any)

    Attributes:
        changed (bool): ``True`` if the task is changing the system
        diff (obj): Diff between state of the system before/after running this task
        result (obj): Result of the task execution, see task's documentation for details
        host (:obj:`brigade.core.inventory.Host`): Reference to the host that lead ot this result
        failed (bool): Whether the execution failed or not
        exception (Exception): uncaught exception thrown during the exection of the task (if any)
    """

    def __init__(self, host, result=None, changed=False, diff="", failed=False, exception=None,
                 **kwargs):
        self.result = result
        self.host = host
        self.changed = changed
        self.diff = diff
        self.failed = failed
        self.exception = exception
        self.name = None

        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return '{}: "{}"'.format(self.__class__.__name__, self.name)

    def __str__(self):
        if self.exception:
            return str(self.exception)
        else:
            return str(self.result)


class AggregatedResult(dict):
    """
    It basically is a dict-like object that aggregates the results for all devices.
    You can access each individual result by doing ``my_aggr_result["hostname_of_device"]``.
    """
    def __init__(self, name, **kwargs):
        self.name = name
        super().__init__(**kwargs)

    def __repr__(self):
        return '{} ({}): {}'.format(self.__class__.__name__, self.name, super().__repr__())

    @property
    def failed(self):
        """If ``True`` at least a host failed."""
        return any([h.failed for h in self.values()])

    @property
    def failed_hosts(self):
        """Hosts that failed during the execution of the task."""
        return {h: r for h, r in self.items() if r.failed}

    def raise_on_error(self):
        """
        Raises:
            :obj:`brigade.core.exceptions.BrigadeExecutionError`: When at least a task failed
        """
        if self.failed:
            raise BrigadeExecutionError(self)


class MultiResult(list):
    """
    It is basically is a list-like object that gives you access to the results of all subtasks for
    a particular device/task.
    """
    def __init__(self, name):
        self.name = name

    def __getattr__(self, name):
        return getattr(self[0], name)

    def __repr__(self):
        return "{}: {}".format(self.__class__.__name__, super().__repr__())

    @property
    def failed(self):
        """If ``True`` at least a task failed."""
        return any([h.failed for h in self])

    @property
    def changed(self):
        """If ``True`` at least a task changed the system."""
        return any([h.changed for h in self])

    def raise_on_error(self):
        """
        Raises:
            :obj:`brigade.core.exceptions.BrigadeExecutionError`: When at least a task failed
        """
        if self.failed:
            raise BrigadeExecutionError(self)
