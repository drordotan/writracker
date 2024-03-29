"""
Plot an experiment to a pdf file
"""

import math
import re
from matplotlib.backends import backend_pdf
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patches

import writracker.utils as u
from writracker.encoder.transform import get_bounding_box


#------------------------------------------------------------------------------
# noinspection PyMethodMayBeStatic
class PdfPlotter(object):

    def __init__(self, bounding_box=False, temporal_gaps=False, fraction_of_x_points=None, fraction_of_y_points=None,
                 cols_per_page=2, rows_per_page=5, n_colors=10, trial_title=None):
        """

        :param bounding_box: True/False plot bounding box
        :param temporal_gaps: True/False plot temporal gaps between adjacent characters
        :param fraction_of_x_points: This % of x-points determines the bounding box
        :param fraction_of_y_points: This % of y-points determines the bounding box
        :param cols_per_page: Number of stimuli per row in each page
        :param rows_per_page: Number of stimuli per column in each page
        :param n_colors: Number of grayscale color gradients for showing pen pressure
        :param trial_title: Function that sets each trial's title
        """
        self.bounding_box = bounding_box
        self.temporal_gaps = temporal_gaps
        self.fraction_of_x_points = fraction_of_x_points
        self.fraction_of_y_points = fraction_of_y_points
        self.cols_per_page = cols_per_page
        self.rows_per_page = rows_per_page
        self.n_colors = n_colors
        self.get_trial_title = trial_title or TrialTitle()

        self.bounding_box_line_width = 0.5

    #------------------------------------------------------------------------------
    def plot(self, trials, out_fn, max_trials=None):
        """
        Plot the experiment raw data - the characters, as the subject wrote them - and save to a PDF file.

        :param trials: either a list of CodedTrial objects or an Experiment object (coded)
        :param out_fn: PDF file name
        :param cols_per_page: No. of trial columns in each page
        :param rows_per_page: No. of trial rows in each page
        :param n_colors: No. of colors to use to denote level of pressure
        :param max_trials: Plot only the first trials in the experiment
        """

        if hasattr(trials, 'sorted_trials'):
            trials = list(trials.sorted_trials)

        assert len(trials) > 0

        n_trials_per_page = self.cols_per_page * self.rows_per_page

        pdf = backend_pdf.PdfPages(out_fn)
        z_values = np.array([point.z for t in trials for point in t.on_paper_points])
        max_z = max(z_values)

        def get_z_levels(z):
            return _convert_z_to_level(z, max_z, self.n_colors)

        if max_trials is not None:
            trials = trials[:min(max_trials, len(trials))]

        n_pages = math.ceil(len(trials) / n_trials_per_page)

        progress = u.ProgressBar(len(trials), 'Preparing pdf...')
        n_done = 0

        while len(trials) > 0:

            curr_page_n_trials = min(n_trials_per_page, len(trials))
            fig, axes = plt.subplots(self.rows_per_page, self.cols_per_page)
            fig.subplots_adjust(hspace=.8, wspace=0.3)

            axes = np.reshape(axes, [n_trials_per_page])

            for i in range(curr_page_n_trials):
                trial = trials.pop(0)
                n_done += 1
                ax = axes[i]
                ax.get_yaxis().set_visible(False)
                ax.get_xaxis().set_visible(False)
                ax.set_title(self.get_trial_title(trial), fontdict=dict(fontsize=5))
                self.plot_trial(trial, ax=ax, get_z_levels=get_z_levels)

            if curr_page_n_trials < n_trials_per_page:
                for i in range(curr_page_n_trials, n_trials_per_page):
                    ax = axes[i]
                    ax.get_yaxis().set_visible(False)
                    ax.get_xaxis().set_visible(False)

            pdf.savefig(fig)
            plt.close(fig)

            progress.progress(n_done)

        pdf.close()

        if n_pages > 3:
            print('')

    #------------------------------------------------------------------------------
    def plot_trial(self, trial, n_colors=10, get_z_levels=None, ax=None):
        """
        Plot the trial raw data - the characters, as the subject wrote them.

        :type trial: trajwriter.Trial
        :param n_colors: No. of colors to use to denote level of pressure
        :param ax: The axes to use for plotting
        """
        lightest_color = 0.95

        points = trial.on_paper_points
        if len(points) == 0:
            return

        x = np.array([point.x for point in points])
        y = np.array([point.y for point in points])
        z = np.array([point.z for point in points])
        # minz = int(min(z))
        if get_z_levels is None:
            z = _convert_z_to_level(z, max(z), n_colors)
        else:
            z = get_z_levels(z)

        if ax is None:
            ax = plt.figure()

        self._draw_trial_rectangles(trial, ax)

        for z_level in range(n_colors+1):
            inds = z == z_level
            if sum(inds) > 0:
                color = lightest_color * (1 - z_level/n_colors)
                #before:
                color = (color, ) * 3

                #c = int(minz/10)
                #mult = c if (c>3 and c< 5) else 3
                #color = (color, ) * (int(mult))
                ax.scatter(x[inds], y[inds], color=color, s=4)

    #-------------------------------------------------------------
    def _draw_trial_rectangles(self, trial, ax):

        if not self.bounding_box and not self.temporal_gaps:
            return

        characters = trial.characters

        gaps = []
        ys = []
        xs = []
        firstx = 0

        for n, c in enumerate(characters):
            box = get_bounding_box(c, fraction_of_x_points=self.fraction_of_x_points, fraction_of_y_points=self.fraction_of_y_points)
            x, y = box[4], box[5]
            ys.append(int(y))
            xs.append(int(x))
            if characters.index(c) == 0:
                firstx = x

            gap = " " * int(c.pre_char_delay/120)
            gap += "\npre-" + str(c.character) + ":\n"
            gap += (" {0:.2f}s".format(c.pre_char_delay))

            gaps.append(gap)

            if self.bounding_box:
                rect = patches.Rectangle((x, y), box[1], box[3],
                                         edgecolor='r' if (n % 2 == 0) else 'b', facecolor='none')
                rect.set_linewidth(self.bounding_box_line_width)
                ax.add_patch(rect)


        #-- Plot temporal gaps
        if self.temporal_gaps:
            bott = int(min(ys))
            for i in range(len(gaps)):
                #print("bott-100 is " + str(bott-100))
                ax.text(firstx-100 + i * 510, bott - 150, gaps[i], fontsize=4, ha="left", va="center",
                        bbox=dict(boxstyle="square", linewidth=0.3, ec=(1., 0.5, 0.5), fc=(1., 0.8, 0.8) if i % 2 == 0 else (1., 0.65, 0.65)))

