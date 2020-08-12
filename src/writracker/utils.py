import numpy as np
import os


#---------------------------------------------------------------------
def split_list_at(elems, is_bound, is_bound_args=None):
    """
    Split a list into several sub-lists according to some criterion

    :param elems: A list
    :param is_bound: A function that gets 2 arguments - elements i+1 and i - and returns True if the list should be split here
    """

    if '__getitem__' not in dir(elems):
        elems = tuple(elems)

    is_bound_args = is_bound_args or elems

    bounds = [is_bound(is_bound_args[i - 1], is_bound_args[i]) for i in range(1, len(is_bound_args))]
    bounds.insert(0, True)
    bounds.append(True)
    bounds = np.where(bounds)[0]

    result = [elems[bounds[i - 1]:bounds[i]] for i in range(1, len(bounds))]

    return result



#------------------------------------------------------------------------
class ProgressBar(object):

    def __init__(self, total, prefix='', suffix='', start_now=True):
        self._prefix = prefix
        self._suffix = suffix
        self._total = total
        self._last_progress = None
        if start_now:
            self.progress(0)


    def progress(self, n):
        progress = round(n / self._total * 1000) / 10
        if progress != self._last_progress:
            self._last_progress = progress
            print_progress_bar(progress, 100, self._prefix, self._suffix)


    def must_print_on_next(self):
        """ Next call to progress() will inevitably print the progress bar """
        self._last_progress = None


#------------------------------------------------------------------------
def print_progress_bar(iteration, total, prefix='Progress: ', suffix='', decimals=1, length=100, fill = '█'):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end = '')
    # Print New Line on Complete
    if iteration == total:
        print()


#------------------------------------------------------------------------
def is_windows():
    return os.name == 'nt'


#------------------------------------------------------------------------
def newline():
    return '\r\n' if os.name == 'nt' else '\n'