#-------------------------------------------------------------
def default_trial_title(trial):
    """
    Default trial title: Trial [id] (#[target]): [stimulus]
    """

    title = 'Trial {:}'.format(trial.trial_id)

    if trial.target_id is not None:
        title += '(#{:})'.format(trial.target_id)

    if trial.stimulus is not None:
        if isinstance(trial.stimulus, int) or trial.stimulus.isdigit():
            title += ': {:,d}'.format(int(trial.stimulus))
        else:
            title += ': {}'.format(trial.stimulus)

    return title


#-------------------------------------------------------------
def _trial_stim(trial):
    if isinstance(trial.stimulus, int) or trial.stimulus.isdigit():
        return '{:,d}'.format(int(trial.stimulus))
    else:
        return str(trial.stimulus)


#-------------------------------------------------------------
class TrialTitle(object):

    def __init__(self, format='Trial {trial_id}(#{target_id}): {stimulus}'):
        #self.validate_format(format)
        self.format = format
        self.keywords = dict(
                trial_id=lambda trial: str(trial.trial_id),
                target_id=lambda trial: str(trial.target_id),
                stimulus=_trial_stim,
                response=self.response,
                rc=lambda trial: str(trial.rc),
                nchars=lambda trial: str(len(trial.characters)),
                nstrokes=lambda trial: str(len(trial.strokes)),
        )

    def __call__(self, trial):

        title = self.format
        while True:
            m = re.match('^(.*)\\{(\\w+)}(.*)$', title)
            if m is None:
                break

            title = m.group(1) + self.keywords[m.group(2)](trial) + m.group(3)

        return title

    def response(self, trial):
        if str(trial.stimulus) == str(trial.response):
            return '='
        else:
            return str(trial.response)


#-------------------------------------------------------------
def _convert_z_to_level(z_values, max_z, n_colors):
    return np.round(z_values * (n_colors / max_z)).astype(int)
